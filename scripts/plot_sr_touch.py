"""
4-4 이동평균 터치 후 롱/숏 신호 시각화

마커 규칙 (텍스트 라벨은 연속 터치 구간에서 겹쳐 보여 제거하고, 마커 모양/색으로만 구분):
- 색: 롱 신호 = 초록, 숏 신호 = 빨강
- 모양: MA50 = 원(o)/얇은 X(x), MA200 = 사각형(s)/굵은 X(X)
- 배경으로 EMA50(보라)/EMA200(검정 점선) 라인을 함께 그려서 터치 지점을 눈으로 확인 가능하게 함
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

KR_FONT = FontProperties(family="Malgun Gothic")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_sr_touch.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-4_sr_touch"
CHUNK_SIZE = 90

# (ma_col, signal) -> (marker, color)
MARKER_STYLE = {
    ("MA50", "long"): ("o", "green"),
    ("MA50", "short"): ("x", "red"),
    ("MA200", "long"): ("s", "green"),
    ("MA200", "short"): ("X", "red"),
}


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

        ma_specs = [("MA50", "purple", 1.2, "-"), ("MA200", "black", 1.2, "--")]
        addplots = []
        for col, color, width, style in ma_specs:
            vals = chunk[col].values
            if np.all(np.isnan(vals)):
                continue
            addplots.append(mpf.make_addplot(vals, color=color, width=width, linestyle=style))

        used_keys = set()
        for ma_col in ["MA50", "MA200"]:
            signal_col = f"{ma_col}_signal"
            for signal in ["long", "short"]:
                vals = np.full(len(chunk), np.nan)
                any_val = False
                for pos in range(len(chunk)):
                    if chunk[signal_col].iloc[pos] != signal:
                        continue
                    vals[pos] = chunk[ma_col].iloc[pos]
                    any_val = True
                if any_val:
                    marker, color = MARKER_STYLE[(ma_col, signal)]
                    addplots.append(mpf.make_addplot(vals, type="scatter", markersize=90, marker=marker, color=color))
                    used_keys.add((ma_col, signal))

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  MA Touch Long/Short (MA50/MA200)  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"sr_touch_{c+1:02d}_{start_date}_{end_date}.png"

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

        legend_labels = {
            ("MA50", "long"): "MA50 터치 → 롱 신호",
            ("MA50", "short"): "MA50 터치 → 숏 신호",
            ("MA200", "long"): "MA200 터치 → 롱 신호",
            ("MA200", "short"): "MA200 터치 → 숏 신호",
        }
        legend_elems = []
        for key in [("MA50", "long"), ("MA50", "short"), ("MA200", "long"), ("MA200", "short")]:
            if key in used_keys:
                marker, color = MARKER_STYLE[key]
                legend_elems.append(Line2D([0], [0], marker=marker, color=color, linestyle="None",
                                            markersize=8, label=legend_labels[key]))
        if legend_elems:
            ax.legend(handles=legend_elems, loc="upper left", prop=KR_FONT, fontsize=7.5)

        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
