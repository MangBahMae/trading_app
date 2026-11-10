#!/usr/bin/env bash
# 서버(EC2)에서 실행되는 백엔드 배포 스크립트.
#
# GitHub Actions가 이 파일을 서버에 두지 않고 SSH 표준입력으로 흘려 실행한다
#   ssh prod "APP_DIR=... VENV_DIR=... SERVICE_NAME=... DEPLOY_SHA=... bash -s" < deploy/deploy_backend.sh
# 그래서 항상 "배포하려는 커밋의" 스크립트가 돌고, git이 실행 중인 스크립트 파일을 바꾸는 문제도 없다.
# 서버에서 손으로 돌릴 때도 같은 환경변수를 주면 된다.
#
# 순서: manual_lines.db 백업 -> 정확히 DEPLOY_SHA로 fast-forward -> (requirements.txt가 바뀌었으면) pip install
#       -> systemctl restart -> /health 확인
#
# 주의: data/merged/manual_lines.db는 사용자 데이터다. 절대 reset --hard / checkout 으로 덮어쓰지 않는다.
#       fast-forward가 안 되면(서버에서 바뀐 DB와 새 커밋이 충돌 등) 배포를 실패로 끝내고 사람이 처리한다.
set -euo pipefail

main() {
  : "${APP_DIR:?APP_DIR(서버의 저장소 경로)가 필요합니다}"
  : "${VENV_DIR:?VENV_DIR(백엔드 venv 경로)가 필요합니다}"
  : "${SERVICE_NAME:?SERVICE_NAME(systemd 서비스 이름)이 필요합니다}"
  : "${DEPLOY_SHA:?DEPLOY_SHA(배포할 커밋)가 필요합니다}"
  local health_url="${HEALTH_URL:-http://127.0.0.1:8000/health}"
  local backup_dir="${BACKUP_DIR:-$HOME/backups/manual_lines}"
  local backup_keep="${BACKUP_KEEP:-30}"
  local py="$VENV_DIR/bin/python"

  cd "$APP_DIR"
  echo "==> 배포 대상: $DEPLOY_SHA (현재 HEAD: $(git rev-parse HEAD))"

  # 1) manual_lines.db 백업 - 서비스가 쓰는 중일 수 있으므로 cp 대신 SQLite 온라인 백업 API를 쓴다
  local db="data/merged/manual_lines.db"
  if [[ -f "$db" ]]; then
    mkdir -p "$backup_dir"
    local dest="$backup_dir/manual_lines_$(date +%Y%m%d_%H%M%S).db"
    "$py" - "$db" "$dest" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
PY
    echo "==> manual_lines.db 백업: $dest"
    # 오래된 백업 정리 (최근 $backup_keep 개만 유지)
    ls -1t "$backup_dir"/manual_lines_*.db 2>/dev/null | tail -n +"$((backup_keep + 1))" | xargs -r rm --
  else
    echo "==> $db 없음 - 백업 건너뜀"
  fi

  # 2) 코드 갱신: 정확히 테스트를 통과한 커밋으로만 fast-forward
  local req="backend/requirements.txt"
  local old_req_hash
  old_req_hash="$(sha256sum "$req" | cut -d' ' -f1)"

  git fetch --quiet origin main
  if ! git merge --ff-only "$DEPLOY_SHA"; then
    echo "!!! fast-forward 실패 - 배포 중단 (서버 파일은 그대로 둠)" >&2
    echo "!!! 서버의 로컬 변경 사항:" >&2
    git status --short >&2
    echo "!!! manual_lines.db 충돌이면 deploy/README.md의 '배포가 fast-forward 실패로 멈췄을 때'를 보세요." >&2
    exit 1
  fi

  # 3) 의존성: requirements.txt가 바뀌었을 때만 설치
  local new_req_hash
  new_req_hash="$(sha256sum "$req" | cut -d' ' -f1)"
  if [[ "$old_req_hash" != "$new_req_hash" || "${FORCE_PIP:-0}" == "1" ]]; then
    echo "==> requirements.txt 변경됨 - pip install"
    "$py" -m pip install --quiet -r "$req"
  else
    echo "==> requirements.txt 변경 없음 - pip 건너뜀"
  fi

  # 4) 재시작 (-n: sudoers 설정이 없으면 비밀번호를 기다리지 않고 바로 실패)
  echo "==> sudo systemctl restart $SERVICE_NAME"
  sudo -n systemctl restart "$SERVICE_NAME"

  # 5) 헬스체크 (최대 약 30초)
  for i in $(seq 1 15); do
    if curl -fsS --max-time 3 "$health_url" >/dev/null; then
      echo "==> 헬스체크 통과 ($health_url, ${i}회차)"
      echo "==> 배포 완료: $(git rev-parse --short HEAD)"
      return 0
    fi
    sleep 2
  done

  echo "!!! 헬스체크 실패: $health_url" >&2
  journalctl -u "$SERVICE_NAME" -n 50 --no-pager >&2 || true
  exit 1
}

main "$@"
