"""
고점 거부 캔들: doji_at_high / spinning_top_at_high

직전 캔들(t-1)이 3.5% 이상 큰 양봉으로 상승했는데, 이번 캔들이 그 상승을
이어가지 못하고 방향성 없는 캔들로 마감하는 경우를 잡는다. 매도(숏) 고려 신호.

공통 조건:
- prev_body_pct = (종가[t-1] - 시가[t-1]) / 시가[t-1] * 100 (부호 있는 값, 절대값 아님)
- prev_body_pct >= 3.5 (직전 캔들이 음봉이면 무조건 제외)

몸통 비율 (이번 캔들 t):
- body_ratio = |종가[t] - 시가[t]| / (고가[t] - 저가[t]) * 100
- 고가==저가(range 0)인 경우 0으로 나누기 방지를 위해 해당 캔들은 신호 대상에서 제외

신호 (모두 trigger - 해당 캔들에서만 발화, state로 유지되지 않음):
- doji_at_high: body_ratio <= 15 -> 숏
- spinning_top_at_high: 15 < body_ratio <= 40 -> 숏

두 구간은 겹치지 않으므로 한 캔들이 동시에 두 신호로 잡히는 일은 없다 (__main__에서 검증).
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_doji_spinning_top_at_high.parquet"

PREV_BODY_MIN_PCT = 3.5
DOJI_BODY_MAX_PCT = 15
SPINNING_TOP_BODY_MAX_PCT = 40


def compute_doji_spinning_top_at_high(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    prev_body_pct = (df["close"] - df["open"]) / df["open"] * 100
    candle_range = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()

    nonzero_range = candle_range != 0
    body_ratio = pd.Series(0.0, index=df.index)
    body_ratio[nonzero_range] = body[nonzero_range] / candle_range[nonzero_range] * 100

    df["prev_body_pct"] = prev_body_pct
    df["body_ratio"] = body_ratio

    is_doji_at_high = [False] * len(df)
    is_spinning_top_at_high = [False] * len(df)

    for i in range(1, len(df)):
        if prev_body_pct.iloc[i - 1] < PREV_BODY_MIN_PCT:
            continue
        if not nonzero_range.iloc[i]:
            continue  # 고가==저가: 0으로 나누기 방지, 신호 제외

        ratio = body_ratio.iloc[i]
        if ratio <= DOJI_BODY_MAX_PCT:
            is_doji_at_high[i] = True
        elif ratio <= SPINNING_TOP_BODY_MAX_PCT:
            is_spinning_top_at_high[i] = True

    df["is_doji_at_high"] = is_doji_at_high
    df["is_spinning_top_at_high"] = is_spinning_top_at_high
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_doji_spinning_top_at_high(df)

    doji_count = result["is_doji_at_high"].sum()
    spin_count = result["is_spinning_top_at_high"].sum()
    overlap = int((result["is_doji_at_high"] & result["is_spinning_top_at_high"]).sum())

    print(f"doji_at_high 개수: {doji_count} / 전체 {len(result)}개")
    print(f"spinning_top_at_high 개수: {spin_count} / 전체 {len(result)}개")
    print(f"중첩(둘 다 True) 개수: {overlap}건")
    assert overlap == 0, "doji_at_high와 spinning_top_at_high는 겹치면 안 된다 (body_ratio 구간 배타적)"

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
