"""
시세 분출 (volatility expansion)

급등 직후에는 약세 캔들이 나와도 바로 하락하지 않고 눌림 후 상승하는 경우가
많다. 이런 구간을 판정해서 약세 캔들 신호(doji_at_high, spinning_top_at_high,
bearish_engulfing)를 무효화하는 데 쓴다.

판정 로직:
약세 캔들이 발생한 봉을 t라 할 때, 직전 N봉(N=2,3,4)을 각각 검사한다.
창(window) = [t-N, t-1]. 약세 캔들 t 자신은 계산에 포함하지 않는다.

각 N에 대해 아래 두 조건을 모두 만족하면 그 N에서 시세 분출로 판정:
1. 창 안의 모든 캔들이 양봉 (close > open)
2. cum_pct = (close[t-1] - open[t-N]) / open[t-N] * 100
   cum_pct / N >= CUM_PCT_PER_N_MIN

N=2,3,4 중 하나라도 충족하면 시세 분출 (OR 판정).
실질 임계값: 2봉 전부 양봉+누적 8%↑ / 3봉 전부 양봉+누적 12%↑ / 4봉 전부 양봉+누적 16%↑

의도적으로 제외한 조건 (검토 후 결정, 임의 추가 금지):
- EMA 배열(정배열/역배열) 조건
- 단일 캔들 상승 비율 조건
- 5봉 이상 창
- 거래량 조건
- 창 안 양봉 개수를 "N개 중 M개"로 완화하는 것 (전부 양봉이어야 함)
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_volatility_expansion.parquet"

MIN_WINDOW = 2
MAX_WINDOW = 4
WINDOWS = range(MIN_WINDOW, MAX_WINDOW + 1)
CUM_PCT_PER_N_MIN = 4.0


def compute_volatility_expansion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    n = len(df)
    is_bullish = df["close"] > df["open"]

    any_expansion = [False] * n
    matched_windows = [[] for _ in range(n)]

    for window in WINDOWS:
        bullish_run = [False] * n
        cum_pct = [float("nan")] * n
        cum_pct_per_n = [float("nan")] * n
        expansion = [False] * n

        for t in range(window, n):
            start = t - window
            window_bullish = bool(is_bullish.iloc[start:t].all())
            bullish_run[t] = window_bullish

            open_start = df["open"].iloc[start]
            close_prev = df["close"].iloc[t - 1]
            pct = (close_prev - open_start) / open_start * 100
            cum_pct[t] = pct
            cum_pct_per_n[t] = pct / window

            if window_bullish and cum_pct_per_n[t] >= CUM_PCT_PER_N_MIN:
                expansion[t] = True
                any_expansion[t] = True
                matched_windows[t].append(window)

        df[f"bullish_run_{window}"] = bullish_run
        df[f"cum_pct_{window}"] = cum_pct
        df[f"cum_pct_per_n_{window}"] = cum_pct_per_n
        df[f"expansion_{window}"] = expansion

    df["is_volatility_expansion"] = any_expansion
    df["volatility_expansion_windows"] = matched_windows
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_volatility_expansion(df)

    print(f"시세 분출 판정 개수: {result['is_volatility_expansion'].sum()} / 전체 {len(result)}개")
    for window in WINDOWS:
        print(f"  N={window} 단독 충족: {result[f'expansion_{window}'].sum()}건")

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
