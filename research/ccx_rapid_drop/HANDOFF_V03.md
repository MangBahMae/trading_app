# 급락 대응 신호 v0.3 다음 기기 인계

브랜치 `feat/rapid-drop-signals-v03`, v0.2 기준 `aefe83ef583f1ae76129208ef3133cf089dfc610` 포함. 최종 SHA·원격 확인·Draft PR 주소는 작업 완료 응답을 참고한다. 기존 `.vscode/settings.json`과 수동 도형 DB는 유지했지만, **실제 매매 DB는 기존 회귀 테스트의 생성/삭제로 원본 해시가 바뀌었고 확정 복구하지 못했다.** `REPORT_V03.md` 사고 기록부터 읽는다.

2026-11-20 보완: Draft PR [#1](https://github.com/MangBahMae/trading_app/pull/1)을 유지한다. 추가 실행 전에 현재 DB 사본을 Git 제외 경로에 보존했다. 현재 trades `f046…`/manual `c14d…`는 전체 회귀와 격리 서버 종료 후에도 사본과 같다. 보호 파일 10슬롯의 추가 변경은 0이다. **이 사본은 사고 전 `d44b…` 백업이 아니며 원본 복구·데이터 영향 미확인 상태는 계속된다.** 현재 0행을 원래 빈 DB의 증거로 사용하지 않는다. 실제 DB를 덮어쓰지 않는다.

현재 안전 증거는 `results_v03/safety_20261120/`의 전후/최종 보존 JSON과 `backend_tests.log`, 실제 Edge 화면은 [BROWSER_VERIFICATION.md](results_v03/safety_20261120/BROWSER_VERIFICATION.md) 및 `screenshots/`를 확인한다. 고정 6/11 신규·6/12~13 유지·6/14 만료와 합성 첫 후보+경고·반복 접촉 중복 방지·무효·동일 지지 버전 회복·다음 날 중복 부재를 실제 캔버스 클릭으로 확인했다. 과거 원본 보존 실패 기록은 지우지 않았다.

```powershell
git status --short --branch
git fetch origin
git switch feat/rapid-drop-signals-v03
git merge --ff-only origin/feat/rapid-drop-signals-v03
git rev-parse HEAD
git ls-remote origin refs/heads/feat/rapid-drop-signals-v03
```

기본 기능은 OFF다. 연구 엔진은 `research/ccx_rapid_drop/rapid_drop.py` 한 파일이며 운영용 사본은 없다. API 정책은 `backend/app/services/rapid_drop_signals.py`, 수동 지지 버전은 `rapid_drop_support_history.py`, 표시 흐름은 `SignalScanner` → `useRapidDrop` → `SignalPanel` → `RapidDropPanel`이다. 먼저 `REPORT_V03.md`와 `results_v03/full_replay.json`을 읽는다.

운영 앱에서 실험을 켜려면 백엔드 시작 전에 `CCX_ENABLE_RAPID_DROP_SIGNALS=1`을 설정하고, 일봉 차트 범례의 `급락 대응 · 실험` 토글을 켠다. 기존 독립 신호 집계에 합산되지 않는다. 선택 날짜 GET `/api/rapid-drop?date=YYYY-MM-DD`만 호출하며 판단은 백엔드에서 한다.

개발 검증은 사용자 DB를 쓰지 않는 별도 실행기로 재현한다. 저장소 루트에서:

```powershell
Set-Location research/ccx_rapid_drop
& ../../backend/.venv/Scripts/python.exe -B -u dev_server_v03.py
# 합성 검증은 위 서버를 중지한 뒤 별도로 실행한다.
& ../../backend/.venv/Scripts/python.exe -B -u dev_server_v03.py --synthetic
```

다른 터미널에서는 `frontend`에서 `npm run dev -- --host 127.0.0.1`로 실행한다. 고정 모드는 실제 API 프런트 회귀용이며 합성 모드로 기존 전체 테스트를 대체하지 않는다. 합성 화면에는 `합성 데이터 · 검증용` 배지가 있어야 한다. 초기 턴에는 URL 확인 정책으로 실제 합성 화면 자동화가 중지됐고 우회하지 않았다. 11/20 새 검증에서 로컬 URL이 확인되는 전용 Edge 창을 사용해 실제 화면을 완료했다. 이번 검증 서버는 종료한 상태다.

합성 입력은 12봉이다. 2022-01-06 첫 후보+가속 경고, 1/8 재지지 신규, 1/9 새 롱 없이 두 후보 유지, 1/10 두 발행 후보 무효 및 접촉 관찰, 1/11 트랩 관찰만, 1/12 새 사건 없음이다. 실제 과거 수동 지지 검증으로 보고하지 않는다. 날짜 선택은 차트 캔들 클릭이며 우측 패널 날짜로 확인한다. 고정 데이터는 3M→전체로 전체 범위를 맞춘 뒤 시간축 확대/가로 스크롤로 2023년 6월을 선택할 수 있다.

검사 재현:

```powershell
# research/ccx_rapid_drop에서
& ../../backend/.venv/Scripts/python.exe -B -u run_checks_v03.py
& ../../backend/.venv/Scripts/python.exe -B -u verify_v03.py
# --synthetic 검증 서버가 떠 있을 때만
& ../../backend/.venv/Scripts/python.exe -B verify_api_v03.py
# frontend에서, 고정 검증 서버 :8000 사용
npx vitest run
npx tsc --noEmit -p .
npm run lint
npm run build
```

확인된 환경은 Python 3.13.2, pandas 3.0.5, numpy 2.5.2, Vite 8.3.1이다. 백엔드 전체 367개, 연구 46개, 프런트 154개 통과. 타입·빌드 통과, lint 오류 0·기존 경고 3개다. 고정 전체 1,762봉에서 실제 수동 지지 없이 신규 재지지 후보 2023-06-11 한 번, 6/12·13 유지, 6/14 만료다. 이는 거래·수익성이 아니다.

위 숫자는 초기 v0.3 실행이다. 11/20 안전 보완 후 backend 전체는 **396개 통과**(guard 29개 포함, 기존 경고 1개)했다. manual 해시 불일치도 실패 처리하며 양 DB의 보조 파일과 개인 지지 이력/lock 생성·삭제·변경까지 검사한다. 기존 실패 종료 상태도 지우지 않는다. 세션 trades 격리는 모듈 종료 정리까지 유지한다. 프런트·엔진·판정 설정은 이번에 수정하지 않아 타입/lint/빌드/프런트·연구·전체 접두 검사를 다시 실행하지 않았다. 초기 로그를 새 실행 결과로 덮어쓰지 않는다. 이후 재실행 로그는 새 날짜 디렉터리에 보관한다.

현재 `verify_v03.py`의 마지막 원기기 보존 assert는 매매 DB의 원본 SHA 불일치로 실패한다. 계산/접두 구간 결과는 사고 전에 생성된 `full_replay.json`과 신호 테스트로 구분해서 확인한다. 이 원기기 manifest를 다른 기기의 개인 파일 보존 증거로 사용하지 않는다. 원본 매매 DB 백업이 없으므로 현재 파일을 삭제하거나 추측으로 덮어쓰지 않는다. `run_checks_v03.py`는 보완한 세션 임시 DB와 실제 파일 시작/종료 해시 가드로 추가 변경 없이 통과했다.

새 수동 좌표 이력은 기본 `data/rapid_drop_support_versions.jsonl`이며 `CCX_RAPID_DROP_SUPPORT_HISTORY`로 경로를 선택한다. 원본 DB를 덮어쓰지 않는 별도 개인 파일이고 Git에서 제외한다. 다음 기기에 이력이 없으면 과거를 추측하지 않고 지지 미확인으로 시작한다. `created_at`만으로 이력을 복원하거나 현재 도형을 과거에 적용하지 않는다. 기록 시작 이전, 외부 편집의 관찰 사이 실제 시각, 추세선 판정은 확인할 수 없다. 손상 이력은 덮어쓰지 않는다.

실제 과거 수동 지지에서의 첫 후보·트랩, 운영 실시간 입력의 후보 표시, 체결·성과는 미검증이다. 기능 OFF·주봉의 추가 실제 브라우저 검사는 하지 않았으며 기존 자동 회귀와 구분한다. 후보 발생 기록과 상태 종료를 별도로 보존하고 종료는 실제 이전 후보 ID에 연결한다. 현재 규칙은 검증용 초안이다. main 병합·운영 배포·실제 주문은 승인 범위가 아니다.

다음 기기에서도 테스트·서버 시작 전에 그 기기의 trades/manual DB 및 sidecar·지지 이력을 먼저 별도 보존하고 해시를 기록한다. 이번 비공개 사본은 Git에 없으며 사본 경로 포인터도 제외했다. 이 기기의 manifest를 다른 기기 원본 증거로 사용하지 않는다. 사고 전 원본과 일치하는 백업을 별도로 확보하면 **사본끼리** 비교해 복구·영향을 조사하고, 확인되지 않은 파일로 실제 DB를 덮어쓰지 않는다.
