"""
4-8 재설계 - 1단계 검증: RSI 극점(스윙) 탐지 자체가 맞게 찍히는지 확인

RSI 패널 위에 RSI 스윙 하이/로우 마커 표시 (4-1 가격 스윙 차트와 동일한 색상 규칙):
- RSI 스윙 하이: 빨간 위쪽 삼각형
- RSI 스윙 로우: 파란 아래쪽 삼각형
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf

RSI_SWINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi_swings.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-8_rsi_swings_check"
CHUNK_SIZE = 90


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


if __name__ == "__main__":
    df = pd.read_parquet(RSI_SWINGS_PATH).reset_index(drop=True)

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

        high_vals = np.where(chunk["rsi_swing_high"].values, rsi_vals + 3, np.nan)
        low_vals = np.where(chunk["rsi_swing_low"].values, rsi_vals - 3, np.nan)
        if not np.all(np.isnan(high_vals)):
            addplots.append(mpf.make_addplot(high_vals, panel=2, type="scatter", markersize=60, marker="^", color="red"))
        if not np.all(np.isnan(low_vals)):
            addplots.append(mpf.make_addplot(low_vals, panel=2, type="scatter", markersize=60, marker="v", color="blue"))

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  RSI Swing Check  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"rsi_swing_check_{c+1:02d}_{start_date}_{end_date}.png"

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
            rsi_ax.axhline(70, color="gray", linestyle=":", linewidth=0.8)
            rsi_ax.axhline(30, color="gray", linestyle=":", linewidth=0.8)
            rsi_ax.set_ylim(0, 100)
            # mplfinance가 패널마다 만드는 빈 트윈 축이 데이터 범위로 자동 스케일되어
            # 별도의 눈금(예: 25~40)이 겹쳐 보이는 문제 방지 - 트윈 축 눈금 숨김
            if rsi_ax_pos + 1 < len(fig.axes):
                twin = fig.axes[rsi_ax_pos + 1]
                if twin.get_position().bounds == rsi_ax.get_position().bounds:
                    twin.set_yticks([])

        import matplotlib.pyplot as plt
        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
