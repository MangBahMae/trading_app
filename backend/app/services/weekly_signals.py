"""
주봉(1w) 신호 4종 - 일봉 모듈(pipeline/candle_patterns/sr_touch 등)은 건드리지 않는 별도 모듈.
규칙과 상수 목록은 docs/weekly_signals.md에도 정리돼 있다.

신호 (모두 주봉 마감 시점까지의 정보만 쓴다 - 미래 참조 없음. 화면/신호는 display_start 이후 주만):
  1. 반전 캔들: 직전 주가 양봉(몸통 >= W_REVERSAL_PREV_BODY_MIN_PCT)이고 이번 주가 도지/망치형/역망치형이면 숏,
     직전 주가 음봉(몸통 >= 같은 값)이면 롱. 직전 주 시가 == 종가(몸통 0)면 양봉도 음봉도 아니라 신호 없음.
     모양은 일봉 compute_candle_shape를 그대로 쓰되 기준값은 주봉 전용 WEEKLY_SHAPE_PARAMS를 넘긴다.
  2. 장악형: 이번 주 음봉이 직전 양봉 몸통을 덮으면 숏, 이번 주 양봉이 직전 음봉 몸통을 덮으면 롱.
     (일봉 bearish_engulfing.py와 같은 조건을 주봉 상수로 복사하고, 롱은 대칭으로 확장)
  3. 매물소진: 직전 주 변화율 >= W_EXHAUSTION_PREV_MIN_PCT, 이번 주 변화율 <= 직전의 절반, 이번 주 거래량 >=
     직전 주의 W_EXHAUSTION_VOLUME_MIN_RATIO. 직전 음봉이면 매수(롱), 양봉이면 매도(숏). 이번 주 방향은 무관.
  4. EMA20/50/200 지지·저항 터치: 일봉 sr_touch.py와 같은 정의(저가 <= EMA <= 고가인 캔들만, 이격률 = (종가-EMA)/EMA*100)로
     |이격| <= W_EMA_TOUCH_MAX_PCT 이면 근접 - 방향은 시가 위치(시가==EMA면 직전 종가, 그것도 같으면 무신호),
     |이격| > W_EMA_BREAKOUT_MIN_PCT 이면 돌파 - 방향은 종가 위치, 그 사이는 회색지대(참고, 신호 아님).
  장대봉/시세분출 무효는 주봉에 적용하지 않는다. 선/존은 쓰지 않는다. 신호의 source/near_zone/next_bar는 None(문구 앞 "주봉"으로 구분).

일봉 상수와 분리된 주봉 전용 상수는 이 파일 상단에 있다(일봉 값에서 출발한 값과, 주봉 분포에 맞춰 정한 값).
"""
import pandas as pd

import candle_patterns
from candle_patterns import PATTERN_LABEL_KR, ShapeParams
from signal_types import Signal

# --- 모양 판정 기준값: 주봉 전용 사본 (값은 일봉과 같게 시작 - 바꿔도 일봉에는 영향 없음)
WEEKLY_SHAPE_PARAMS = ShapeParams(
    body_max=0.15, body_ext_max=0.25, hammer_body_max=0.35, hammer_opposite_wick_max=0.10,
    hammer_wick_body_mult=2, volume_lookback=20, volume_ratio_min=1.5,   # 거래량 룩백 20은 "20주"
)

# --- 1. 반전 캔들
W_REVERSAL_PREV_BODY_MIN_PCT = 3.0    # 직전 주 몸통 변화율 |종가-시가|/시가*100 최소값(%)

# --- 2. 장악형 (일봉 bearish_engulfing.py 값에서 출발: 직전 몸통 최소만 주봉 분포에 맞춰 4%)
W_ENGULF_PREV_BODY_MIN_PCT = 4.0
W_ENGULF_OPEN_TOLERANCE_RATIO = 0.999   # 숏: 이번 주 시가 >= 직전 종가 x 0.999 (롱은 대칭: <= 직전 종가 x 1.001)
W_ENGULF_CLOSE_BREAK_RATIO = 0.997      # 숏: 이번 주 종가 <= 직전 시가 x 0.997 (롱은 대칭: >= 직전 시가 x 1.003)

# --- 3. 매물소진 (직전 큰 캔들 기준만 주봉 분포에 맞춰 10%)
W_EXHAUSTION_PREV_MIN_PCT = 10.0
W_EXHAUSTION_CURRENT_MAX_RATIO = 0.5    # 이번 주 변화율 <= 직전 변화율 x 이 값
W_EXHAUSTION_VOLUME_MIN_RATIO = 0.5     # 이번 주 거래량 >= 직전 주 거래량 x 이 값

# --- 4. EMA 터치 (일봉 EMA50/200의 근접/회색/돌파 비율 7% / 22% / 71%에 맞춘 값)
W_EMA_PERIODS = (20, 50, 200)
W_EMA_TOUCH_MAX_PCT = 0.65       # 근접: |이격률| <= 이 값(%)
W_EMA_BREAKOUT_MIN_PCT = 2.0     # 돌파: |이격률| > 이 값(%)


