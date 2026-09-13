"""
volatility_expansion 무효화 필터 검증용 리포트 스크립트 (일회성 분석, pipeline에서 안 씀).

1. 2022-01-01 이후 시세 분출 판정 건수/날짜/걸린 창(N) 목록
2. 약세 신호 3종의 필터 적용 전/무효화/최종 건수 비교
3. 무효화된 케이스별 날짜/신호명/N/cum_pct/cum_pct_per_n + 이후 5봉 수익률/최대 상승폭/최대 하락폭
"""
from pathlib import Path

import pandas as pd

import bearish_engulfing
import doji_spinning_top_at_high
import pipeline
import volatility_expansion
from data_fetcher import ensure_fresh_data

FORWARD_N = 5
REPORT_START = "2022-01-01"


def _forward_stats(df: pd.DataFrame, i: int, n_bars: int = FORWARD_N):
    """i번째 캔들 종가 기준 이후 n_bars봉 수익률/최대 상승폭/최대 하락폭 (%)."""
    last = len(df) - 1
    end = min(i + n_bars, last)
    if end <= i:
        return None, None, None

    base_close = df["close"].iloc[i]
    fwd_close = df["close"].iloc[end]
    fwd_high = df["high"].iloc[i + 1 : end + 1].max()
    fwd_low = df["low"].iloc[i + 1 : end + 1].min()

    ret_pct = (fwd_close - base_close) / base_close * 100
    max_up_pct = (fwd_high - base_close) / base_close * 100
    max_down_pct = (fwd_low - base_close) / base_close * 100
    return ret_pct, max_up_pct, max_down_pct


def main():
    base_df = ensure_fresh_data().reset_index(drop=True)

    # --- 1. 시세 분출 판정 건수/날짜/창(N) ---
    vol_exp_df = volatility_expansion.compute_volatility_expansion(base_df)
    report_mask = base_df["open_time"] >= REPORT_START
    exp_rows = vol_exp_df.index[vol_exp_df["is_volatility_expansion"] & report_mask]

    print("=" * 70)
    print(f"1. 시세 분출 판정 ({REPORT_START} 이후): 총 {len(exp_rows)}건")
    print("=" * 70)
    for i in exp_rows:
        windows = vol_exp_df["volatility_expansion_windows"].iloc[i]
        date = base_df["open_time"].iloc[i].date()
        detail = ", ".join(
            f"N={w} cum={vol_exp_df[f'cum_pct_{w}'].iloc[i]:.2f}% (/N={vol_exp_df[f'cum_pct_per_n_{w}'].iloc[i]:.2f})"
            for w in windows
        )
        print(f"  {date}  matched N={windows}  [{detail}]")

    # --- 2. 필터 적용 전/후 비교 ---
    rejection_df = doji_spinning_top_at_high.compute_doji_spinning_top_at_high(base_df)
    bearish_engulfing_df = bearish_engulfing.compute_bearish_engulfing(base_df)

    raw_counts = {
        "doji_at_high": int(rejection_df["is_doji_at_high"].sum()),
        "spinning_top_at_high": int(rejection_df["is_spinning_top_at_high"].sum()),
        "bearish_engulfing": int(bearish_engulfing_df["is_bearish_engulfing"].sum()),
    }

    invalidated_log = []
    signals = pipeline.build_signals_by_date(base_df, invalidated_log=invalidated_log)

    final_counts = {
        "doji_at_high": 0,
        "spinning_top_at_high": 0,
        "bearish_engulfing": 0,
    }
    text_to_key = {
        "고점 도지 (거부 캔들) - 숏 신호": "doji_at_high",
        "고점 스피닝탑 (거부 캔들) - 숏 신호": "spinning_top_at_high",
        "장악형 하락 - 숏 신호": "bearish_engulfing",
    }
    for sigs in signals.values():
        for s in sigs:
            key = text_to_key.get(s.text)
            if key:
                final_counts[key] += 1

    # 같은 (index, signal_text) 쌍이 N=2,3,4 여러 창에 동시에 걸리면 invalidated_log에
    # 여러 줄이 기록되므로, "무효화된 신호 발생 건수"는 (index, signal_text) 기준 unique로 센다.
    invalidated_unique = {(rec["index"], rec["signal_text"]) for rec in invalidated_log}
    invalidated_counts = {
        "doji_at_high": 0,
        "spinning_top_at_high": 0,
        "bearish_engulfing": 0,
    }
    for _, text in invalidated_unique:
        key = text_to_key.get(text)
        if key:
            invalidated_counts[key] += 1

    print()
    print("=" * 70)
    print("2. 약세 신호 3종 필터 전/후 비교")
    print("=" * 70)
    print(f"{'신호':30s} {'필터 전':>8s} {'무효화':>8s} {'최종':>8s}")
    for key, label in [
        ("doji_at_high", "doji_at_high"),
        ("spinning_top_at_high", "spinning_top_at_high"),
        ("bearish_engulfing", "bearish_engulfing"),
    ]:
        print(f"{label:30s} {raw_counts[key]:8d} {invalidated_counts[key]:8d} {final_counts[key]:8d}")
        assert raw_counts[key] == invalidated_counts[key] + final_counts[key], f"{key} 건수 불일치"

    # --- 3. 무효화된 케이스 상세 + 이후 5봉 성과 ---
    print()
    print("=" * 70)
    print(f"3. 무효화된 케이스 상세 (이후 {FORWARD_N}봉 성과)")
    print("=" * 70)
    header = f"{'날짜':12s} {'신호':28s} {'N':>3s} {'cum_pct':>9s} {'cum/N':>8s} {'fwd_ret%':>9s} {'fwd_up%':>9s} {'fwd_dn%':>9s}"
    print(header)
    for rec in sorted(invalidated_log, key=lambda r: (r["index"], r["n"])):
        i = rec["index"]
        ret_pct, max_up_pct, max_down_pct = _forward_stats(base_df, i)
        ret_str = f"{ret_pct:9.2f}" if ret_pct is not None else f"{'N/A':>9s}"
        up_str = f"{max_up_pct:9.2f}" if max_up_pct is not None else f"{'N/A':>9s}"
        dn_str = f"{max_down_pct:9.2f}" if max_down_pct is not None else f"{'N/A':>9s}"
        date = rec["date"].date()
        print(
            f"{str(date):12s} {rec['signal_text']:28s} {rec['n']:3d} "
            f"{rec['cum_pct']:9.2f} {rec['cum_pct_per_n']:8.2f} {ret_str} {up_str} {dn_str}"
        )

    print()
    print(f"무효화 총 기록 수(창 중복 포함): {len(invalidated_log)}건 "
          f"/ unique (index,signal) 기준: {len(invalidated_unique)}건")


if __name__ == "__main__":
    main()
