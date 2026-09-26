"""
4-3. 이동평균 배열 판정 (최종 확정 스펙)

- EMA9, EMA20, EMA50, EMA200은 지수이동평균(EMA)으로 계산
  (pandas ewm(span=N, adjust=False), 각 EMA는 자기 기간만큼 데이터가 쌓이기 전에는 NaN 유지)
- "강한 정배열/역배열(EMA200 관여)" 개념은 폐기됨
- 정배열: EMA9 > EMA20 > EMA50 (EMA200 관여 없음)
- 역배열: EMA9 < EMA20 < EMA50 (EMA200 관여 없음)
- 수렴: EMA50이 EMA20 또는 EMA200과 가격(종가) 대비 폭 1.5% 이내. 단, 정배열/역배열이 이미 성립하면 수렴보다 우선
- 혼조: 위 세 가지 중 어느 것도 아닌 경우
- EMA9/EMA20/EMA50 중 하나라도 없는 극초반 구간은 "데이터 부족"(None)

의심 스택 (그날 종가만으로 그날 상태를 독립적으로 계산, 전날 상태에 의존하지 않음. 동률은 의심 아님):
- 정배열 의심 (정배열일 때만 의미 있음, 0~2단계):
    (A) 종가가 EMA9보다 0.5% 이상 아래 마감:  (EMA9 - close) / EMA9 >= 0.5%
    (B) 종가가 EMA20 아래 마감(오차없음):      close < EMA20
  두 항목을 독립적으로 세어 0/1/2로 표시
- 역배열 의심 (역배열일 때만 의미 있음, 0~1단계):
    (C) 종가가 EMA50 위에서 마감(오차없음):    close > EMA50

정배열 의심 래칫 (bullish_suspicion_ratchet, 검증 후 추가):
- 정배열 구간(bullish_state 연속 True) 시작일 = 0단계로 강제
- 이후 매일 max(전날 래칫값, 오늘 스냅샷 bullish_suspicion) - 한번 오르면 구간 끝까지 안 내려감
- 구간이 끝나면(state False) 리셋, 다음 구간에서 다시 0부터
- 정배열이 아닌 날은 None

정배열 해제 trigger (bullish_exit_trigger, 검증 후 추가):
- EMA9>EMA20>EMA50 순서가 깨지는 첫날(전날 bullish_state=True, 오늘 False)에만 True
- 진입 trigger(bullish_trigger)와 대칭 구조, state로 유지되지 않는 1회성 트리거
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
    df["EMA9"] = df["close"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["EMA20"] = df["close"].ewm(span=20, adjust=False, min_periods=20).mean()
    df["EMA50"] = df["close"].ewm(span=50, adjust=False, min_periods=50).mean()
    df["EMA200"] = df["close"].ewm(span=200, adjust=False, min_periods=200).mean()

    regimes = [None] * len(df)
    bullish_susp = [None] * len(df)
    bearish_susp = [None] * len(df)
    bullish_trigger = [False] * len(df)
    bullish_state = [False] * len(df)
    bearish_trigger = [False] * len(df)
    bearish_state = [False] * len(df)
    bullish_suspicion_ratchet = [None] * len(df)
    bullish_exit_trigger = [False] * len(df)

    prev_bullish = False
    prev_bearish = False
    ratchet_max = None

    for i in range(len(df)):
        ma9, ma20, ma50, ma200 = df["EMA9"].iloc[i], df["EMA20"].iloc[i], df["EMA50"].iloc[i], df["EMA200"].iloc[i]
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

        bullish_state[i] = bullish
        bullish_trigger[i] = bullish and not prev_bullish
        bullish_exit_trigger[i] = (not bullish) and prev_bullish
        prev_bullish = bullish

        if bullish:
            if bullish_trigger[i] or ratchet_max is None:
                ratchet_max = 0  # 구간 시작일 = 0단계 강제
            else:
                ratchet_max = max(ratchet_max, bullish_susp[i])
            bullish_suspicion_ratchet[i] = ratchet_max
        else:
            ratchet_max = None

        bearish_state[i] = bearish
        bearish_trigger[i] = bearish and not prev_bearish
        prev_bearish = bearish

    df["ma_regime"] = regimes
    df["bullish_suspicion"] = bullish_susp
    df["bearish_suspicion"] = bearish_susp
    df["bullish_trigger"] = bullish_trigger
    df["bullish_state"] = bullish_state
    df["bearish_trigger"] = bearish_trigger
    df["bearish_state"] = bearish_state
    df["bullish_suspicion_ratchet"] = bullish_suspicion_ratchet
    df["bullish_exit_trigger"] = bullish_exit_trigger
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
