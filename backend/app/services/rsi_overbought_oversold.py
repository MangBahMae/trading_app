"""
4-8. RSI 과매수/과매도 신호 (다이버전스와 완전히 독립된 별도 신호)

- RSI <= 25 -> 매수 신호
- RSI >= 80 -> 매도 신호
- 단순 임계값 기준. 그 구간에 머무는 동안 매 캔들 반복 발생 (크로스백 아님)

다이버전스(rsi_swings.py, divergence.py)와는 무관하게 독립적으로 관리되는 신호이므로
파일도 분리되어 있음. RSI 값 자체는 rsi.py의 결과(BTCUSDT_1d_rsi.parquet)를 그대로 사용.
"""
from pathlib import Path

import pandas as pd

RSI_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi_ob_os.parquet"

OVERSOLD = 25
OVERBOUGHT = 80


def compute_ob_os_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    df["rsi_buy"] = df["rsi"] <= OVERSOLD
    df["rsi_sell"] = df["rsi"] >= OVERBOUGHT

    df["oversold_state"] = df["rsi_buy"]
    df["oversold_trigger"] = df["oversold_state"] & ~df["oversold_state"].shift(1, fill_value=False)
    return df


if __name__ == "__main__":
    df = pd.read_parquet(RSI_PATH)
    result = compute_ob_os_signals(df)

    print(f"과매도(RSI<={OVERSOLD}) 매수 신호 캔들 수: {result['rsi_buy'].sum()}")
    print(f"과매수(RSI>={OVERBOUGHT}) 매도 신호 캔들 수: {result['rsi_sell'].sum()}")

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
