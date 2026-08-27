"""
4-8 RSI 과매수/과매도 시각화 (다이버전스와 완전히 분리된 독립 차트)

- 캔들 패널 아래에 RSI 패널을 추가, 25/80 기준선(실선)만 표시
- 과매도(RSI<=25) 구간은 파란 점, 과매수(RSI>=80) 구간은 빨간 점으로
  매 캔들 반복 표시 (크로스백 아님, 그 구간에 머무는 동안 계속 찍힘)
- 다이버전스 마커/연결선은 여기 없음 (plot_rsi.py 참고)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

KR_FONT = FontProperties(family="Malgun Gothic")

OB_OS_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi_ob_os.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-8_rsi_ob_os"
CHUNK_SIZE = 90


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


if __name__ == "__main__":
    df = pd.read_parquet(OB_OS_PATH).reset_index(drop=True)

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
        rsi_vals = chunk["rsi"].values

        addplots = [mpf.make_addplot(rsi_vals, panel=2, color="black", width=1.1, ylabel="RSI")]

        oversold_vals = np.where(chunk["rsi_buy"].values, rsi_vals, np.nan)
        overbought_vals = np.where(chunk["rsi_sell"].values, rsi_vals, np.nan)
        used = set()
        if not np.all(np.isnan(oversold_vals)):
            addplots.append(mpf.make_addplot(oversold_vals, panel=2, type="scatter", markersize=35, marker="o", color="blue"))
            used.add("buy")
        if not np.all(np.isnan(overbought_vals)):
            addplots.append(mpf.make_addplot(overbought_vals, panel=2, type="scatter", markersize=35, marker="o", color="red"))
            used.add("sell")

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  RSI Overbought/Oversold (25/80)  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"rsi_ob_os_{c+1:02d}_{start_date}_{end_date}.png"

        fig, axlist = mpf.plot(
            ohlc,
            type="candle",
            style="yahoo",
            addplot=addplots,
            title=title,
            volume=True,
            panel_ratios=(3, 1, 1.4),
            figsize=(18, 11),
            returnfig=True,
        )

        rsi_ax = None
        rsi_ax_pos = None
        for pos, ax in enumerate(fig.axes):
            if ax.get_ylabel() == "RSI":
                rsi_ax = ax
                rsi_ax_pos = pos
                break
        if rsi_ax is not None:
            rsi_ax.axhline(80, color="orangered", linestyle="-", linewidth=1)
            rsi_ax.axhline(25, color="royalblue", linestyle="-", linewidth=1)
            rsi_ax.set_ylim(0, 100)
            if rsi_ax_pos + 1 < len(fig.axes):
                twin = fig.axes[rsi_ax_pos + 1]
                if twin.get_position().bounds == rsi_ax.get_position().bounds:
                    twin.set_yticks([])

        ax = axlist[0]
        legend_elems = []
        if "buy" in used:
            legend_elems.append(Line2D([0], [0], marker="o", color="blue", linestyle="None", markersize=7, label="과매도(RSI<=25) 매수 신호"))
        if "sell" in used:
            legend_elems.append(Line2D([0], [0], marker="o", color="red", linestyle="None", markersize=7, label="과매수(RSI>=80) 매도 신호"))
        if legend_elems:
            ax.legend(handles=legend_elems, loc="upper left", prop=KR_FONT, fontsize=8)

        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
