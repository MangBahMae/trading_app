# 주봉(1W) 신호 규칙과 상수

주봉은 일봉과 **별도 모듈**이다. 일봉 신호/응답은 건드리지 않는다.

| 파일 | 역할 |
|---|---|
| `backend/app/services/weekly_data.py` | Binance 1w 수집, 캐시(`data/merged/BTCUSDT_1w_dashboard.parquet`) |
| `backend/app/services/weekly_signals.py` | 신호 4종과 주봉 전용 상수 |
| `backend/app/services/weekly.py` | `/api/dashboard/weekly` 응답 조립 (EMA, RSI(표시용), 신호, 일봉 선/존) |
| `backend/app/services/candle_patterns.py` | `compute_candle_shape(df, params)` - 모양 판정 기준값을 인자로 받을 수 있다(기본값은 일봉 모듈 상수) |

## 데이터

- Binance BTCUSDT 1w 캔들. 월요일 00:00 UTC에 열려 일요일 23:59:59.999 UTC에 마감한다. **마감된 주만** 쓴다
  (진행 중인 주는 캐시/응답/신호 어디에도 없다). 새 주봉은 한국시간 월요일 09:00 이후에 확정된다.
- 캐시는 일봉과 같은 구조: 없으면 전체를 페이지네이션으로 받고, 있으면 마지막 캔들 이후만 증분으로 이어붙인다.
- **EMA 워밍업:** EMA200(200주 = 약 4년)이 2022년 초부터 유효하도록 캐시는 `WEEKLY_CACHE_START = 2017-08-01`부터 받는다
  (Binance 첫 주봉은 2017-08-14). 응답의 캔들과 신호는 `WEEKLY_DISPLAY_START = 2022-01-03`(2022-01-01 이후 첫 월요일)부터만이다.
  신호의 "직전 주"는 표시 시작 이전 주도 쓴다.

## 신호 4종

모든 판정은 해당 주 마감 시점까지의 정보만 쓴다(미래 참조 없음). 같은 주에 여러 신호가 겹칠 수 있고 중복 제거는 하지 않는다.
신호 문구는 일봉과 구분되게 앞에 "주봉"이 붙고, `source` / `near_zone` / `next_bar`는 비어 있다(None).
장대봉/시세분출 무효는 주봉에 적용하지 않는다. 선/존은 신호 판정에 쓰지 않는다(1W 화면에서 표시만).

1. **반전 캔들** - 직전 주가 양봉(몸통 >= `W_REVERSAL_PREV_BODY_MIN_PCT`)이고 이번 주가 도지/망치형/역망치형이면 **숏 후보**,
   직전 주가 음봉(몸통 >= 같은 값)이면 **롱 후보**. 직전 주 시가 == 종가(몸통 0)면 무신호.
   - `주봉 {도지|망치형|역망치형} 반전 - 숏 후보` / `롱 후보`
   - 모양은 일봉과 같은 `compute_candle_shape`로 판정하되 기준값은 주봉 전용 `WEEKLY_SHAPE_PARAMS`를 넘긴다.
2. **장악형** - 이번 주 음봉이 직전 양봉 몸통을 덮으면 **숏**(`주봉 장악형 하락 - 숏 신호`), 이번 주 양봉이 직전 음봉 몸통을 덮으면 **롱**(`주봉 장악형 상승 - 롱 신호`).
   - 숏: 직전 몸통 >= `W_ENGULF_PREV_BODY_MIN_PCT`, 이번 주 음봉, 시가 >= 직전 종가 x `W_ENGULF_OPEN_TOLERANCE_RATIO`, 종가 <= 직전 시가 x `W_ENGULF_CLOSE_BREAK_RATIO`.
   - 롱은 대칭: 시가 <= 직전 종가 x (2 - OPEN_TOLERANCE), 종가 >= 직전 시가 x (2 - CLOSE_BREAK).
3. **매물소진** - 직전 주 변화율 >= `W_EXHAUSTION_PREV_MIN_PCT`, 이번 주 변화율 <= 직전 x `W_EXHAUSTION_CURRENT_MAX_RATIO`,
   이번 주 거래량 >= 직전 x `W_EXHAUSTION_VOLUME_MIN_RATIO`. 직전이 음봉이면 `주봉 매물소진 - 매수 신호`(롱), 양봉이면 `매도 신호`(숏). 이번 주 방향은 무관.
