# 고정 데이터 테스트와 골든값

백엔드 테스트는 **네트워크, 캐시 parquet(`data/merged/*.parquet`, git에 없음), 실제 `manual_lines.db` 없이** 새로 clone한
환경에서도 그대로 통과한다. 데이터는 전부 저장소 안의 픽스처다.

| 파일 | 내용 |
|---|---|
| `backend/tests/fixtures/BTCUSDT_1d_2022-01-01_2026-10-28.csv` | 마감된 일봉 1,762개 (기간은 파일명). 자동 갱신하지 않는다 |
| `backend/tests/fixtures/BTCUSDT_1w_2017-08-14_2026-10-19.csv` | 마감된 주봉 480개 (EMA 워밍업 포함) |
| `backend/tests/fixtures/manual_lines_snapshot.json` | 선/존 스냅샷: 존 3개(27, 28, 54 - 2026-10-28 시점 실제 DB 행 그대로) + 합성 수평선(9001, 65,000)과 추세선(9002, 2023-10-27 33,400 → 2023-11-14 34,800) |
| `backend/tests/golden/daily_golden.json` | 일봉 대시보드 신호 요약의 기대값(골든값) |
| `backend/tests/golden_support.py` | 위 파일 로더, 요약/비교/실패 메시지 도우미 (테스트와 재생성 스크립트가 같이 쓴다) |
| `backend/tests/regen_golden.py` | 골든값을 다시 뽑는 스크립트 |

## 어떻게 연결되나 (`backend/tests/conftest.py`)

- 세션 시작 때 `data_fetcher.ensure_fresh_data`와 `pipeline.ensure_fresh_data`를 고정 일봉 CSV로 바꾸고, 테스트 중 `requests` 호출은
  막는다(고정 데이터를 안 쓰는 테스트가 몰래 네트워크에 기대면 바로 실패한다). 주봉은 `weekly_offline` 픽스처로 같은 방식.
- `lines_store.DB_PATH`는 모든 테스트에서 빈 임시 DB로 바뀐다(실제 DB는 읽지도 쓰지도 않고, 세션 끝에 해시로 확인). 선/존이 필요한
  테스트는 `seed_snapshot_db` 픽스처로 스냅샷(id 그대로)을 그 임시 DB에 채워 쓴다. 그래서 차트에서 선/존을 편집해도 테스트는 안 깨진다.
- 회귀 테스트(`test_regression_pipeline.py`)의 원본/이식본 서브프로세스는 `dump_pipeline_result.py --daily-fixture <csv>`로 같은
  고정 일봉을 보게 한다.

## 골든값 테스트 (`test_daily_golden.py`)

고정 일봉 + 선/존 스냅샷으로 `dashboard.get_dashboard_data()`를 계산해 신호 요약을 `daily_golden.json`과 비교한다.
요약에는 캔들 수/기간, 신호 총수와 신호가 있는 날 수, 방향별 건수, 항목별 건수(신호 문구에서 가격/날짜 같은 숫자를 `#`으로
바꿔 묶음 - 예: `수평선 # 근접 - 지지 시험 (매수 후보)`, EMA50/EMA200 같은 이름은 유지), 존별 신호 건수, `near_zone`/`next_bar` 건수,
그리고 개별 신호 전체의 해시(`signals_sha256`)가 들어 있다.

실패하면 어떤 항목이 몇에서 몇으로 바뀌었는지 한눈에 보인다:

```
일봉 골든값이 바뀌었다 (3개 항목: 기대 -> 실제):
  - by_category['도지 - 롱 후보']: 130 -> 128 (-2)
  - by_category['도지 - 롱 무효 (장대 음봉 #/#)']: 26 -> 28 (+2)
  - signals_total: 3683 -> 3683 ...
의도한 규칙 변경이면 골든값을 다시 뽑아 diff를 확인한 뒤 커밋한다: ...
```

항목별 건수는 같은데 개별 신호의 날짜/문구가 바뀐 경우는 "개별 신호가 바뀌었다 (signals_sha256 불일치)"로 알려 준다.

## 골든값 다시 뽑기

의도한 규칙 변경(신호 규칙, 기준값 등) 뒤에 골든 테스트가 실패하면, 차이가 의도한 것인지 확인한 다음:

```
cd backend
.venv/Scripts/python tests/regen_golden.py            # 새로 계산 -> 기존 골든값과의 차이를 출력하고 daily_golden.json 갱신
.venv/Scripts/python tests/regen_golden.py --check    # 파일은 그대로 두고 차이만 출력 (다르면 종료 코드 1)
```

1. 실패한 테스트의 메시지(또는 `--check` 출력)로 바뀐 항목을 확인한다. 의도하지 않은 변화면 코드를 고친다.
2. 의도한 변화면 `regen_golden.py`를 돌린다(테스트와 같은 고정 데이터/스냅샷/임시 DB 환경에서 계산한다).
3. `git diff backend/tests/golden/daily_golden.json`으로 바뀐 숫자를 다시 확인하고, 규칙 변경과 같은 커밋에 올린다.

## 픽스처 데이터를 새로 만들어야 할 때

- **일봉/주봉 CSV 갱신(예: 새 마감 캔들까지 늘리기):** 캐시나 Binance에서 받은 마감 캔들을 `open_time, open, high, low, close, volume, close_time`
  열 그대로(시각은 ISO 문자열, UTC)로 저장하고 파일명의 기간을 바꾼다. `golden_support.py`의 경로 상수와
  `test_regression_pipeline.py`/`dump_pipeline_result.py` 호출부를 새 파일명으로 맞추고, 신호가 늘어나므로 골든값과
  주봉 건수 고정 테스트(`test_weekly_signals.py`)도 같이 갱신한다.
- **선/존 스냅샷 갱신:** `manual_lines_snapshot.json`의 `lines`를 고치고(실제 DB에서 옮길 때는 읽기 전용으로만 열 것) `regen_golden.py`를 돌린다.