def _label(shape: str) -> str:
    return PATTERN_LABEL_KR[shape]


def compute_weekly_signals(df: pd.DataFrame, display_start: str | pd.Timestamp | None = None) -> dict:
    """df: open_time/open/high/low/close/volume 컬럼과 EMA{20,50,200}(워밍업 포함 전체 이력으로 계산한 값)을 가진 주봉
    데이터프레임(0-based 연속 인덱스). 반환: {row_index: [Signal, ...]} - display_start 이전 주는 신호를 내지 않는다
    (직전 주 정보로는 그 이전 데이터도 쓴다)."""
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}
    start = 1
    if display_start is not None:
        ts = pd.Timestamp(display_start)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
        later = df.index[df["open_time"] >= ts]
        start = max(1, int(later[0]) if len(later) else n)

    o, h, lo, c, v = (df[col].tolist() for col in ("open", "high", "low", "close", "volume"))
    shapes = candle_patterns.compute_candle_shape(df, WEEKLY_SHAPE_PARAMS)["shape"].tolist()

    def pct(i: int) -> float:
        """몸통 변화율(부호 있음, %): (종가-시가)/시가*100 - 양봉 +, 음봉 -."""
        return (c[i] - o[i]) / o[i] * 100 if o[i] else 0.0

    for i in range(start, n):
        prev = i - 1
        prev_pct = pct(prev)

        # 1) 반전 캔들 (직전 몸통 0이면 양봉도 음봉도 아니라 신호 없음)
        if shapes[i] is not None:
            label = _label(shapes[i])
            if prev_pct > 0 and prev_pct >= W_REVERSAL_PREV_BODY_MIN_PCT:
                signals[i].append(Signal(f"주봉 {label} 반전 - 숏 후보", "short"))
            elif prev_pct < 0 and -prev_pct >= W_REVERSAL_PREV_BODY_MIN_PCT:
                signals[i].append(Signal(f"주봉 {label} 반전 - 롱 후보", "long"))

        # 2) 장악형
        if prev_pct >= W_ENGULF_PREV_BODY_MIN_PCT and c[i] < o[i] \
                and o[i] >= c[prev] * W_ENGULF_OPEN_TOLERANCE_RATIO and c[i] <= o[prev] * W_ENGULF_CLOSE_BREAK_RATIO:
            signals[i].append(Signal("주봉 장악형 하락 - 숏 신호", "short"))
        if -prev_pct >= W_ENGULF_PREV_BODY_MIN_PCT and c[i] > o[i] \
                and o[i] <= c[prev] * (2 - W_ENGULF_OPEN_TOLERANCE_RATIO) \
                and c[i] >= o[prev] * (2 - W_ENGULF_CLOSE_BREAK_RATIO):
            signals[i].append(Signal("주봉 장악형 상승 - 롱 신호", "long"))

        # 3) 매물소진 (방향은 직전 캔들 기준, 이번 주 방향은 무관)
        cur_change = abs(pct(i))
        prev_change = abs(prev_pct)
        if prev_change >= W_EXHAUSTION_PREV_MIN_PCT and cur_change <= prev_change * W_EXHAUSTION_CURRENT_MAX_RATIO \
                and v[i] >= v[prev] * W_EXHAUSTION_VOLUME_MIN_RATIO:
            if prev_pct < 0:
                signals[i].append(Signal("주봉 매물소진 - 매수 신호", "long"))
            elif prev_pct > 0:
                signals[i].append(Signal("주봉 매물소진 - 매도 신호", "short"))

        # 4) EMA 터치 / 돌파
        for period in W_EMA_PERIODS:
            ema = df[f"EMA{period}"].iloc[i]
            if pd.isna(ema) or not (lo[i] <= ema <= h[i]):
                continue
            name = f"EMA{period}"
            deviation = (c[i] - ema) / ema * 100
            if abs(deviation) <= W_EMA_TOUCH_MAX_PCT:
                if o[i] > ema:
                    signals[i].append(Signal(f"주봉 {name} 지지", "long"))
                elif o[i] < ema:
                    signals[i].append(Signal(f"주봉 {name} 저항 (거부)", "short"))
                elif c[prev] > ema:       # 시가 == EMA: 직전 종가가 있던 쪽, 그것도 같으면 무신호
                    signals[i].append(Signal(f"주봉 {name} 지지", "long"))
                elif c[prev] < ema:
                    signals[i].append(Signal(f"주봉 {name} 저항 (거부)", "short"))
            elif abs(deviation) > W_EMA_BREAKOUT_MIN_PCT:
                if deviation > 0:
                    signals[i].append(Signal(f"주봉 {name} 상향 돌파", "long"))
                else:
                    signals[i].append(Signal(f"주봉 {name} 하향 이탈", "short"))
            else:
                signals[i].append(Signal(f"주봉 {name} 근접했으나 회색지대라 신호 제외", "reference"))

    return signals
