# 급락 대응 v0.2 다음 기기 인계

작업 브랜치는 `feat/rapid-drop-v02`이며, 검토 기준 `38d3f59685e577da2991323d97b448e72b66dd54`를 포함한다. 완료된 로컬·원격 최종 SHA와 실제 푸시 확인값은 최종 작업 응답에 기록한다. 다음 기기에서는 원격 브랜치 HEAD와 대조한다.

```powershell
git status --short --branch
git fetch origin
git switch feat/rapid-drop-v02
git merge --ff-only origin/feat/rapid-drop-v02
git rev-parse HEAD
git ls-remote origin refs/heads/feat/rapid-drop-v02
git merge-base --is-ancestor 38d3f59685e577da2991323d97b448e72b66dd54 HEAD
```

기존 미커밋 변경·사용자 DB를 유지한다. checkout/reset으로 DB를 복원하거나 다른 기기의 DB를 덮어쓸 필요가 없다. 이번 기기의 기존 `.vscode/settings.json`은 미커밋으로 남겼다.

프로젝트 가상환경의 의존성을 준비한 뒤 저장소 루트에서 실행한다:

```powershell
Set-Location research/ccx_rapid_drop
& ../../backend/.venv/Scripts/python.exe -B -m unittest discover -v
& ../../backend/.venv/Scripts/python.exe -B replay.py --repo ../.. --config example_config.json --levels levels.example.json --output results_v02/observations.jsonl
& ../../backend/.venv/Scripts/python.exe -B -u run_audit.py
```

확인된 환경은 Python 3.13.2, pandas 3.0.5, numpy 2.5.2다. 기존 기기에서는 샌드박스 밖 프로젝트 Python 실행이 필요했고, 가상환경 자체는 수정하지 않았다. `run_audit.py`의 비교에는 기준 커밋의 Git 이력이 필요하다. 개인 DB나 `.vscode`가 없는 다른 기기에서도 실행 가능하며, 없는 파일은 보존 검사에서 없다고 기록하고 새로 만들지 않는다.

읽을 순서는 `README.md` → `REPORT_V02.md` → `results_v02/v01_diff.csv` → `rapid_drop.py`다. 전체 봉 JSONL은 Git에 없는 로컬 생성물이며 위 명령으로 재생성한다. v0.1의 `REVIEW.md`와 `results/`는 과거 기록으로 그대로 남겼다.

JSONL 스키마는 0.2다. `events`가 사건 객체 배열로 바뀌었으며 `id`, 기준·지지 참조, 종가 위치, 두 거래량 배수, `entry_status=not_evaluated`가 있다. 세 반전 모양을 평가하지만 자동 매수 규칙은 없다. 기준은 한 개를 추적하고 새 반응은 독립적인 사실로 기록한다. 반전 재시험 후에도 기준은 종가 이탈·기간 만료까지 유지한다.

이 기기 검증: 테스트 46개 통과, 고정 1,762봉 전체 실행, 실제 접두 구간 1,762개/과거 관찰 비교 1,553,203개, 미래 32일 및 미래 지지 추가 불변성, 합성 지지 13개 시나리오/89개 접두 구간/각 미래 32일 확장에서 불일치 0개다. 보호 파일 232개(앱·사용자 DB·원본 모양 함수·기존 실험 설정 포함)의 실행 전후 해시가 같다.

실제 지지 입력은 여전히 `[]`다. 첫 수동 지지 반응, 수동 지지 이탈·회복은 합성 동작 검사만 했으며 실제 시장 경로는 검증 불가다. 과거 도형 좌표의 버전별 사용 가능 시점도 확인되지 않았다. 현재 도형을 과거에 소급 적용하지 않는다. 역망치 재시험은 합성으로 검증했으며 이번 실제 재시험 17건의 모양 분포는 없음 12, 도지 4, 망치 1이다.

후속 작업에서 실제 지지 검증을 하려면 당시 좌표 버전·알려진 시각의 이력이 필요하다. 자동 기준 가격을 사용자 지지선처럼 취급하지 않는다. 후보나 사건 건수를 거래 수 또는 수익성으로 보고하지 않는다. 분할 비중·손절·체결·손익·웹 통합·RSI·실제 주문은 구현하지 않았고, main 병합·운영 배포도 하지 않았다.
