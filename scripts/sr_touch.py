"""
4-4. 이동평균(EMA50/EMA200) 터치/돌파 신호 (재설계 확정 스펙)

- EMA50, EMA200만 대상 (EMA9, EMA20은 대상 아님), 각각 독립적으로 판정
  (한 캔들에서 두 신호가 동시에 나올 수 있음)

공통 전제 조건 - 이걸 만족해야만 신호 후보가 됨(꼬리 포함 접촉):
    touched = (low <= EMA <= high)
    접촉 자체가 없으면(EMA 위/아래에 캔들이 완전히 떨어져 있으면) 무조건 무신호.
    이전 버전에 있던 "0.1% 이내 근접이면 접촉 인정" 같은 여유(tolerance)는 없음 -
    순수하게 캔들 범위가 EMA를 실제로 관통했는지만 본다.

이격률(부호 있음, %): deviation = (close - EMA) / EMA * 100

전제 조건을 만족한 캔들에 한해 이격률로 3구간 판정:
- A. 터치/거부 (|deviation| <= 0.1): 종가가 EMA에 바짝 붙어 마감 - 종가 위치로는
     방향을 알 수 없으므로 몸통 색으로 판정. 양봉(close>open)=EMA 저항→SHORT,
     음봉(close<open)=EMA 지지→LONG, 도지(close==open)=무신호.
- B. 돌파 (|deviation| > 0.5): 몸통 색은 안 쓰고 종가 위치만으로 판정 - 윗꼬리로
     EMA를 찌르고 종가가 EMA 아래로 밀려난 양봉(EMA에 거부당한 캔들)도 종가 기준으로
     SHORT 처리해야 하기 때문. deviation>0.5 -> LONG, deviation<-0.5 -> SHORT.
- C. 회색지대 (0.1 < |deviation| <= 0.5): 무신호.

모두 trigger 신호 (그 캔들에서만 발화, state로 유지되지 않음).
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_ma_regime.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_sr_touch.parquet"

MA_TARGETS = ["MA50", "MA200"]
TOUCH_MAX_PCT = 0.1      # 터치/거부 구간: |이격률| <= 0.1%
BREAKOUT_MIN_PCT = 0.5   # 돌파 구간: |이격률| > 0.5%


def compute_sr_touch(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    for ma_col in MA_TARGETS:
        touch_col = f"{ma_col}_touch"            # bool: 전제 조건(접촉) 충족 여부
        case_col = f"{ma_col}_case"              # None / 'touch_reject' / 'breakout' / 'gray_zone'
        deviation_col = f"{ma_col}_deviation"     # float: (close-EMA)/EMA*100, 접촉 안 했으면 None
        signal_col = f"{ma_col}_signal"          # None / 'long' / 'short'

        touches = [False] * len(df)
        cases = [None] * len(df)
        deviations = [None] * len(df)
        signals = [None] * len(df)

        for i in range(len(df)):
            ma_val = df[ma_col].iloc[i]
            if pd.isna(ma_val):
                continue

            low, high = df["low"].iloc[i], df["high"].iloc[i]
            open_, close = df["open"].iloc[i], df["close"].iloc[i]

            touched = low <= ma_val <= high
            if not touched:
                continue

            touches[i] = True
            deviation = (close - ma_val) / ma_val * 100
            deviations[i] = deviation
            abs_dev = abs(deviation)

            if abs_dev <= TOUCH_MAX_PCT:
                cases[i] = "touch_reject"
                if close > open_:
                    signals[i] = "short"
                elif close < open_:
                    signals[i] = "long"
                # else: 도지 -> 무신호(None 유지)
            elif abs_dev > BREAKOUT_MIN_PCT:
                cases[i] = "breakout"
                signals[i] = "long" if deviation > BREAKOUT_MIN_PCT else "short"
            else:
                cases[i] = "gray_zone"
                # 무신호(None 유지)

        df[touch_col] = touches
        df[case_col] = cases
        df[deviation_col] = deviations
        df[signal_col] = signals

    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_sr_touch(df)

    for ma_col in MA_TARGETS:
        print(f"--- {ma_col} ---")
        touch_col, case_col, signal_col = f"{ma_col}_touch", f"{ma_col}_case", f"{ma_col}_signal"
        print(f"접촉(전제조건 충족): {result[touch_col].sum()}개")
        print(result.loc[result[touch_col], case_col].value_counts(dropna=False))
        print(result.loc[result[signal_col].notna(), signal_col].value_counts())
        print()

    result.to_parquet(OUT_PATH, index=False)
    print(f"저장 완료: {OUT_PATH}")
