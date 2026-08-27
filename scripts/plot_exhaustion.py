"""
4-6 매물소진 패턴 시각화

마커 (제안, 기존 차트들과 색/모양 겹치지 않게):
- 매수 신호: 파란 별(*), 저가 아래쪽에 표시
- 매도 신호: 주황 별(*), 고가 위쪽에 표시
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

KR_FONT = FontProperties(family="Malgun Gothic")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_exhaustion.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-6_exhaustion"
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
        pad = span * 0.03

        buy_vals = np.full(len(chunk), np.nan)
        sell_vals = np.full(len(chunk), np.nan)
        for pos in range(len(chunk)):
            sig = chunk["exhaustion_signal"].iloc[pos]
            if sig == "buy":
                buy_vals[pos] = chunk["low"].iloc[pos] - pad
            elif sig == "sell":
                sell_vals[pos] = chunk["high"].iloc[pos] + pad

        addplots = []
        used = set()
        if not np.all(np.isnan(buy_vals)):
            addplots.append(mpf.make_addplot(buy_vals, type="scatter", markersize=140, marker="*", color="blue"))
            used.add("buy")
        if not np.all(np.isnan(sell_vals)):
            addplots.append(mpf.make_addplot(sell_vals, type="scatter", markersize=140, marker="*", color="darkorange"))
            used.add("sell")

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  Exhaustion Pattern  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"exhaustion_{c+1:02d}_{start_date}_{end_date}.png"

        fig, axlist = mpf.plot(
            ohlc,
            type="candle",
            style="yahoo",
            addplot=addplots if addplots else None,
            title=title,
            volume=True,
            figsize=(16, 8),
            returnfig=True,
        )
        ax = axlist[0]
        legend_elems = []
        if "buy" in used:
            legend_elems.append(Line2D([0], [0], marker="*", color="blue", linestyle="None", markersize=12, label="매물소진 매수 신호"))
        if "sell" in used:
            legend_elems.append(Line2D([0], [0], marker="*", color="darkorange", linestyle="None", markersize=12, label="매물소진 매도 신호"))
        if legend_elems:
            ax.legend(handles=legend_elems, loc="upper left", prop=KR_FONT, fontsize=8)

        fig.savefig(fname, dpi=130)
        import matplotlib.pyplot as plt
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
