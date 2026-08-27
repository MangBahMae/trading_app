"""
4-8 다이버전스 재설계 (v3) - RSI 극점(pivot) 탐지, 트레이딩뷰 표준 방식

트레이딩뷰 내장 RSI 다이버전스 로직 및 커뮤니티 표준 구현체 참고:
https://github.com/iamc1oud/Tradingview-Scripts/blob/master/rsi-indicator.pine
(MPL-2.0, 원작 (c) systemalphatrader) - pivot 탐지 파라미터(lbL=5, lbR=5)를 이식.

- 중심 캔들 i의 RSI가 좌우 5개봉(lbL=lbR=5)의 RSI보다 모두 높으면 고점,
  모두 낮으면 저점으로 확정 (동률 스킵, 오차 허용 없음)
  * 4-1 가격 스윙(N=2)과는 의도적으로 다른 파라미터 - RSI는 가격보다 노이즈가
    많아 더 넓은 좌우 범위가 필요
- 확정 방식: 우측 5봉이 모두 마감되어야 확정 (confirmed_at = i+5 캔들의 close_time)
- RSI가 NaN인 구간(워밍업 14봉)은 판정 대상에서 제외
"""
from pathlib import Path

import pandas as pd

RSI_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi_swings.parquet"

N = 5  # lbL = lbR = 5 (트레이딩뷰 표준)


def find_rsi_swings(df: pd.DataFrame, n: int = N) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    rsi = df["rsi"]
    n_rows = len(df)

    swing_high = [False] * n_rows
    swing_low = [False] * n_rows
    confirmed_at = [pd.NaT] * n_rows

    for i in range(n, n_rows - n):
        window = rsi.iloc[i - n:i + n + 1]
        if window.isna().any():
            continue  # 워밍업 구간 등 RSI 없는 캔들이 껴 있으면 판정 불가

        left = rsi.iloc[i - n:i]
        right = rsi.iloc[i + 1:i + n + 1]

        if rsi.iloc[i] > left.max() and rsi.iloc[i] > right.max():
            swing_high[i] = True
            confirmed_at[i] = df["close_time"].iloc[i + n]

        if rsi.iloc[i] < left.min() and rsi.iloc[i] < right.min():
            swing_low[i] = True
            confirmed_at[i] = df["close_time"].iloc[i + n]

    df["rsi_swing_high"] = swing_high
    df["rsi_swing_low"] = swing_low
    df["rsi_confirmed_at"] = confirmed_at
    return df


if __name__ == "__main__":
    df = pd.read_parquet(RSI_PATH)
    result = find_rsi_swings(df, N)

    print(f"RSI 스윙 하이 개수: {result['rsi_swing_high'].sum()}")
    print(f"RSI 스윙 로우 개수: {result['rsi_swing_low'].sum()}")

    result.to_parquet(OUT_PATH, index=False)
    print(f"저장 완료: {OUT_PATH}")
