"""
4-1 스윙 하이/로우 시각화

전체 구간을 한 화면에 넣으면 가독성이 떨어지므로,
약 90개 캔들(3개월 안팎) 단위로 나눠서 여러 장의 이미지로 저장한다.

마커:
- 스윙 하이: 위쪽 삼각형 (빨강), 고가 위쪽에 표시
- 스윙 로우: 아래쪽 삼각형 (파랑), 저가 아래쪽에 표시
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_swings.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-1_swing_points"
CHUNK_SIZE = 90


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


def marker_series(df: pd.DataFrame, col: str, price_col: str, direction: int, offset_ratio: float = 0.02):
    """
    col: 'swing_high' or 'swing_low' boolean 컬럼
    price_col: 'high' or 'low'
    direction: +1이면 가격 위쪽에, -1이면 가격 아래쪽에 마커 배치
    """
    vals = np.full(len(df), np.nan)
    span = df["high"].max() - df["low"].min()
    pad = span * offset_ratio
    for i in range(len(df)):
        if df[col].iloc[i]:
            vals[i] = df[price_col].iloc[i] + direction * pad
    return vals


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH).reset_index(drop=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_chunks = int(np.ceil(len(df) / CHUNK_SIZE))
    print(f"전체 {len(df)}개 캔들 -> {n_chunks}장으로 분할 (장당 최대 {CHUNK_SIZE}개)")

    saved_files = []
    for idx in range(n_chunks):
        start = idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(df))
        chunk = df.iloc[start:end].reset_index(drop=True)
        if len(chunk) < 5:
            continue

        ohlc = build_ohlc(chunk)

        high_markers = marker_series(chunk, "swing_high", "high", direction=+1)
        low_markers = marker_series(chunk, "swing_low", "low", direction=-1)

        addplots = []
        if not np.all(np.isnan(high_markers)):
            addplots.append(
                mpf.make_addplot(high_markers, type="scatter", markersize=90, marker="^", color="red")
            )
        if not np.all(np.isnan(low_markers)):
            addplots.append(
                mpf.make_addplot(low_markers, type="scatter", markersize=90, marker="v", color="blue")
            )

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  Swing High/Low  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"swing_{idx+1:02d}_{start_date}_{end_date}.png"

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
        saved_files.append(fname)
        print(f"저장: {fname}")

    print(f"\n총 {len(saved_files)}장의 차트 이미지 생성 완료: {OUT_DIR}")
