"""
4-5 도지캔들 시각화

마커: 보라색 다이아몬드(D)를 캔들 고가 위쪽에 표시 (기존 스윙/MA/터치 마커와 색·모양이 겹치지 않도록)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_doji.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-5_doji"
CHUNK_SIZE = 90


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH).reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_chunks = int(np.ceil(len(df) / CHUNK_SIZE))
    print(f"전체 {len(df)}개 캔들 -> {n_chunks}장으로 분할 (장당 최대 {CHUNK_SIZE}개)")

    for c in range(n_chunks):
        start = c * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(df))
        chunk = df.iloc[start:end].reset_index(drop=True)
        if len(chunk) < 5:
            continue

        ohlc = build_ohlc(chunk)
        span = chunk["high"].max() - chunk["low"].min()
        pad = span * 0.02

        doji_vals = np.full(len(chunk), np.nan)
        for pos in range(len(chunk)):
            if chunk["is_doji"].iloc[pos]:
                doji_vals[pos] = chunk["high"].iloc[pos] + pad

        addplots = []
        if not np.all(np.isnan(doji_vals)):
            addplots.append(mpf.make_addplot(doji_vals, type="scatter", markersize=90, marker="D", color="darkviolet"))

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  Doji Candles  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"doji_{c+1:02d}_{start_date}_{end_date}.png"

        mpf.plot(
            ohlc,
            type="candle",
            style="yahoo",
            addplot=addplots if addplots else None,
            title=title,
            volume=True,
            figsize=(16, 8),
            savefig=dict(fname=str(fname), dpi=130),
        )
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
