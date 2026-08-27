"""
4-8 RSI 시각화

- 캔들 패널 아래에 RSI 패널을 추가
- 과매수/과매도 신호(RSI<=25/>=80)는 다이버전스와 무관한 별도 신호라
  rsi_overbought_oversold.py + plot_rsi_ob_os.py로 완전히 분리됨 - 이 파일에는
  표시하지 않음. RSI 패널의 70/30 참고선만 유지 (일반적인 RSI 구간 표시용)
- 다이버전스(극점 기반 재설계): 가격 패널은 가격 스윙 위치(index)에, RSI 패널은
  짝지어진 RSI 스윙 위치(rsi_swing_index)에 마커 표시 - 둘의 x위치가 ±3봉 정도
  다를 수 있음(가격 극점과 RSI 극점이 정확히 같은 날이 아닐 수 있으므로)
  직전 스윙과 확정된 스윙을 각 패널에서 점선으로 연결해서
  "가격은 이 방향, RSI는 반대 방향"이 한눈에 보이게 함
  (연결에 필요한 점이 다른 차트 구간에 있어 잘리는 경우는 마커만 표시)
  - 정상 강세: 초록 위 삼각형 / 정상 약세: 빨강 아래 삼각형
  - 은닉 강세: 청록 다이아몬드 / 은닉 약세: 자홍 다이아몬드
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

KR_FONT = FontProperties(family="Malgun Gothic")

SWINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_swings.parquet"
RSI_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi.parquet"
DIV_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_divergence.parquet"
OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "4-8_rsi"
CHUNK_SIZE = 90

DIV_STYLE = {
    "regular_bullish": ("^", "green"),
    "regular_bearish": ("v", "red"),
    "hidden_bullish": ("D", "teal"),
    "hidden_bearish": ("D", "magenta"),
}
DIV_LABEL = {
    "regular_bullish": "정상 강세 다이버전스",
    "regular_bearish": "정상 약세 다이버전스",
    "hidden_bullish": "은닉 강세 다이버전스",
    "hidden_bearish": "은닉 약세 다이버전스",
}


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


if __name__ == "__main__":
    swings = pd.read_parquet(SWINGS_PATH).reset_index(drop=True)
    rsi_df = pd.read_parquet(RSI_PATH)
    div = pd.read_parquet(DIV_PATH)

    df = swings.merge(rsi_df[["open_time", "rsi"]], on="open_time", how="left")

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

        # 다이버전스 마커 (가격 패널 panel=0은 "index" 기준, RSI 패널 panel=2는
        # 짝지어진 "rsi_swing_index" 기준 - 가격 극점과 RSI 극점이 ±3봉 차이날 수 있음)
        div_chunk = div[(div["index"] >= start) & (div["index"] < end)].copy()

        price_markers = {}
        connector_lines = []  # (px1, py1, px2, py2, rx1, ry1, rx2, ry2, color) - 필요한 점이 같은 청크 안에 있을 때만
        for dtype in DIV_STYLE:
            p_vals = np.full(len(chunk), np.nan)
            r_vals = np.full(len(chunk), np.nan)
            any_val = False
            for _, ev in div_chunk[div_chunk["type"] == dtype].iterrows():
                price_pos = int(ev["index"]) - start
                p_vals[price_pos] = ev["price"]
                any_val = True

                rsi_swing_idx = int(ev["rsi_swing_index"])
                if start <= rsi_swing_idx < end:
                    r_vals[rsi_swing_idx - start] = ev["rsi"]

                prev_price_idx = int(ev["prev_index"])
                prev_rsi_idx = int(ev["prev_rsi_swing_index"])
                _, color = DIV_STYLE[dtype]
                if start <= prev_price_idx < end:
                    connector_lines.append((
                        "price", prev_price_idx - start, ev["prev_price"], price_pos, ev["price"], color,
                    ))
                if start <= prev_rsi_idx < end and start <= rsi_swing_idx < end:
                    connector_lines.append((
                        "rsi", prev_rsi_idx - start, ev["prev_rsi"], rsi_swing_idx - start, ev["rsi"], color,
                    ))
            if any_val:
                marker, color = DIV_STYLE[dtype]
                addplots.append(mpf.make_addplot(p_vals, panel=0, type="scatter", markersize=110, marker=marker, color=color))
                if not np.all(np.isnan(r_vals)):
                    addplots.append(mpf.make_addplot(r_vals, panel=2, type="scatter", markersize=90, marker=marker, color=color))
                price_markers[dtype] = True

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  RSI(14) + Divergence  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"rsi_{c+1:02d}_{start_date}_{end_date}.png"

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

        # mplfinance는 panel마다 (price_ax, twin_ax) 형태로 axes를 반환하는 경우가 있어
        # 실제 RSI 패널의 주 축을 이름으로 찾는다.
        rsi_ax = None
        rsi_ax_pos = None
        for pos, ax in enumerate(fig.axes):
            if ax.get_ylabel() == "RSI":
                rsi_ax = ax
                rsi_ax_pos = pos
                break
        if rsi_ax is not None:
            rsi_ax.axhline(70, color="orangered", linestyle=":", linewidth=0.8)
            rsi_ax.axhline(30, color="royalblue", linestyle=":", linewidth=0.8)
            rsi_ax.set_ylim(0, 100)
            # 빈 트윈 축이 데이터 범위로 자동 스케일되어 별도 눈금이 겹쳐 보이는 문제 방지
            if rsi_ax_pos + 1 < len(fig.axes):
                twin = fig.axes[rsi_ax_pos + 1]
                if twin.get_position().bounds == rsi_ax.get_position().bounds:
                    twin.set_yticks([])

        ax = axlist[0]

        for panel, x1, y1, x2, y2, color in connector_lines:
            target_ax = ax if panel == "price" else rsi_ax
            if target_ax is not None:
                target_ax.plot([x1, x2], [y1, y2], linestyle="--", color=color, linewidth=1.3, alpha=0.8, zorder=1)
        legend_elems = [Line2D([0], [0], marker=m, color=c_, linestyle="None", markersize=9, label=DIV_LABEL[k])
                        for k, (m, c_) in DIV_STYLE.items() if k in price_markers]
        if legend_elems:
            ax.legend(handles=legend_elems, loc="upper left", prop=KR_FONT, fontsize=7.5)

        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {n_chunks}장 생성 완료: {OUT_DIR}")
