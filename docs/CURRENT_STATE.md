# 현재 구현 상태 (자동 생성 문서)

작성 시점: 2026-09-13, 기준 커밋 `627d623` (main, working tree clean)
대조한 기획 문서: `docs/트레이딩앱 기획.docx` (v3, 2026-08-30 세션 확정본)

이 문서는 기획 문서를 대체하지 않는다. 기획 문서는 "의도"를, 이 문서는 "지금 코드가
실제로 무엇을 하는가"를 기록한다. 코드가 바뀌면 이 문서도 다시 생성해야 최신 상태를
유지할 수 있다.

---

## 1. 구현된 신호 전체 목록

### 1-1. `scripts/pipeline.py`에 등록된 신호 (12개 + 필터 1개)

`build_signals_by_date()`가 만드는 `{row_index: [Signal(text, direction)]}` 구조에
들어가는 것만 정리. `direction`이 `long`/`short`면 통합 탭 카운트에 포함되고,
`reference`면 표시만 되고 카운트에서 빠진다.

| # | 신호명 | 파일 | 유형 | 방향 | 카운트 |
|---|---|---|---|---|---|
| 1 | 매물소진 - 매수 | `exhaustion.py` | trigger | long | O |
| 2 | 매물소진 - 매도 | `exhaustion.py` | trigger | short | O |
| 3 | 도지캔들 | `doji.py` | trigger | reference | X |
| 4 | 정배열 진입/유지 | `ma_regime.py` | trigger+state | long | O |
| 5 | 역배열 진입/유지 | `ma_regime.py` | trigger+state | short | O |
| 6 | EMA50 터치 - 롱/숏 | `sr_touch.py` | trigger | long/short | O |
| 7 | EMA200 터치 - 롱/숏 | `sr_touch.py` | trigger | long/short | O |
| 8 | RSI 다이버전스 4종 | `rsi_swings.py`+`divergence.py` | trigger+state | long(2)/short(2) | O |
| 9 | 다우이론 HH/LH/HL/LL | `dow_theory.py` | state (표시전용) | reference | X |
| 10 | RSI 과매도 (≤25) | `rsi_overbought_oversold.py` | trigger+state | long | O |
| 11 | RSI 과매수 (≥80) | `rsi_overbought_oversold.py` | state (표시전용) | reference | X |
| 12 | 고점 도지 (거부 캔들) `doji_at_high` | `doji_spinning_top_at_high.py` | trigger | short | O (시세분출 시 무효화) |
| 13 | 고점 스피닝탑 (거부 캔들) `spinning_top_at_high` | `doji_spinning_top_at_high.py` | trigger | short | O (시세분출 시 무효화) |
| 14 | 장악형 하락 `bearish_engulfing` | `bearish_engulfing.py` | trigger | short | O (시세분출 시 무효화) |

12/13/14는 `volatility_expansion.py`가 판정한 "시세 분출" 구간이면 `pipeline.py`의
`_emit_bearish_signal()`에서 발생이 억제된다 (신호 자체가 생성되지 않음). 억제된
케이스는 `invalidated_log`라는 옵션 인자를 넘겨야만 기록되고, **현재 `app.py`는 이
인자를 넘기지 않으므로 대시보드 UI에는 억제 이력이 전혀 노출되지 않는다** (검증은
`scripts/analyze_volatility_expansion_filter.py`로만 가능). 1-3에서 상세 설명.

### 1-2. 파이프라인 밖에서 계산되는 신호 (`app.py`가 직접 호출, 캐시 없음)

사용자가 그린 수동 선이나 그 선에 의존하는 조건이라 `st.cache_data`로 캐시된
`load_dashboard_data()` 경로에 못 들어가고, 렌더링마다 새로 계산된다.

| 신호명 | 파일 | 유형 | 방향 |
|---|---|---|---|
| 수평선 근접 - 지지/저항 시험 | `manual_lines.py` `compute_manual_line_signals` | 근접해있는 동안 매 캔들 반복 (trigger/state 이분법 미적용, 레거시 방식) | long(지지)/short(저항) |
| 추세선 근접 | `manual_lines.py` `compute_manual_line_signals` | 위와 동일, 항상 short 고정 | short |
| 수평선 돌파 진입/유지 | `manual_lines.py` `compute_manual_line_state_signals` | trigger+state | long(상향)/short(하향) |
| 유효 도지 (지지 근처+거래량 증가) | `doji.py` `compute_valid_doji_long` | trigger | long 전용 (숏 대칭 미구현) |

