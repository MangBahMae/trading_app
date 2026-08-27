"""
4-3. 이동평균 배열 판정 (최종 확정 스펙)

- MA9, MA20, MA50, MA200은 지수이동평균(EMA)으로 계산
  (pandas ewm(span=N, adjust=False), 각 MA는 자기 기간만큼 데이터가 쌓이기 전에는 NaN 유지)
- "강한 정배열/역배열(MA200 관여)" 개념은 폐기됨
- 정배열: MA9 > MA20 > MA50 (MA200 관여 없음)
- 역배열: MA9 < MA20 < MA50 (MA200 관여 없음)
- 수렴: MA50이 MA20 또는 MA200과 가격(종가) 대비 폭 1.5% 이내. 단, 정배열/역배열이 이미 성립하면 수렴보다 우선
- 혼조: 위 세 가지 중 어느 것도 아닌 경우
- MA9/MA20/MA50 중 하나라도 없는 극초반 구간은 "데이터 부족"(None)

의심 스택 (그날 종가만으로 그날 상태를 독립적으로 계산, 전날 상태에 의존하지 않음. 동률은 의심 아님):
- 정배열 의심 (정배열일 때만 의미 있음, 0~2단계):
    (A) 종가가 MA9보다 0.5% 이상 아래 마감:  (MA9 - close) / MA9 >= 0.5%
    (B) 종가가 MA20 아래 마감(오차없음):      close < MA20
  두 항목을 독립적으로 세어 0/1/2로 표시
- 역배열 의심 (역배열일 때만 의미 있음, 0~1단계):
    (C) 종가가 MA50 위에서 마감(오차없음):    close > MA50
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_ma_regime.parquet"

CONVERGENCE_PCT = 0.015
BULLISH_SUSPICION_A_PCT = 0.005


def compute_ma_regime(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    df["MA9"] = df["close"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["MA20"] = df["close"].ewm(span=20, adjust=False, min_periods=20).mean()
    df["MA50"] = df["close"].ewm(span=50, adjust=False, min_periods=50).mean()
    df["MA200"] = df["close"].ewm(span=200, adjust=False, min_periods=200).mean()

    regimes = [None] * len(df)
    bullish_susp = [None] * len(df)
    bearish_susp = [None] * len(df)

    for i in range(len(df)):
        ma9, ma20, ma50, ma200 = df["MA9"].iloc[i], df["MA20"].iloc[i], df["MA50"].iloc[i], df["MA200"].iloc[i]
        close = df["close"].iloc[i]

        if pd.isna(ma9) or pd.isna(ma20) or pd.isna(ma50):
            continue  # 데이터 부족 -> None 유지

        has_ma200 = not pd.isna(ma200)

        bullish = ma9 > ma20 > ma50
        bearish = ma9 < ma20 < ma50

        if bullish:
            regimes[i] = "bullish"
        elif bearish:
            regimes[i] = "bearish"
        else:
            conv = abs(ma50 - ma20) / close <= CONVERGENCE_PCT
            if has_ma200:
                conv = conv or (abs(ma50 - ma200) / close <= CONVERGENCE_PCT)
            regimes[i] = "convergence" if conv else "mixed"

        # 의심 스택: 그날 종가/MA만으로 독립 계산 (전날 상태 참조 없음)
        cond_a = (ma9 - close) / ma9 >= BULLISH_SUSPICION_A_PCT
        cond_b = close < ma20
        bullish_susp[i] = int(cond_a) + int(cond_b)

        cond_c = close > ma50
        bearish_susp[i] = int(cond_c)

    df["ma_regime"] = regimes
    df["bullish_suspicion"] = bullish_susp
    df["bearish_suspicion"] = bearish_susp
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_ma_regime(df)

    print(result["ma_regime"].value_counts(dropna=False))
    print()
    print("정배열 구간의 의심 단계 분포:")
    print(result.loc[result["ma_regime"] == "bullish", "bullish_suspicion"].value_counts().sort_index())
    print()
    print("역배열 구간의 의심 단계 분포:")
    print(result.loc[result["ma_regime"] == "bearish", "bearish_suspicion"].value_counts().sort_index())

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
