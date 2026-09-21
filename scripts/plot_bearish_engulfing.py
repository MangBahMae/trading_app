"""
장악형 하락(bearish_engulfing) 시각화 + 임계값 검증용 통계

목적: bearish_engulfing.py의 임계값(PREV_BODY_MIN_PCT=1.5%, OPEN_TOLERANCE_RATIO,
CLOSE_BREAK_RATIO)이 적절한지 실데이터로 확인.

다른 plot_*.py와 다른 점 (plot_doji_spinning_top_at_high.py와 동일한 이유):
- "2022-01-01 이후" 통계가 필요해서 로컬 정적 parquet(2025-01~) 대신
  data_fetcher.ensure_fresh_data()로 전체 이력을 가져온다.
- compute_bearish_engulfing()/compute_volatility_expansion()도 사전 병합 parquet
  대신 여기서 직접 호출한다.
- 신호가 드물어서 신호(무효화 포함) 발생 캔들 기준 앞/뒤 여유를 두고 잘라서
  저장하며, 가까운 신호는 한 창으로 묶는다 (4-1처럼 고정폭 분할 아님).

마커:
- bearish_engulfing: 보라 아래쪽 삼각형(v), 고가 위
- 시세 분출로 무효화된 케이스: 같은 모양이지만 회색 + 반투명(alpha=0.4)
- 트리거가 된(장악당한) 직전 양봉: 파란 위쪽 삼각형(^), 저가 아래
- 각 신호 위에 텍스트로 prev_body_pct / open[t]÷close[t-1] / close[t]÷open[t-1]
  (무효화면 N/cum_pct/cum_pct_per_n) 표기
"""
from pathlib import Path

import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

import bearish_engulfing as beng
import volatility_expansion as ve
from data_fetcher import ensure_fresh_data

KR_FONT = FontProperties(family="Malgun Gothic")

OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "charts" / "bearish_engulfing"
START_DATE = pd.Timestamp("2022-01-01", tz="UTC")

BEFORE = 15
AFTER = 10
MERGE_GAP = 5
MAX_SPAN = 70   # 병합 결과가 이 캔들 수를 넘으면 병합을 멈추고 새 창을 시작


def build_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    ohlc = df.set_index("open_time")[["open", "high", "low", "close", "volume"]].copy()
    ohlc.columns = ["Open", "High", "Low", "Close", "Volume"]
    ohlc.index.name = "Date"
    return ohlc


def merge_windows(indices: set, before: int, after: int, merge_gap: int, max_span: int, n: int) -> list:
    windows = []
    for i in sorted(indices):
        start = max(0, i - before)
        end = min(n - 1, i + after)
        if windows:
            prev_start, prev_end, members = windows[-1]
            merged_end = max(prev_end, end)
            if start <= prev_end + merge_gap and merged_end - prev_start <= max_span:
                windows[-1] = (prev_start, merged_end, members | {i})
                continue
        windows.append((start, end, {i}))
    return windows


def invalidation_text(vol_df: pd.DataFrame, i: int) -> str:
    matches = vol_df["volatility_expansion_windows"].iloc[i]
    if not matches:
        return "무효화(시세분출)"
    m = matches[0]
    cum = vol_df[f"cum_pct_{m}"].iloc[i]
    cum_n = vol_df[f"cum_pct_per_n_{m}"].iloc[i]
    return f"무효화 N={m} cum={cum:.1f}% cum/N={cum_n:.1f}%"