### 1-3. 판정 조건 (의사코드) + 하드코딩 상수

#### 매물소진 (`exhaustion.py`)
```
prev_pct = (close[t-1] - open[t-1]) / open[t-1] * 100   # 부호 있음
curr_pct = (close[t]   - open[t])   / open[t]   * 100   # 부호 있음
if |prev_pct| < 3.5: skip
if |curr_pct| > |prev_pct| / 2: skip
if volume[t] < volume[t-1] * 0.5: skip
signal = "buy"  if prev_close < prev_open   # 직전 음봉
       = "sell" if prev_close > prev_open   # 직전 양봉
```
상수: `PREV_MIN_PCT = 3.5` (`exhaustion.py:24`), `VOLUME_MIN_RATIO = 0.5` (`exhaustion.py:25`)

#### 도지캔들 (`doji.py`)
```
doji_ratio = |close[t] - open[t]| / (high[t] - low[t])   # range=0이면 0으로 정의
is_doji = doji_ratio <= 0.10
```
상수: `DOJI_THRESHOLD = 0.10` (`doji.py:27`)

유효 도지(롱, `compute_valid_doji_long`):
```
if not is_doji[t]: skip
near_swing_low = _near(low[t], high[t], 최근 확정 스윙저점)   # ±0.1%
near_ema = MA50_touch[t] or MA200_touch[t]
near_line = 사용자가 그은 수평선 중 direction=="long"인 근접 신호가 그날 있음
if not (near_swing_low or near_ema or near_line): skip
if volume[t] <= volume[t-1] * 1.0: skip
-> Signal("유효한 도지 (지지 근처, 거래량 증가)", "long")
```
상수: `PROXIMITY_PCT = 0.001` (`doji.py:28`), `VOLUME_INCREASE_RATIO = 1.0` (`doji.py:29`)
숏 대칭 버전은 없음 (코드 주석에 "추후 대칭 적용" 명시).

#### 이동평균 배열 (`ma_regime.py`)
```
MA9/20/50/200 = EMA(close, span=9/20/50/200, adjust=False, min_periods=동일)
bullish = MA9 > MA20 > MA50   # MA200 불관여
bearish = MA9 < MA20 < MA50
regime  = "bullish" | "bearish"
        | "convergence" if bullish/bearish 둘 다 아니고 |MA50-MA20|/close <= 1.5%
                            (또는 |MA50-MA200|/close <= 1.5%, MA200 있을 때만)
        | "mixed" (그 외)

bullish_trigger[t] = bullish[t] and not bullish[t-1]   # 새로 완성된 캔들만 True
bullish_state[t]   = bullish[t]                        # 유지되는 동안 True
(bearish도 대칭)

# 의심 스택 - 그날 값만으로 매일 독립 계산 (전날 값에 의존하지 않음)
bullish_suspicion = int((MA9-close)/MA9 >= 0.5%) + int(close < MA20)   # 0~2
bearish_suspicion = int(close > MA50)                                  # 0~1
```
상수: `CONVERGENCE_PCT = 0.015` (`ma_regime.py:29`), `BULLISH_SUSPICION_A_PCT = 0.005` (`ma_regime.py:30`)

#### EMA50/EMA200 터치 (`sr_touch.py`, MA50/MA200 각각 독립 판정)
```
touched = low[t] <= EMA <= high[t]
if not touched: 무신호
deviation = (close[t] - EMA) / EMA * 100   # 부호 있음
if |deviation| <= 0.1:      # touch_reject
    signal = "short" if close>open else "long" if close<open else None(도지)
elif |deviation| > 0.5:     # breakout
    signal = "long" if deviation>0.5 else "short"
else:                       # gray_zone (0.1~0.5%)
    무신호 (reference로 "회색지대" 표시)
```
상수: `TOUCH_MAX_PCT = 0.1`, `BREAKOUT_MIN_PCT = 0.5`, `MA_TARGETS = ["MA50","MA200"]` (`sr_touch.py:33-35`)

