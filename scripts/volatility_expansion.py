"""
시세 분출 (volatility expansion)

급등 직후에는 약세 캔들이 나와도 바로 하락하지 않고 눌림 후 상승하는 경우가
많다. 이런 구간을 판정해서 약세 캔들 신호(doji_at_high, spinning_top_at_high,
bearish_engulfing)를 무효화하는 데 쓴다.

판정 로직 (실측 검증 후 재조정, 이전 버전: N=2,3,4 + 전부양봉):
약세 캔들이 발생한 봉을 t라 할 때, 직전 N봉(N=3,4)을 각각 검사한다.
창(window) = [t-N, t-1]. 약세 캔들 t 자신은 계산에 포함하지 않는다.

각 N에 대해 아래 조건을 만족하면 그 N에서 시세 분출로 판정:
cum_pct = (close[t-1] - open[t-N]) / open[t-N] * 100
cum_pct / N >= CUM_PCT_PER_N_MIN

N=3,4 중 하나라도 충족하면 시세 분출 (OR 판정).
실질 임계값: 3봉 누적 12%↑ / 4봉 누적 16%↑

이전 버전 대비 변경점 (실측 시뮬레이션+차트 육안 확인 후 결정):
- N=2 제외: 2봉 단독 매치가 기존 38건 중 23건으로 대부분을 차지했는데,
  직전 큰 하락에서의 단순 반등 초입을 "급등"으로 오인하는 애매한 케이스가
  섞여 있었음(예: 2024-03-26 - 3/14~21 대하락 후 이틀 반등을 급등으로 판정).
- "창 안 전부 양봉" 조건 삭제: 색깔 섞인 계단식 상승(예: 2022-02-06,
  양봉-음봉-양봉이어도 누적으로는 급등)을 놓치고 있었던 것으로 확인돼서 제거.
  실질적으로 cum_pct_per_n만으로 판정.

의도적으로 제외한 조건 (검토 후 결정, 임의 추가 금지):
- EMA 배열(정배열/역배열) 조건
- 단일 캔들 상승 비율 조건
- 5봉 이상 창
- 거래량 조건
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_volatility_expansion.parquet"

MIN_WINDOW = 3
MAX_WINDOW = 4
WINDOWS = range(MIN_WINDOW, MAX_WINDOW + 1)
CUM_PCT_PER_N_MIN = 4.0


def compute_volatility_expansion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    n = len(df)

    any_expansion = [False] * n
    matched_windows = [[] for _ in range(n)]

    for window in WINDOWS:
        cum_pct = [float("nan")] * n
        cum_pct_per_n = [float("nan")] * n
        expansion = [False] * n

        for t in range(window, n):
            start = t - window
            open_start = df["open"].iloc[start]
            close_prev = df["close"].iloc[t - 1]
            pct = (close_prev - open_start) / open_start * 100
            cum_pct[t] = pct
            cum_pct_per_n[t] = pct / window

            if cum_pct_per_n[t] >= CUM_PCT_PER_N_MIN:
                expansion[t] = True
                any_expansion[t] = True
                matched_windows[t].append(window)

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
