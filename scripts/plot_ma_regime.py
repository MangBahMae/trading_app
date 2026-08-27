"""
4-3 이동평균 배열 판정 시각화 (최종 확정 스펙)

- 캔들 + EMA9/EMA20/EMA50/EMA200 라인을 함께 그려서 배열 순서를 눈으로 직접 확인 가능하게 함
- 구간별 배경색으로 판정 결과 표시:
  - 정배열: 초록 계열 (의심 단계에 따라 진하기 다름: 0단계=진하게, 1단계=중간, 2단계=연하게)
  - 역배열: 빨강 계열 (의심 단계에 따라 진하기 다름: 0단계=진하게, 1단계=연하게)
  - 수렴: 노랑
  - 혼조: 무색
  - 데이터 부족(MA 계산 전): 연한 회색
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties

KR_FONT = FontProperties(family="Malgun Gothic")

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_ma_regime.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-3_ma_regime"
CHUNK_SIZE = 90

BULLISH_ALPHA_BY_SUSPICION = {0: 0.40, 1: 0.24, 2: 0.10}
BEARISH_ALPHA_BY_SUSPICION = {0: 0.40, 1: 0.16}
CONVERGENCE_ALPHA = 0.30
INSUFFICIENT_ALPHA = 0.15

GREEN = "#1a9c1a"
RED = "#c21807"
YELLOW = "#f5e642"
GRAY = "#bdbdbd"


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


def regime_style(regime, bullish_susp, bearish_susp):
    """(color, alpha) 반환. 표시할 배경이 없으면 (None, 0)."""
    if regime == "bullish":
        susp = int(bullish_susp) if not pd.isna(bullish_susp) else 0
        return GREEN, BULLISH_ALPHA_BY_SUSPICION.get(susp, 0.10)
    if regime == "bearish":
        susp = int(bearish_susp) if not pd.isna(bearish_susp) else 0
        return RED, BEARISH_ALPHA_BY_SUSPICION.get(susp, 0.16)
    if regime == "convergence":
        return YELLOW, CONVERGENCE_ALPHA
    if regime is None:
        return GRAY, INSUFFICIENT_ALPHA
    return None, 0.0  # mixed


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH).reset_index(drop=True)
    df["ma_regime"] = df["ma_regime"].where(df["ma_regime"].notna(), None)

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

        ma_specs = [
            ("MA9", "blue", 1.0, "-"),
            ("MA20", "orange", 1.0, "-"),
            ("MA50", "purple", 1.2, "-"),
            ("MA200", "black", 1.2, "--"),
        ]
        addplots = []
        for col, color, width, style in ma_specs:
            vals = chunk[col].values
            if np.all(np.isnan(vals)):
                continue
            addplots.append(mpf.make_addplot(vals, color=color, width=width, linestyle=style))

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  EMA Regime  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"ma_regime_{c+1:02d}_{start_date}_{end_date}.png"

        fig, axlist = mpf.plot(
            ohlc,
            type="candle",
            style="yahoo",
            addplot=addplots,
            title=title,
            volume=True,
            figsize=(18, 9),
            returnfig=True,
        )
        ax = axlist[0]

        for pos in range(len(chunk)):
            regime = chunk["ma_regime"].iloc[pos]
            color, alpha = regime_style(regime, chunk["bullish_suspicion"].iloc[pos], chunk["bearish_suspicion"].iloc[pos])
            if color and alpha > 0:
                ax.axvspan(pos - 0.5, pos + 0.5, color=color, alpha=alpha, lw=0)

        # 이 차트(구간)에 실제로 등장하는 카테고리만 범례에 표시 (없는 카테고리를 보여줘서
        # "이 구간에도 해당 배경이 있나?"로 오해하는 것을 방지)
        bullish_mask = chunk["ma_regime"] == "bullish"
        bearish_mask = chunk["ma_regime"] == "bearish"
        present_bullish_susp = set(chunk.loc[bullish_mask, "bullish_suspicion"].dropna().astype(int))
        present_bearish_susp = set(chunk.loc[bearish_mask, "bearish_suspicion"].dropna().astype(int))
        has_convergence = (chunk["ma_regime"] == "convergence").any()
        has_insufficient = chunk["ma_regime"].isna().any()

        legend_handles = [
            mpatches.Patch(color="blue", label="EMA9"),
            mpatches.Patch(color="orange", label="EMA20"),
            mpatches.Patch(color="purple", label="EMA50"),
            mpatches.Patch(color="black", label="EMA200(점선)"),
        ]
        for susp in sorted(present_bullish_susp):
            legend_handles.append(mpatches.Patch(facecolor=GREEN, alpha=BULLISH_ALPHA_BY_SUSPICION[susp], label=f"정배열(의심{susp})"))
        for susp in sorted(present_bearish_susp):
            legend_handles.append(mpatches.Patch(facecolor=RED, alpha=BEARISH_ALPHA_BY_SUSPICION[susp], label=f"역배열(의심{susp})"))
        if has_convergence:
            legend_handles.append(mpatches.Patch(facecolor=YELLOW, alpha=CONVERGENCE_ALPHA, label="수렴"))
        if has_insufficient:
            legend_handles.append(mpatches.Patch(facecolor=GRAY, alpha=INSUFFICIENT_ALPHA, label="데이터 부족"))

        ax.legend(handles=legend_handles, loc="upper left", prop=KR_FONT, fontsize=7, ncol=2)

        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