#### RSI 값 (`rsi.py`)
```
Wilder 14기간: 첫 평균은 14개 단순평균으로 시드, 이후 avg = (avg_prev*13 + 현재)/14
avg_loss==0 and avg_gain==0 -> RSI=50
avg_loss==0                 -> RSI=100
그 외                        -> RSI = 100 - 100/(1+avg_gain/avg_loss)
```
상수: `PERIOD = 14` (`rsi.py:20`)

#### RSI 과매도/과매수 (`rsi_overbought_oversold.py`)
```
oversold_state[t]  = RSI[t] <= 25;  oversold_trigger = 새로 진입한 캔들
overbought(rsi_sell)[t] = RSI[t] >= 80  (표시 전용, state/trigger 구분 없이 매 캔들 재계산)
```
상수: `OVERSOLD = 25`, `OVERBOUGHT = 80` (`rsi_overbought_oversold.py:18-19`)

#### RSI 다이버전스 (`rsi_swings.py` + `divergence.py`)
```
# 1) RSI 자체의 피벗(rsi_swings.py) - 좌우 5봉 모두보다 크면 고점, 작으면 저점
#    확정 시점 = i+5 (우측 5봉 마감 후, look-ahead 방지)

# 2) 직전 피벗과 이번 피벗, 딱 1쌍만 비교
gap = curr_pivot_idx - prev_pivot_idx
if not (5 <= gap <= 60): 제외 (excluded_by_gap)

정상 약세 = 가격고가 HH and RSI고점 LH
은닉 약세 = 가격고가 LH and RSI고점 HH
정상 강세 = 가격저가 LL and RSI저점 HL
은닉 강세 = 가격저가 HL and RSI저점 LL
동률(가격 or RSI가 직전과 정확히 같음) -> 다이버전스 아님

# state 해제 (둘 중 먼저 오는 것)
① 종가가 무효화 가격(다이버전스를 만든 pivot의 저가/고가) 이탈
② 반대 방향 RSI 피벗이 "확정"됨 (그 피벗의 i+5 시점)
```
상수: `N(pivot lookback/lookahead) = 5` (`rsi_swings.py:22`), `GAP_MIN=5`, `GAP_MAX=60` (`divergence.py:38-39`)

#### 다우이론 (`dow_theory.py`, `swing_points.py`)
```
스윙하이/로우: 중심 캔들이 좌우 N=2봉의 고/저보다 엄격히 크거나/작으면 확정
             확정 시점 = i+2 (우측 2봉 마감 후)
새 스윙하이 확정 시 직전 스윙하이와 비교 -> HH(상승)/LH(하락)
새 스윙로우 확정 시 직전 스윙로우와 비교 -> HL(상승)/LL(하락)
라벨->방향: HH,HL -> long / LH,LL -> short
동률(직전 스윙과 가격이 정확히 같음)이면 label=None (스펙에 없는 케이스, 실행 중 실제 발생 확인)
```
상수: `swing_points.N = 2` (`swing_points.py:15`)

#### 고점 도지 / 고점 스피닝탑 (`doji_spinning_top_at_high.py`) — 이번 세션 신규
```
prev_body_pct = (close[t-1] - open[t-1]) / open[t-1] * 100   # 부호 있음
if prev_body_pct < 3.5: skip
if high[t] == low[t]: skip                                    # 0으로 나누기 방지
body_ratio = |close[t]-open[t]| / (high[t]-low[t]) * 100
doji_at_high         = body_ratio <= 15
spinning_top_at_high = 15 < body_ratio <= 40
```
상수: `PREV_BODY_MIN_PCT=3.5`, `DOJI_BODY_MAX_PCT=15`, `SPINNING_TOP_BODY_MAX_PCT=40`

#### 장악형 하락 (`bearish_engulfing.py`) — 이번 세션 신규
```
prev_body_pct = (close[t-1]-open[t-1])/open[t-1]*100
if prev_body_pct < 1.5: skip
if close[t] >= open[t]: skip                       # 당일 음봉이어야 함
if open[t]  < close[t-1] * 0.999: skip              # 위쪽 장악
if close[t] > open[t-1] * 0.997: skip               # 아래쪽 장악
-> bearish_engulfing
```
상수: `PREV_BODY_MIN_PCT=1.5`, `OPEN_TOLERANCE_RATIO=0.999`, `CLOSE_BREAK_RATIO=0.997`

