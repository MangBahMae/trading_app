"""
[DISABLED] 실험용 스크립트 - 활성 파이프라인에서 제외됨 (scripts/_disabled/로 이동, 2026-08-27)
참고/비교 목적으로만 보관. 정식 4단계 로직은 scripts/exhaustion.py를 볼 것.

4-6 매물소진 패턴 - 기존 버전 vs 실험 버전(ER Score) 비교 시각화

마커:
- 기존 매수: 파란 별(*), 저가 아래
- 기존 매도: 주황 별(*), 고가 위
- 실험 매수: 청록 +(P), 저가 아래쪽(기존보다 더 아래로 오프셋 - 같은 날 겹치면 위아래로 쌓여 보임)
- 실험 매도: 자홍 +(P), 고가 위쪽(기존보다 더 위로 오프셋)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

KR_FONT = FontProperties(family="Malgun Gothic")

OLD_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "merged" / "BTCUSDT_1d_exhaustion.parquet"
NEW_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "merged" / "BTCUSDT_1d_exhaustion_v2.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "charts" / "4-6_exhaustion_compare"
CHUNK_SIZE = 90


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


if __name__ == "__main__":
    old = pd.read_parquet(OLD_PATH)[["open_time", "exhaustion_signal"]]
    new = pd.read_parquet(NEW_PATH)[["open_time", "exhaustion_signal_v2"]]
    base = pd.read_parquet(OLD_PATH)  # OHLCV 포함
    df = base.merge(new, on="open_time", how="left").reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n_chunks = int(np.ceil(len(df) / CHUNK_SIZE))
    print(f"전체 {len(df)}개 캔들 -> {n_chunks}장으로 분할 (장당 최대 {CHUNK_SIZE}개)")

    overlap_dates = []

    for c in range(n_chunks):
        start = c * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(df))
        chunk = df.iloc[start:end].reset_index(drop=True)
        if len(chunk) < 5:
            continue

        ohlc = build_ohlc(chunk)
        span = chunk["high"].max() - chunk["low"].min()
        pad = span * 0.03

        old_buy = np.full(len(chunk), np.nan)
        old_sell = np.full(len(chunk), np.nan)
        new_buy = np.full(len(chunk), np.nan)
        new_sell = np.full(len(chunk), np.nan)

        for pos in range(len(chunk)):
            row = chunk.iloc[pos]
            if row["exhaustion_signal"] == "buy":
                old_buy[pos] = row["low"] - pad
            elif row["exhaustion_signal"] == "sell":
                old_sell[pos] = row["high"] + pad
            if row["exhaustion_signal_v2"] == "buy":
                new_buy[pos] = row["low"] - pad * 2.4
            elif row["exhaustion_signal_v2"] == "sell":
                new_sell[pos] = row["high"] + pad * 2.4

            if pd.notna(row["exhaustion_signal"]) and pd.notna(row["exhaustion_signal_v2"]):
                overlap_dates.append((row["open_time"], row["exhaustion_signal"], row["exhaustion_signal_v2"]))

        addplots = []
        used = set()
        if not np.all(np.isnan(old_buy)):
            addplots.append(mpf.make_addplot(old_buy, type="scatter", markersize=130, marker="*", color="blue"))
            used.add("old_buy")
        if not np.all(np.isnan(old_sell)):
            addplots.append(mpf.make_addplot(old_sell, type="scatter", markersize=130, marker="*", color="darkorange"))
            used.add("old_sell")
        if not np.all(np.isnan(new_buy)):
            addplots.append(mpf.make_addplot(new_buy, type="scatter", markersize=110, marker="P", color="teal"))
            used.add("new_buy")
        if not np.all(np.isnan(new_sell)):
            addplots.append(mpf.make_addplot(new_sell, type="scatter", markersize=110, marker="P", color="magenta"))
            used.add("new_sell")

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  Exhaustion: Original vs Experimental(ER Score)  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"exhaustion_compare_{c+1:02d}_{start_date}_{end_date}.png"

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

        legend_map = {
            "old_buy": ("*", "blue", "기존 매수"),
            "old_sell": ("*", "darkorange", "기존 매도"),
            "new_buy": ("P", "teal", "실험 매수(ER Score)"),
            "new_sell": ("P", "magenta", "실험 매도(ER Score)"),
        }
        legend_elems = [Line2D([0], [0], marker=m, color=c_, linestyle="None", markersize=10, label=l)
                        for key, (m, c_, l) in legend_map.items() if key in used]
        if legend_elems:
            ax.legend(handles=legend_elems, loc="upper left", prop=KR_FONT, fontsize=8)

        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
    print(f"\n두 버전이 같은 날 동시에 신호를 낸 경우: {len(overlap_dates)}건")
    for d, o, n in overlap_dates:
        print(f"  {d.date()}: 기존={o}, 실험={n}")
