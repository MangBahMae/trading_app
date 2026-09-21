"""
임시 진단 스크립트 - sr_touch.py는 전혀 건드리지 않음, 결과만 검증.

전체 기간(2022-01-01~) EMA50/EMA200 터치·돌파 신호 5개 항목 검증.
모든 값은 sr_touch.py를 그대로 호출한 결과 컬럼(touch/case/deviation/signal)과,
raw OHLC로부터 독립적으로 재계산한 값을 대조하는 방식으로 확인한다.
"""
import inspect

import pandas as pd

import ma_regime
import sr_touch
from data_fetcher import ensure_fresh_data

START_DATE = pd.Timestamp("2022-01-01", tz="UTC")
TOUCH_MAX = sr_touch.TOUCH_MAX_PCT
BREAKOUT_MIN = sr_touch.BREAKOUT_MIN_PCT

df = ensure_fresh_data().reset_index(drop=True)
df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

regime_df = ma_regime.compute_ma_regime(df)
result = sr_touch.compute_sr_touch(regime_df)

print(f"기간: {df['open_time'].iloc[0].date()} ~ {df['open_time'].iloc[-1].date()}  (캔들 {len(df)}개)")
print("=" * 70)

for ma_col in sr_touch.MA_TARGETS:
    touch_col = f"{ma_col}_touch"
    case_col = f"{ma_col}_case"
    dev_col = f"{ma_col}_deviation"
    sig_col = f"{ma_col}_signal"

    print(f"\n########## {ma_col} ##########")

    fired = result[result[sig_col].notna()]
    print(f"발화(신호 있음) 총 {len(fired)}건")

    # ---------------- 1. deviation 구간별 분류 ----------------
    abs_dev = fired[dev_col].abs()
    bin_touch = (abs_dev <= TOUCH_MAX).sum()
    bin_gray = ((abs_dev > TOUCH_MAX) & (abs_dev <= BREAKOUT_MIN)).sum()
    bin_breakout = (abs_dev > BREAKOUT_MIN).sum()
    print(f"\n[1] 발화 신호의 deviation 구간별 분류")
    print(f"    터치(|dev|<=0.1%): {bin_touch}건")
    print(f"    회색지대(0.1%<|dev|<=0.5%): {bin_gray}건  <- 0이어야 정상")
    print(f"    돌파(|dev|>0.5%): {bin_breakout}건")

    # ---------------- 2. 전제조건 위반 ----------------
    viol = 0
    for i in fired.index:
        low, high = df["low"].iloc[i], df["high"].iloc[i]
        ma_val = regime_df[ma_col].iloc[i]
        if not (low <= ma_val <= high):
            viol += 1
    print(f"\n[2] 전제조건(low<=EMA<=high) 위반 발화: {viol}건  <- 0이어야 정상")

    # ---------------- 3. 방향 판정 정합성 ----------------
    touch_rows = fired[fired[case_col] == "touch_reject"]
    reverse_touch = 0
    doji_fired = 0
    for i in touch_rows.index:
        open_, close = df["open"].iloc[i], df["close"].iloc[i]
        sig = result[sig_col].iloc[i]
        if close > open_ and sig == "long":
            reverse_touch += 1
        elif close < open_ and sig == "short":
            reverse_touch += 1
        elif close == open_:
            doji_fired += 1

    # 터치 구간 전체(신호 유무 무관)에서 도지 캔들 개수 vs 그중 발화 건수
    all_touch_bin = result[(result[touch_col]) & (result[dev_col].abs() <= TOUCH_MAX)]
    doji_total_in_touch_bin = (df.loc[all_touch_bin.index, "close"] == df.loc[all_touch_bin.index, "open"]).sum()

    breakout_rows = fired[fired[case_col] == "breakout"]
    reverse_breakout = 0
    for i in breakout_rows.index:
        close = df["close"].iloc[i]
        ma_val = regime_df[ma_col].iloc[i]
        sig = result[sig_col].iloc[i]
        if close > ma_val and sig == "short":
            reverse_breakout += 1
        elif close < ma_val and sig == "long":
            reverse_breakout += 1

    print(f"\n[3] 방향 판정 정합성")
    print(f"    터치구간 역방향(양봉인데 long / 음봉인데 short): {reverse_touch}건  <- 0이어야 정상")
    print(f"    돌파구간 역방향(종가>EMA인데 short / 종가<EMA인데 long): {reverse_breakout}건  <- 0이어야 정상")
    print(f"    터치구간 도지 판정 기준: close == open (오차 허용 없음, 코드 그대로)")
    print(f"    터치구간 내 도지 캔들 총수: {doji_total_in_touch_bin}건, 그중 신호 발화: {doji_fired}건  <- 0이어야 정상")

    # ---------------- 4. 경계값 처리 ----------------
    print(f"\n[4] 경계값(|dev|==0.1% 또는 ==0.5%) 처리")
    touched_all = result[result[touch_col]]
    dev_abs_all = touched_all[dev_col].abs()
    exact_01 = touched_all[dev_abs_all == TOUCH_MAX]
    exact_05 = touched_all[dev_abs_all == BREAKOUT_MIN]
    print(f"    |dev| 정확히 0.1%인 캔들: {len(exact_01)}건", end="")
    if len(exact_01):
        print(f" -> case={exact_01[case_col].unique().tolist()}")
    else:
        print(" (실데이터엔 없음 - 코드 로직상 <= 라 touch_reject로 분류되게 되어있음)")
    print(f"    |dev| 정확히 0.5%인 캔들: {len(exact_05)}건", end="")
    if len(exact_05):
        print(f" -> case={exact_05[case_col].unique().tolist()}")
    else:
        print(" (실데이터엔 없음 - 코드 로직상 > 가 아니라 gray_zone으로 분류되게 되어있음)")

print("\n" + "=" * 70)
print("[5] EMA50/EMA200 계산 방식 확인 (ma_regime.py)")
src = inspect.getsource(ma_regime.compute_ma_regime)
has_ewm = ".ewm(" in src
has_rolling = ".rolling(" in src
print(f"    .ewm(...) 사용: {has_ewm}")
print(f"    .rolling(...) 사용: {has_rolling}")
for line in src.splitlines():
    if "MA50" in line or "MA200" in line:
        print(f"    -> {line.strip()}")
