# AGENTS.md - 이 저장소에서 작업하는 에이전트(Codex 등)를 위한 안내

BTCUSDT 신호 대시보드. 사용자와는 **한국어**로 소통한다. 코드 주석/문서/커밋 메시지도 한국어(기존 스타일 유지).

## 구조

| 경로 | 내용 |
|---|---|
| `backend/` | FastAPI. 신호 로직은 `backend/app/services/` (아래 "중요한 규칙" 참고) |
| `frontend/` | React + TypeScript + Vite + lightweight-charts 4.1.3. 다크 테마, 차트 중심 레이아웃 |
| `scripts/` | **원본(Streamlit 시절) 코드. 수정 금지** - 회귀 테스트의 기준선이다 |
| `app.py`, `components/` | 예전 Streamlit 앱(scripts/ 원본을 씀). 건드리지 않는다 |
| `data/merged/` | `*.parquet` 캐시(git 제외, 자동 생성), `manual_lines.db`(**사용자가 차트에 직접 그린 선/존 - 사용자 데이터**) |
| `docs/` | `weekly_signals.md`(주봉 규칙/상수), `golden_tests.md`(고정 데이터/골든값), `CURRENT_STATE.md`(2026-09 시점 옛 문서 - 최신 아님) |

## 실행 / 테스트

```
# 백엔드 (포트 8000)
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
# 프런트 (포트 5173, /api는 vite가 8000으로 프록시)
cd frontend && npx vite --port 5173

# 테스트
cd backend && .venv/Scripts/python -m pytest tests -q        # 301개, 네트워크/캐시/실제 DB 없이 통과해야 한다
cd frontend && npx tsc --noEmit -p . && npx vitest run && npm run build   # vitest 135개
```
- 백엔드 venv는 `backend/.venv`(Windows: `.venv/Scripts/python`). Windows + Git Bash 환경이다(경로는 슬래시, `/dev/null`).
- 프런트 통합 테스트(`SignalScanner.test.tsx`)는 **:8000에 떠 있는 백엔드**를 실제로 호출한다(`fileParallelism: false`). 테스트 전에 백엔드를 켜 둘 것.
- 백엔드 테스트는 고정 데이터를 쓴다: `backend/tests/fixtures/`(일봉 2022-01-01~2026-10-28, 주봉 2017-08-14~2026-10-19 CSV, 선/존 스냅샷 JSON).
  `conftest.py`가 `ensure_fresh_data`를 고정 CSV로 바꾸고 `requests` 호출을 막는다. 테스트가 네트워크/캐시/`manual_lines.db`에 기대면 안 된다.
- **골든값 테스트**(`test_daily_golden.py`): 신호 규칙을 일부러 바꿔 실패하면 `cd backend && .venv/Scripts/python tests/regen_golden.py`로 갱신하고
  `git diff backend/tests/golden/daily_golden.json`을 확인해 같은 커밋에 올린다. 상세는 `docs/golden_tests.md`.

## 중요한 규칙 (사용자와 합의된 것들)

1. **`scripts/`는 수정하지 않는다.** `backend/app/services/`는 그 이식본이고, 의도한 차이만 있다(`test_regression_pipeline.py`가 검증).
2. **`data/merged/manual_lines.db`는 사용자 데이터다.** `git checkout`/삭제/덮어쓰기 금지. 테스트는 임시 DB만 쓴다(`conftest.py`가 격리하고 세션 끝에 해시 확인).
   사용자가 차트에서 편집하면 이 파일이 "변경됨"으로 보이는데, 사용자가 말할 때만 별도 커밋(`data: 수동 라인/존 데이터 동기화`)으로 올린다.
3. **bare import 구조:** `backend/app/services/`의 모듈들은 서로 `import pipeline`처럼 모듈 이름으로 import한다(`dashboard.py`가 경로를 `sys.path`에 넣는 유일한 창구).
   같은 프로세스에서 `scripts/`와 `services/`를 동시에 import하지 말 것(회귀 테스트는 서브프로세스로 분리).