#### 시세 분출 무효화 필터 (`volatility_expansion.py`) — 이번 세션 신규
```
for N in (2,3,4):
    window = [t-N, t-1]
    if not all(양봉 in window): continue
    cum_pct = (close[t-1] - open[t-N]) / open[t-N] * 100
    if cum_pct / N >= 4.0: is_volatility_expansion[t] = True  (OR 판정)
```
상수: `MIN_WINDOW=2`, `MAX_WINDOW=4`, `CUM_PCT_PER_N_MIN=4.0`
연결: doji_at_high / spinning_top_at_high / bearish_engulfing이 이 구간에서 발생하면
`pipeline.py`가 신호 생성을 억제.

#### 수동 라인 (`manual_lines.py`)
```
근접 판정: |low~high 범위와 level 사이 거리| / level <= 0.1%
수평선: 종가>=level -> "지지 시험(long)", 종가<level -> "저항 시험(short)"
추세선: 두 등록점을 선형 외삽한 그날 가격 기준, 항상 "매도 후보(short)" 고정
```
```
수평선 돌파 state: 종가가 level을 새로 넘으면 trigger, 해제는
  ① 반대로 넘어 마감  ② 저가~고가가 다음 레벨선에 걸침
  둘 다 없으면 ongoing (state 계속 유지)
```
상수: `PROXIMITY_PCT = 0.001` (`manual_lines.py:21`)

---

## 2. 기획 문서(docx) vs 실제 코드 — 어긋나는 부분

### 2-1. 구현됐는데 문서에 전혀 없는 것

- **`doji_at_high` / `spinning_top_at_high` / `bearish_engulfing` / `volatility_expansion` 무효화 필터** — 이번 세션에서 새로 만든 4개 모듈. `트레이딩앱 기획.docx`에는 이 개념 자체(직전 급등 후 거부 캔들, 장악형, 시세 분출) 및 관련 임계값이 전혀 없다. 기획 문서 업데이트가 필요.
- **`ma_regime.py`의 `convergence`(수렴)/`mixed`(혼조) 레짐** — docx 전체를 통틀어 "수렴"·"혼조"라는 단어가 한 번도 안 나온다. `CONVERGENCE_PCT=1.5%` 임계값도 문서에 없음. docx는 "정배열/역배열" 두 상태만 다룬다.
- **역배열 의심 스택(`bearish_suspicion`, 종가>MA50)** — docx 부록은 "정배열 의심 스택"만 명시(EMA9 0.5%/EMA20). 대칭되는 역배열 의심 항목은 문서 어디에도 없는데 코드에는 구현돼 있다.
- **EMA 터치의 3구간(touch_reject/breakout/gray_zone, 0.1%/0.5%) 정밀 판정** — docx 3-1 #4/3-2 #2는 "저가가 터치, 종가가 위/아래 마감"이라는 한 줄짜리 단순 규칙만 적어놨다. 실제 `sr_touch.py`는 이격률 기반 3단계 분류를 쓰는데, 이 설계 자체가 문서에 없다 (파일 자체 docstring엔 "재설계 확정 스펙"이라고만 돼 있어 사후 문서화가 안 된 것으로 보임).

### 2-2. 문서에는 있는데 구현 안 된 것

이번 단계에서 문서가 스스로 "미구현/보류 확정"이라고 표시한 항목들은 정상이다 (라운딩 바텀·라운딩 탑, 주봉/월봉 도지, 쌍고점/쌍바텀, 숏 조건 3번 거래량). 아래는 문서가 "해결했다" 또는 "적용 예정"이라고 썼는데 실제로는 안 고쳐진 것들:

