"""
장악형 하락 (bearish engulfing)

직전 양봉의 상승분을 당일 음봉이 전부 되돌리는 상황을 잡는다. 매도(숏) 고려 신호.

조건 (모두 만족):
1. 직전 캔들(t-1)이 양봉이고 몸통이 1.5% 이상
   prev_body_pct = (종가[t-1] - 시가[t-1]) / 시가[t-1] * 100 (부호 있는 값, 절대값 아님)
   prev_body_pct >= PREV_BODY_MIN_PCT
2. 당일 캔들(t)이 음봉: 종가[t] < 시가[t]
3. 위쪽 장악: 시가[t] >= 종가[t-1] * OPEN_TOLERANCE_RATIO
   BTC는 24시간 시장이라 갭이 거의 없다. 시가가 직전 종가보다 미세하게
   낮게 열리는 경우까지 인정하기 위해 0.1% 여유를 둔다.
4. 아래쪽 장악: 종가[t] <= 시가[t-1] * CLOSE_BREAK_RATIO
   직전 시가 선에 간신히 걸치는 캔들을 배제하기 위해 0.3% 초과해서 뚫고
   마감해야 인정한다.

방향: SHORT. trigger 신호 (해당 캔들에서만 발화, state로 유지되지 않음).
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_bearish_engulfing.parquet"

PREV_BODY_MIN_PCT = 1.5
OPEN_TOLERANCE_RATIO = 0.999
CLOSE_BREAK_RATIO = 0.997


def compute_bearish_engulfing(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    prev_body_pct = (df["close"] - df["open"]) / df["open"] * 100
    df["prev_body_pct"] = prev_body_pct

    is_bearish_engulfing = [False] * len(df)

    for i in range(1, len(df)):
        if prev_body_pct.iloc[i - 1] < PREV_BODY_MIN_PCT:
            continue

        open_, close = df["open"].iloc[i], df["close"].iloc[i]
        if close >= open_:
            continue

        prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
        if open_ < prev_close * OPEN_TOLERANCE_RATIO:
            continue
        if close > prev_open * CLOSE_BREAK_RATIO:
            continue

        is_bearish_engulfing[i] = True

    df["is_bearish_engulfing"] = is_bearish_engulfing
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_bearish_engulfing(df)

    print(f"bearish_engulfing 개수: {result['is_bearish_engulfing'].sum()} / 전체 {len(result)}개")

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