if __name__ == "__main__":
    df = ensure_fresh_data().reset_index(drop=True)
    df = df[df["open_time"] >= START_DATE].reset_index(drop=True)

    result = beng.compute_bearish_engulfing(df)
    vol_df = ve.compute_volatility_expansion(df)

    beng_idx = set(df.index[result["is_bearish_engulfing"]].tolist())

    def is_invalidated(i: int) -> bool:
        return bool(vol_df["is_volatility_expansion"].iloc[i])

    beng_final = {i for i in beng_idx if not is_invalidated(i)}

    # ---------------- 콘솔 요약 ----------------
    print(f"=== bearish_engulfing 발생 건수 ({START_DATE.date()} 이후) ===")
    print(f"bearish_engulfing : 원시 {len(beng_idx):3d}건 / 무효화 {len(beng_idx) - len(beng_final):3d}건 / 최종 {len(beng_final):3d}건")
    print()

    # ---------------- 시각화 ----------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    windows = merge_windows(beng_idx, BEFORE, AFTER, MERGE_GAP, MAX_SPAN, len(df))
    print(f"이벤트 {len(beng_idx)}건 -> {len(windows)}개 구간(차트)으로 병합해서 저장")

    for w_i, (start, end, members) in enumerate(windows):
        chunk = df.iloc[start:end + 1].reset_index(drop=True)
        offset = start
        ohlc = build_ohlc(chunk)
        span = chunk["high"].max() - chunk["low"].min()
        pad = span * 0.03

        beng_valid = np.full(len(chunk), np.nan)
        beng_invalid = np.full(len(chunk), np.nan)
        trigger_vals = np.full(len(chunk), np.nan)
        annotations = []

        for i in sorted(members):
            pos = i - offset
            invalid = is_invalidated(i)
            (beng_invalid if invalid else beng_valid)[pos] = chunk["high"].iloc[pos] + pad

            trig_pos = pos - 1
            if trig_pos >= 0:
                trigger_vals[trig_pos] = chunk["low"].iloc[trig_pos] - pad

            if invalid:
                text = invalidation_text(vol_df, i)
            else:
                prev_pct = result["prev_body_pct"].iloc[i - 1]
                open_t, close_t = df["open"].iloc[i], df["close"].iloc[i]
                prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
                open_over_prevclose = open_t / prev_close
                close_over_prevopen = close_t / prev_open
                text = f"prev={prev_pct:.1f}% O/pC={open_over_prevclose:.4f} C/pO={close_over_prevopen:.4f}"
            annotations.append((pos, chunk["high"].iloc[pos] + pad * 3.2, text))

        addplots = []
        used = set()
        if not np.all(np.isnan(beng_valid)):
            addplots.append(mpf.make_addplot(beng_valid, type="scatter", markersize=120, marker="v", color="purple"))
            used.add("valid")
        if not np.all(np.isnan(beng_invalid)):
            addplots.append(mpf.make_addplot(beng_invalid, type="scatter", markersize=120, marker="v", color="gray", alpha=0.4))
            used.add("invalid")
        if not np.all(np.isnan(trigger_vals)):
            addplots.append(mpf.make_addplot(trigger_vals, type="scatter", markersize=100, marker="^", color="blue"))
            used.add("trigger")

        start_date = chunk["open_time"].iloc[0].date()
        end_date = chunk["open_time"].iloc[-1].date()
        title = f"BTCUSDT 1D  Bearish Engulfing  ({start_date} ~ {end_date})"
        fname = OUT_DIR / f"bearish_engulfing_{w_i + 1:02d}_{start_date}_{end_date}.png"

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

        for pos, y, text in annotations:
            ax.text(pos, y, text, fontsize=6.5, ha="center", va="bottom",
                    fontproperties=KR_FONT, color="black",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))

        legend_map = {
            "valid": ("v", "purple", "bearish_engulfing"),
            "invalid": ("v", "gray", "bearish_engulfing (무효화)"),
            "trigger": ("^", "blue", "트리거(장악당한) 직전 양봉"),
        }
        legend_elems = [
            Line2D([0], [0], marker=m, color=c, linestyle="None", markersize=8, label=lbl)
            for key, (m, c, lbl) in legend_map.items() if key in used
        ]
        if legend_elems:
            ax.legend(handles=legend_elems, loc="upper left", prop=KR_FONT, fontsize=7.5)

        fig.savefig(fname, dpi=130)
        plt.close(fig)
        print(f"저장: {fname}")

    print(f"\n총 {len(windows)}장 생성 완료: {OUT_DIR}")