- **추세선 방향 사용자 선택 (3-5)** — docx: "[v3] 미결 해소: 추세선=항상 매도 고정 문제 → 수평선처럼 사용자가 방향을 선택하는 방식으로 통일" 이라고 "해결됨"으로 적어놨다. 그러나 `manual_lines.py:193`은 여전히 `direction_label, direction = "매도 후보", "short"`로 하드코딩돼 있고, `lines_store.py`의 SQLite 스키마에도 방향을 저장할 컬럼이 없다. **문서는 해결됐다고 하는데 코드는 안 고쳐졌다.**
- **도지 필터링 숏 대칭 (3-1-2)** — 문서는 "롱 조건에 필터링 조건 추가 예정"이라고만 썼지만, 실제 `doji.py`의 `compute_valid_doji_long`은 이름부터 롱 전용이고 숏 대칭 버전은 없음 (코드 주석엔 "롱만 우선 구현, 숏은 추후 대칭 적용" 명시).
- **추세선 돌파/이탈 이벤트 판정 (미결 사항 #13)** — 문서 스스로 미결로 인지하고 있는 항목. 실제로 `compute_manual_line_state_signals`는 `line_type != "horizontal"`이면 그냥 skip해서 추세선은 근접 판정(`compute_manual_line_signals`)만 있고 state 기반 판정 자체가 없다.

### 2-3. 조건/임계값 또는 서술이 문서와 다른 것

- **RSI 다이버전스 `opposite_pivot` 해제 조건의 자기모순** — docx 3-3 본문: "검토했으나 채택하지 않은 대안: ... 반대 방향 다이버전스 발생 시 교체. 향후 실사용 후 OR 조건으로 추가 검토 가능"이라고 **미채택**으로 명시했다. 그런데 `divergence.py`의 `compute_divergence_state()`는 이미 "반대 방향 RSI pivot 확정 시 자동 해제"를 조건 ②로 구현해서 실제 신호 계산에 쓰고 있다 (본문과 모순). 같은 문서의 미결 사항 #14는 이 기능을 "이번에 추가한 opposite_pivot 해제 조건"이라고 이미 기정사실로 서술하고 있어, **문서 본문(3-3)과 문서 뒤쪽 미결 사항(#14)이 서로 어긋난 채로 남아있다.** 코드는 미결 사항 #14 쪽(구현됨)을 따르고 있다.
- **정배열 의심 스택 "누적"이라는 표현** — docx 부록: "종가가 MA9 아래 또는 MA20 아래로 마감 시 일별 플래그 **누적**". "누적"이 여러 날에 걸친 카운트를 뜻하는 것으로 읽힐 수 있으나, `ma_regime.py` 자체 docstring은 "그날 종가만으로 그날 상태를 독립적으로 계산, **전날 상태에 의존하지 않음**"이라고 명시하고 실제로도 매일 0~2 사이 값으로 새로 계산될 뿐 날짜 간 누적은 없다. 문서 표현이 모호해서 오해 소지가 있다.
- **다우이론 동률 처리** — docx 4-2 규칙에는 "직전 스윙과 정확히 같은 가격"일 때 어떻게 처리하라는 규정이 없다. `dow_theory.py`는 이 경우를 만나면 `label=None` 처리하며 콘솔에 "스펙에 정의되지 않은 동률 발견"이라는 경고를 낸다 (BTCUSDT 1d 실데이터에서 실제로 1건 발생 중 - index 411 vs 416). 코드가 문서에 없는 엣지케이스를 임의로 결정해서 처리하고 있다.

---

## 3. TODO / 미완성으로 보이는 부분

리터럴 `TODO`/`FIXME` 주석은 코드 전체에 하나도 없다 (이 프로젝트는 "미결"/"보류"/"추후" 같은 한국어 표현으로 미완성 항목을 표시하는 스타일). 발견된 것들:

- **`scripts/pipeline.py`, `scripts/doji.py`**: 위 2-2에서 다룬 "유효 도지 롱만 구현, 숏은 추후" — 코드 주석에 명시.
- **`scripts/manual_lines.py`**: `compute_manual_line_state_signals`의 docstring에 "추세선은 아직 돌파/이탈 이벤트 판정 로직 자체가 없어서 범위 밖 (근접 판정만 존재, 미결 사항 14번 참고)"이라고 자기 한계를 명시. *(문서 번호는 실제로는 미결 사항 #13을 가리켜야 하는데 코드 주석엔 "14번"으로 잘못 적혀 있음 — 사소한 리모날 오기.)*
- **`scripts/data_fetcher.py`**: 자체적으로 TODO는 아니지만, 룩어헤드 방지를 위해 "아직 마감 안 된 캔들은 절대 포함 안 함"이라는 방어 로직이 주석과 함께 있고 이건 완성된 안전장치임 (문제 아님, 참고용으로 기재).
- **`scripts/_disabled/exhaustion_v2_experimental.py`** — 매물소진 조건을 "직전 캔들 1개 의존 → 노이즈 취약" 문제를 해결하려고 만든 실험 버전(최근 20봉 상대 레인지/상대 거래량 기반). 원래 스펙(0.7/1.5)로는 신호가 0개라 0.9/1.1로 완화했었다는 기록이 파일 안에 남아있고, 활성 파이프라인에서 빠진 채(`_disabled/`) 방치돼 있다. `docs` 3-1-1의 "검토 방향 미확정" 서술과 정확히 대응하는 미완성 시도.
- **새 신호 3종(`doji_spinning_top_at_high.py`, `bearish_engulfing.py`, `volatility_expansion.py`)에는 시각 검증(`plot_*.py`) 스크립트가 없다** — 기존 신호들(도지, 매물소진, 다우이론, MA 터치, MA 레짐, RSI류, 스윙)은 전부 `scripts/plot_*.py` 짝이 있어 `output/charts/`에 눈으로 확인할 수 있는 PNG를 남기는데, 이번에 추가된 3개는 `__main__` 블록의 카운트 출력만 있고 차트 시각화가 없다. 프로젝트 관례상 미완성 상태로 볼 수 있음.
- **시세 분출 무효화 이력이 UI에 노출 안 됨** — `pipeline.build_signals_by_date()`의 `invalidated_log` 인자는 `app.py`에서 전혀 넘겨지지 않는다. 즉 실사용 중 "오늘 뜨려던 숏 신호가 시세 분출 때문에 억제됐다"는 사실을 대시보드에서 확인할 방법이 없고, `scripts/analyze_volatility_expansion_filter.py`를 따로 실행해야만 알 수 있다.
- **`docs/` 폴더에 마크다운 기획 문서가 없다** — 유일한 기획 자료가 `.docx` 바이너리 하나뿐이라, 이 문서(`CURRENT_STATE.md`)를 만들 때도 zip 추출 스크립트를 임시로 짜서 읽어야 했다. 향후 갱신 편의를 위해 `.md` 버전 병행 관리를 고려할 만하다 (이번 요청 범위 밖이라 원본은 손대지 않음).

---

## 4. 최근 10일간 커밋 로그 요약 (2026-09-03 ~ 2026-09-13)

프로젝트 전체 히스토리가 5개 커밋뿐이라, 10일 기준에 걸리는 건 아래 2개다.

| 날짜 | 커밋 | 요약 |
|---|---|---|
| 2026-09-10 | `627d623` | 고점 거부 캔들(도지/스피닝탑), 장악형 하락 신호 3종 추가 — `doji_spinning_top_at_high.py`, `bearish_engulfing.py` 신규, `pipeline.py`에 10~12번 신호로 등록 |
| 2026-09-05 | `465b322` | 역배열 trigger/state, EMA 터치/돌파 로직 재구현, 유효 도지 필터, 차트 UI 버그 수정 |

10일 범위 밖이지만 전체 맥락 참고용으로 남기는 이전 히스토리:

| 날짜 | 커밋 | 요약 |
|---|---|---|
| 2026-09-01 | `9928173` | trigger/state 구조 5개 조건 적용, Signal 태깅 통합, 3탭 UI, 다이버전스 중첩 해제 조건 추가 |
| 2026-08-31 | `73690a5` | Feature 1 통합 신호 대시보드 + 수동 라인(기능 1-A) 구현 |
| 2026-08-27 | `dd5dd21` | 4-1~4-6, 4-8 신호 로직 구현 및 검증 완료 (4-7 거래량 급증은 보류) |

(이번 대화에서 `627d623` 이후 추가로 작업한 `volatility_expansion.py`/`analyze_volatility_expansion_filter.py`와 이 문서 자체는 아직 커밋되지 않은 워킹트리 변경 사항이다.)
