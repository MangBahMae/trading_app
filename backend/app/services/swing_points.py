"""
4-1. 스윙 하이/로우 판독

규칙 (킥오프 문서 4-1):
- 중심 캔들 i가 좌우 N=2개 캔들의 고가/저가보다 엄격히(>, <) 높거나 낮으면 스윙 하이/로우
- 동률은 스킵 (오차 허용 없음)
- 판정은 고가/저가 기준 (종가 아님)
- 확정 방식: 우측 N봉이 모두 마감되어야 확정. confirmed_at = 우측 N번째 캔들의 close_time
  (그 시점이 되어야 비로소 스윙 여부를 알 수 있음 -> look-ahead bias 방지)
"""
from pathlib import Path

import pandas as pd

N = 2
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"


def find_swing_points(df: pd.DataFrame, n: int = N) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n_rows = len(df)

    swing_high = [False] * n_rows
    swing_low = [False] * n_rows
    confirmed_at = [pd.NaT] * n_rows  # 스윙 하이/로우 공통 확정 시각 컬럼

    for i in range(n, n_rows - n):
        left_highs = highs[i - n:i]
        right_highs = highs[i + 1:i + n + 1]
        if highs[i] > left_highs.max() and highs[i] > right_highs.max():
            swing_high[i] = True
            confirmed_at[i] = df["close_time"].iloc[i + n]

        left_lows = lows[i - n:i]
        right_lows = lows[i + 1:i + n + 1]
        if lows[i] < left_lows.min() and lows[i] < right_lows.min():
            swing_low[i] = True
            confirmed_at[i] = df["close_time"].iloc[i + n]

    df["swing_high"] = swing_high
    df["swing_low"] = swing_low
    df["confirmed_at"] = confirmed_at
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = find_swing_points(df, N)

    n_high = result["swing_high"].sum()
    n_low = result["swing_low"].sum()
    print(f"스윙 하이 개수: {n_high}")
    print(f"스윙 로우 개수: {n_low}")

    out_path = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_swings.parquet"
    result.to_parquet(out_path, index=False)
    print(f"저장 완료: {out_path}")