4. **미래 참조 금지.** 모든 신호는 해당 캔들 마감 시점까지의 정보만 쓴다. 진행 중(미마감) 일봉/주봉은 데이터에 넣지 않는다(UTC 기준 일봉, 월요일 시작 주봉).
5. **일봉 로직과 주봉 로직은 분리**돼 있다. 주봉 작업이 일봉 응답(`/api/dashboard`, `/api/market-state`)을 바꾸면 안 된다 -
   일봉 응답 JSON을 수정 전/후로 비교해 동일함을 증명하는 방식을 썼다. 기준값은 상수로 빼고(일봉/주봉 상수 분리), 매직 넘버를 코드에 박지 않는다.
6. **기능 플래그**(`feature_flags.py`): RSI 과매도 신호/다이버전스 마커는 `False`로 꺼 둔 것(코드는 보존), 캔들 패턴 "참고"는 `True`.
   `feature_flags.ENABLE_X`처럼 **모듈 속성으로 읽는다**(테스트가 바꿔 볼 수 있게 `from ... import` 금지).
7. 삭제한 것(복원하지 않기로 함): 다우이론 라벨, RSI 과매수 신호. 지우지 않고 끈 것은 위 플래그로 되살린다.

## 신호 규칙 요약 (자세한 건 각 모듈 상단 docstring)

- **캔들 패턴**(`candle_patterns.py`): 도지/망치형/역망치형. 숏 = 몸통 상단 >= 직전 10개 최댓값인 고점 캔들(당일, 아니면 다음 봉 "(다음 봉)"),
  롱 = 직전 캔들이 음봉이고 오늘이 패턴(당일만). 장대봉(몸통 3.5%)/급등락 후 2봉 안의 반대 방향 신호는 "무효"(참고). 신호 안 된 모양 캔들은 "참고 (고점/저점 아님)".
  기준값은 파일 상단 상수(`POSITION_LOOKBACK_N`, `LOW_PREV_BEAR_MIN_PCT`, `BIG_CANDLE_*`, `HAMMER_*` 등), 모양 기준값은 `compute_candle_shape(df, params)`로 주입 가능.
- **수동 선**(`manual_lines.py`): 수평선/추세선 근접(시가로 방향)과 돌파/이탈(종가로 방향, 진입/유지 중). **추세선은 이른 점부터 오른쪽으로 끝없이 연장**해 평가한다.
- **존**(`zone_signals.py`): 시간 범위는 time1~time2만(오른쪽 연장 안 함). 반응/이탈(첫날만)/유동성 스윕(반응 대체). 존 근처 판정은 캔들 신호의 `near_zone` 플래그.
- **EMA 터치**(`sr_touch.py`): EMA50/200, 근접은 시가·돌파는 종가 방향. 근접 0.1%/돌파 0.5%.
- **주봉**(`weekly_*.py`, `docs/weekly_signals.md`): 반전 캔들/장악형/매물소진/EMA20·50·200 터치, 주봉 전용 상수. 선/존은 일봉에서 그린 것을 **표시만**(주봉 신호엔 안 씀, 1W에서 그리기/편집/삭제 불가).
- 화면: 상단 바 `1D / 1W`, 왼쪽 도구 막대, 차트 위 범례(OHLC + 지표 토글), 아래 기간 바(기본 "전체"), 오른쪽 신호 패널.

## 작업 방식 (사용자 선호)

- **큰 변경은 계획을 먼저 보고하고 승인 후 구현**한다. 지시서와 실제 코드가 다르면 구현 전에 먼저 알린다.
- 규칙/기준값을 바꾸는 작업은 **수정 전/후 신호 diff**(건수, 바뀐 날짜)와 테스트 결과를 함께 보고한다. 비교 스크립트는 `backend/tests/regression/`에 있다.
- 단계별로 **커밋을 나누고**, 커밋 후 푸시한다(사용자가 단계마다 푸시해도 된다고 했다). `.vscode/`는 커밋하지 않는다.
- 테스트는 항상 돌려서 숫자(통과 개수)를 보고한다. 실패를 숨기지 않는다.
- 줄바꿈: 일부 파일은 CRLF, 일부는 LF다. 파일을 수정할 때 기존 줄바꿈을 유지한다(git이 경고를 내도 무시).
- 큰 Python 패치를 셸 heredoc에 넣으면 따옴표/백슬래시 문제가 나기 쉽다. 파일로 저장해서 실행하는 편이 안전하다.
