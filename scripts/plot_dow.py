"""
4-2 다우이론(HH/LH/HL/LL) 시각화

마커 규칙 (제안):
- 모양: 스윙 하이는 위쪽 삼각형(▲), 스윙 로우는 아래쪽 삼각형(▼) — 4-1과 동일
- 색상: HH/HL(직전 대비 상승) = 초록, LH/LL(직전 대비 하락) = 빨강
- 맨 처음 스윙(비교 대상 없어 라벨 없음) = 회색
- 각 마커 위/아래에 라벨 텍스트(HH/LH/HL/LL)를 표기
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf

SWINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_swings.parquet"
DOW_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_dow.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-2_dow_theory"
CHUNK_SIZE = 90

COLOR_MAP = {"HH": "green", "HL": "green", "LH": "red", "LL": "red", None: "gray"}


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


if __name__ == "__main__":
    swings = pd.read_parquet(SWINGS_PATH).reset_index(drop=True)
    dow = pd.read_parquet(DOW_PATH)
    # 한 캔들이 스윙 하이이면서 동시에 스윙 로우인 경우가 있으므로(예: 2025-01-20),
    # index만으로 dict를 만들면 high/low 라벨이 서로 덮어써진다 -> kind별로 분리해서 관리
    high_label_by_index = dict(zip(dow.loc[dow["kind"] == "high", "index"], dow.loc[dow["kind"] == "high", "label"]))
    low_label_by_index = dict(zip(dow.loc[dow["kind"] == "low", "index"], dow.loc[dow["kind"] == "low", "label"]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_chunks = int(np.ceil(len(swings) / CHUNK_SIZE))
    print(f"전체 {len(swings)}개 캔들 -> {n_chunks}장으로 분할 (장당 최대 {CHUNK_SIZE}개)")

    for c in range(n_chunks):
        start = c * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(swings))
        chunk = swings.iloc[start:end].reset_index(drop=True)
        if len(chunk) < 5:
            continue

        ohlc = build_ohlc(chunk)
        span = chunk["high"].max() - chunk["low"].min()
        pad = span * 0.02

        # 라벨별로 별도 scatter 시리즈를 만들어 색상을 구분한다.
        addplots = []
        annotations = []  # (x_pos, y, text, color)

        for label, color in [("HH", "green"), ("LH", "red")]:
            vals = np.full(len(chunk), np.nan)
            for pos in range(len(chunk)):
                global_idx = start + pos
                if chunk["swing_high"].iloc[pos] and high_label_by_index.get(global_idx) == label:
                    vals[pos] = chunk["high"].iloc[pos] + pad
                    annotations.append((pos, vals[pos], label, color, "bottom"))
            if not np.all(np.isnan(vals)):
                addplots.append(mpf.make_addplot(vals, type="scatter", markersize=100, marker="^", color=color))

        for label, color in [("HL", "green"), ("LL", "red")]:
            vals = np.full(len(chunk), np.nan)
            for pos in range(len(chunk)):
                global_idx = start + pos
                if chunk["swing_low"].iloc[pos] and low_label_by_index.get(global_idx) == label:
                    vals[pos] = chunk["low"].iloc[pos] - pad
                    annotations.append((pos, vals[pos], label, color, "top"))
            if not np.all(np.isnan(vals)):
                addplots.append(mpf.make_addplot(vals, type="scatter", markersize=100, marker="v", color=color))

        # 라벨 없는 첫 스윙(회색, 비교 대상 없음)
        def is_unlabeled(v):
            return v is None or (isinstance(v, float) and pd.isna(v))

        gray_high = np.full(len(chunk), np.nan)
        gray_low = np.full(len(chunk), np.nan)
        for pos in range(len(chunk)):
            global_idx = start + pos
            if chunk["swing_high"].iloc[pos] and global_idx in high_label_by_index and is_unlabeled(high_label_by_index[global_idx]):
                gray_high[pos] = chunk["high"].iloc[pos] + pad
            if chunk["swing_low"].iloc[pos] and global_idx in low_label_by_index and is_unlabeled(low_label_by_index[global_idx]):
                gray_low[pos] = chunk["low"].iloc[pos] - pad
        if not np.all(np.isnan(gray_high)):
            addplots.append(mpf.make_addplot(gray_high, type="scatter", markersize=100, marker="^", color="gray"))
        if not np.all(np.isnan(gray_low)):
            addplots.append(mpf.make_addplot(gray_low, type="scatter", markersize=100, marker="v", color="gray"))

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  Dow Theory HH/LH/HL/LL  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"dow_{c+1:02d}_{start_date}_{end_date}.png"

        fig, axlist = mpf.plot(
            ohlc,
            type="candle",
            style="yahoo",
            addplot=addplots if addplots else None,
            title=title,
            volume=True,
            figsize=(18, 9),
            returnfig=True,
        )
        ax = axlist[0]
        for x_pos, y, text, color, va in annotations:
            offset_pts = 11 if va == "bottom" else -11
            ax.annotate(text, xy=(x_pos, y), xytext=(0, offset_pts), textcoords="offset points",
                        color=color, fontsize=8, fontweight="bold", ha="center", va=va)

        fig.savefig(fname, dpi=130)
        import matplotlib.pyplot as plt
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
