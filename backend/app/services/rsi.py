"""
4-8. RSI 값 계산 (Wilder 방식 14기간)

- 고전 Wilder 스무딩: 첫 평균 상승/하락폭은 14개 단순평균으로 시드하고,
  이후는 (이전평균*13 + 현재값)/14 로 재귀 계산 (단순 EMA 근사가 아닌 정통 Wilder 공식)
- avg_loss == 0 이면 RSI = 100 (avg_gain도 0이면 RSI = 50, 변동 없음)

이 파일은 RSI 값 자체만 계산한다. 아래 신호들은 각각 독립된 파일로 분리되어 있음:
- 과매수/과매도 신호(RSI<=25 매수, RSI>=80 매도) -> rsi_overbought_oversold.py
- 다이버전스 -> rsi_swings.py + divergence.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi.parquet"

PERIOD = 14


def compute_rsi_wilder(close: pd.Series, period: int = PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = np.full(len(close), np.nan)
    avg_loss = np.full(len(close), np.nan)

    if len(close) <= period:
        return pd.Series(avg_gain, index=close.index)

    avg_gain[period] = gain.iloc[1:period + 1].mean()
    avg_loss[period] = loss.iloc[1:period + 1].mean()

    for i in range(period + 1, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss.iloc[i]) / period

    rsi = np.full(len(close), np.nan)
    for i in range(period, len(close)):
        ag, al = avg_gain[i], avg_loss[i]
        if al == 0 and ag == 0:
            rsi[i] = 50.0
        elif al == 0:
            rsi[i] = 100.0
        else:
            rs = ag / al
            rsi[i] = 100 - 100 / (1 + rs)

    return pd.Series(rsi, index=close.index)


def compute_rsi_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    df["rsi"] = compute_rsi_wilder(df["close"])
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_rsi_signals(df)

    print(result["rsi"].describe())

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