4. **EMA 20/50/200 터치** - 일봉 `sr_touch.py`와 같은 정의: 캔들이 EMA에 닿았을 때(저가 <= EMA <= 고가)만,
   이격률 = (종가 - EMA) / EMA x 100.
   - `|이격| <= W_EMA_TOUCH_MAX_PCT` 근접 -> 방향은 **시가** 위치(위면 `주봉 EMAxx 지지` 롱, 아래면 `저항 (거부)` 숏; 시가 == EMA면 직전 종가 위치, 그것도 같으면 무신호)
   - `|이격| > W_EMA_BREAKOUT_MIN_PCT` 돌파 -> 방향은 **종가** 위치(`상향 돌파` 롱 / `하향 이탈` 숏)
   - 그 사이는 회색지대: `주봉 EMAxx 근접했으나 회색지대라 신호 제외`(참고, 카운트 제외)

## 주봉 전용 상수 (`weekly_signals.py` 상단, 일봉 상수와 분리)

| 상수 | 값 | 근거 |
|---|---|---|
| `WEEKLY_SHAPE_PARAMS` | 일봉 모양 기준 사본: 도지 몸통 15%/25%(15~25%는 거래량 >= 직전 20주 평균 x 1.5), 망치형/역망치형 몸통 35% / 반대 꼬리 10% / 긴 꼬리 >= 몸통 x 2 | 일봉과 같은 값으로 시작 (바꿔도 일봉에 영향 없음) |
| `W_REVERSAL_PREV_BODY_MIN_PCT` | **3.0** | 모양 캔들 67주 중 40주(15.9%)가 신호 - 일봉 롱/숏 신호 비율(약 16.4%)에 맞춤 |
| `W_ENGULF_PREV_BODY_MIN_PCT` | **4.0** | 일봉 숏 장악형 비율(약 1.8%)에 맞춤 (숏 5, 롱 6) |
| `W_ENGULF_OPEN_TOLERANCE_RATIO` / `W_ENGULF_CLOSE_BREAK_RATIO` | 0.999 / 0.997 | 일봉 `bearish_engulfing.py` 값 |
| `W_EXHAUSTION_PREV_MIN_PCT` | **10.0** | 일봉 매물소진이 전체 캔들의 8%인데 주봉 10%에서 20건/251주 = 8% |
| `W_EXHAUSTION_CURRENT_MAX_RATIO` / `W_EXHAUSTION_VOLUME_MIN_RATIO` | 0.5 / 0.5 | 일봉 `exhaustion.py` 값 |
| `W_EMA_PERIODS` | (20, 50, 200) | |
| `W_EMA_TOUCH_MAX_PCT` / `W_EMA_BREAKOUT_MIN_PCT` | **0.65 / 2.0** | 일봉 EMA50/200 접촉 중 근접/회색/돌파 비율 7.0% / 22.0% / 71.0%에 맞춤 (주봉 EMA20/50/200 합산 6.7% / 21.2% / 72.1%) |

## 확정 시점의 신호 건수 (2022-01-03 ~ 2026-10-19 마감 주봉 251개)

| 신호 | 건수 |
|---|---|
| 반전 캔들 숏 / 롱 | 25 / 15 |
| 장악형 숏 / 롱 | 5 / 6 |
| 매물소진 (매수 9 / 매도 11) | 20 |
| EMA 근접 / 돌파 / 회색(참고) | 7 / 75 / 22 |

## API와 화면

- `GET /api/dashboard/weekly` - 일봉 `/api/dashboard`와 같은 응답 모양. 캔들(EMA9/20/50/200, RSI는 표시용), 주봉 신호(날짜 키 = 주 시작 월요일),
  일봉에서 그린 선/존(표시용), 다이버전스 마커는 항상 빈 목록.
- 화면 상단 바의 `1D / 1W`로 전환한다. 1W에서는 주봉 차트와 주봉 신호만 패널에 나오고, 선/존은 표시만(그리기/편집/삭제 불가),
  횡보 음영 토글은 숨겨진다.
