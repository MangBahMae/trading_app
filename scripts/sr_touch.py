"""
4-4. 이동평균(MA50/MA200) 터치 후 롱/숏 신호 (최종 확정 스펙)

기존 "지지/저항 성공/실패"(시가 기준 접근방향 판정) 틀은 폐기하고,
아래처럼 "터치 후 종가 위치로 롱/숏 신호"만 판정한다:

- MA50, MA200만 대상 (MA9, MA20은 대상 아님)
- 터치(닿음): 꼬리(저가 또는 고가)가 이평선을 실제로 침범하거나(크로스), 침범하지 않아도
  0.1% 이내로 근접하면 "닿음"으로 인정 (오차 통일: 0.1%)
    touch = (low <= MA <= high) OR |low-MA|/MA <= 0.1% OR |high-MA|/MA <= 0.1%
- 방향: 시가(접근방향)는 더 이상 쓰지 않고, 순수하게 종가 위치로만 결정
    - 터치된 캔들의 종가가 MA보다 0.1% 이상 위에서 마감 -> 롱 신호
    - 터치된 캔들의 종가가 MA보다 0.1% 이상 아래에서 마감 -> 숏 신호
    - 종가가 MA와 0.1% 이내로 붙어서 애매하면 -> 신호 없음 (터치는 있었지만 방향 불명확)
- 터치 자체가 없으면 신호 없음
- 반복 터치도 매번 독립된 별개 신호로 기록 (전날 상태에 의존하지 않고 그날 데이터만으로 판정)
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_ma_regime.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_sr_touch.parquet"

MA_TARGETS = ["MA50", "MA200"]
TOLERANCE_PCT = 0.001  # 0.1%


def compute_sr_touch(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    for ma_col in MA_TARGETS:
        touch_col = f"{ma_col}_touch"    # True/False
        signal_col = f"{ma_col}_signal"  # None / 'long' / 'short'

        touches = [False] * len(df)
        signals = [None] * len(df)

        for i in range(len(df)):
            ma_val = df[ma_col].iloc[i]
            if pd.isna(ma_val):
                continue

            low, high, close = df["low"].iloc[i], df["high"].iloc[i], df["close"].iloc[i]

            crossed = low <= ma_val <= high
            near_low = abs(low - ma_val) / ma_val <= TOLERANCE_PCT
            near_high = abs(high - ma_val) / ma_val <= TOLERANCE_PCT
            touched = crossed or near_low or near_high
            if not touched:
                continue

            touches[i] = True

            if close > ma_val * (1 + TOLERANCE_PCT):
                signals[i] = "long"
            elif close < ma_val * (1 - TOLERANCE_PCT):
                signals[i] = "short"
            # else: 종가가 MA에 너무 붙어있어 방향 불명확 -> 신호 없음(None 유지)

        df[touch_col] = touches
        df[signal_col] = signals

    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_sr_touch(df)

    for ma_col in MA_TARGETS:
        print(f"--- {ma_col} ---")
        touch_col, signal_col = f"{ma_col}_touch", f"{ma_col}_signal"
        n_touch = result[touch_col].sum()
        n_signal = result[signal_col].notna().sum()
        print(f"터치: {n_touch}개 (그 중 방향 불명확으로 신호 없음: {n_touch - n_signal}개)")
        print(result.loc[result[signal_col].notna(), signal_col].value_counts())
        print()

    result.to_parquet(OUT_PATH, index=False)
    print(f"저장 완료: {OUT_PATH}")
