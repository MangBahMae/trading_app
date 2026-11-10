# 배포 (GitHub Actions -> EC2)

main에 push하면 `.github/workflows/deploy.yml`이 실행된다.

1. **backend-test**: `backend/` pytest (고정 데이터, 네트워크 없음)
2. **frontend-build**: `npm ci && npm run build` (tsc 타입 검사 + vite 빌드). vitest는 CI에서 돌리지 않는다.
3. **deploy** (1, 2 모두 통과 시)
   - 백엔드: `deploy/deploy_backend.sh`를 SSH로 실행 → manual_lines.db 백업 → 테스트한 커밋으로 `git merge --ff-only` → requirements.txt가 바뀌었으면 pip → `systemctl restart` → `/health` 확인
   - 프런트: 빌드한 `dist/`를 `FRONTEND_DIR`에 `rsync --delete-after`로 덮어쓰기 (백엔드가 성공했을 때만)

서버 환경: Ubuntu, `ubuntu` 사용자, 22번 포트 0.0.0.0/0 개방 + **키 인증만**.

---

## 최초 1회 설정 (사람이 직접)

### 0. 서버 값 확인 (서버에서)

```bash
systemctl list-units --type=service | grep -iE 'uvicorn|trading|fastapi'   # 서비스 이름
systemctl cat <서비스이름>                     # WorkingDirectory, ExecStart(venv 경로) 확인
sudo nginx -T 2>/dev/null | grep -nE 'server_name|root |alias |proxy_pass'   # 프런트 경로(root)
cd <저장소 경로> && git remote -v && git status --short && git log --oneline -1
<venv경로>/bin/python --version                 # → GitHub 변수 PYTHON_VERSION
```

여기서 확인한 값으로 아래 GitHub Variables를 채운다.

### 1. 로컬 PC: 배포 전용 SSH 키 만들기

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/trading_deploy -N ""
cat ~/.ssh/trading_deploy.pub     # → 서버 authorized_keys에 추가
cat ~/.ssh/trading_deploy         # → GitHub Secret EC2_SSH_KEY (BEGIN/END 줄 포함 전체)
ssh-keyscan -t ed25519,ecdsa,rsa <EC2 주소>   # → GitHub Secret EC2_KNOWN_HOSTS (출력 전체)
```

> `ssh-keyscan` 결과가 진짜 서버의 키인지 확인하려면 서버에서
> `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`의 지문과 비교한다.

### 2. 서버 (ubuntu로 접속해서)

```bash
# (1) 배포 키 등록
echo '<trading_deploy.pub 내용>' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# (2) 비밀번호 로그인 꺼져 있는지 확인 - "passwordauthentication no" 여야 한다
sudo sshd -T | grep -iE 'passwordauthentication|permitrootlogin|pubkeyauthentication'
#   yes로 나오면 /etc/ssh/sshd_config.d/ 에 'PasswordAuthentication no' 추가 후
#   sudo systemctl reload ssh     (기존 SSH 세션은 닫지 말고 새 창에서 접속 확인)

# (3) 서비스 재시작만 비밀번호 없이 허용 (<서비스이름>을 실제 이름으로)
echo 'ubuntu ALL=(root) NOPASSWD: /usr/bin/systemctl restart <서비스이름>' | sudo tee /etc/sudoers.d/trading-deploy
sudo chmod 440 /etc/sudoers.d/trading-deploy
sudo visudo -cf /etc/sudoers.d/trading-deploy      # "parsed OK" 확인
sudo -n systemctl restart <서비스이름> && echo OK  # 비밀번호 없이 되는지 확인

# (4) 저장소 상태 정리: 원격은 HTTPS(public이라 인증 불필요), 작업 트리는 manual_lines.db 외에 변경 없어야 함
cd <저장소 경로>
git remote set-url origin https://github.com/MangBahMae/trading_app.git
git status --short
git fetch origin main && git merge --ff-only origin/main   # 지금 한 번 최신으로 맞춰 두기

# (5) 프런트 경로에 ubuntu가 쓸 수 있어야 한다 (nginx root가 /var/www/... 처럼 root 소유인 경우)
ls -ld <FRONTEND_DIR>
sudo chown -R ubuntu:ubuntu <FRONTEND_DIR>   # 필요할 때만. nginx(www-data)는 읽기만 하면 된다

# (6) 첫 백업 (수동)
mkdir -p ~/backups/manual_lines && cp data/merged/manual_lines.db ~/backups/manual_lines/manual_lines_initial.db
```

### 3. AWS 콘솔

- EC2 → 보안 그룹 → 인바운드: **22/TCP 0.0.0.0/0** (A안). 80/443은 기존대로.
- (권장) 키 인증만 쓰는지 위 (2)에서 확인했는지 다시 체크. 이 방식은 다음에 B안(배포 시에만 러너 IP 허용)으로 바꿀 예정.

### 4. GitHub (저장소 Settings)

**Settings → Environments → New environment → `production`**
- (선택) Deployment branches: `main`만 허용

**Settings → Secrets and variables → Actions → Secrets**

| 이름 | 값 |
|---|---|
| `EC2_HOST` | EC2 퍼블릭 IP 또는 DNS (Elastic IP 권장 - 재시작 시 IP가 바뀌지 않게) |
| `EC2_SSH_KEY` | `~/.ssh/trading_deploy` 개인키 전체 |
| `EC2_KNOWN_HOSTS` | `ssh-keyscan` 출력 전체 |

**Settings → Secrets and variables → Actions → Variables**

| 이름 | 예시 | 비고 |
|---|---|---|
| `APP_DIR` | `/home/ubuntu/trading_app` | 서버 저장소 경로 |
| `VENV_DIR` | `/home/ubuntu/trading_app/backend/.venv` | systemd ExecStart의 venv |
| `SERVICE_NAME` | `trading-app.service` | systemd 서비스 이름 (sudoers 줄과 글자 그대로 같아야 함) |
| `FRONTEND_DIR` | `/var/www/trading-app` | nginx `root` 경로 (index.html이 있는 곳) |
| `PYTHON_VERSION` | `3.12` | 선택. 서버 venv 버전과 맞춤 (기본 3.12) |
| `HEALTH_URL` | `http://127.0.0.1:8000/health` | 선택. uvicorn 포트가 다르면 |

### 5. 첫 배포

변수까지 넣었으면 Actions 탭 → CI/CD → **Run workflow**로 수동 실행해서 확인 → 이후는 main push 때마다 자동.

---

## 운영

### 배포가 fast-forward 실패로 멈췄을 때

대부분 **서버에서 수정된 `manual_lines.db`** 와 **새 커밋의 `manual_lines.db`** 가 부딪힌 경우다. 배포 스크립트는 아무것도 덮어쓰지 않고 멈춘다.

```bash
cd <APP_DIR>
git status --short
ls -lt ~/backups/manual_lines | head    # 방금 백업이 있음
```
어느 쪽 DB를 살릴지 정한 뒤 직접 처리한다 (예: 서버 쪽을 살린다면 서버 DB를 로컬로 가져와 커밋하는 식). **`git reset --hard`/`git checkout -- data/` 로 서버 DB를 지우지 말 것.**

### 롤백

- 백엔드+프런트: 로컬에서 `git revert <커밋>` 후 push → 같은 파이프라인으로 재배포
- DB 복구: `~/backups/manual_lines/`의 파일을 서비스 중지 후 `data/merged/manual_lines.db`로 복사

### 수동 실행 (서버에서)

```bash
cd <APP_DIR>
APP_DIR=$PWD VENV_DIR=<venv> SERVICE_NAME=<서비스> DEPLOY_SHA=$(git rev-parse origin/main) \
  bash deploy/deploy_backend.sh
```
