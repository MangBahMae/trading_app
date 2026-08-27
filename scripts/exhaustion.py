"""
4-6. 매물소진 패턴 (신규 커스텀 조건)

판정식 (도지와 다름, 등락률 방식):
    change_pct = |종가 - 시가| / 시가 * 100

조건 (모두 만족):
- 직전 캔들의 change_pct >= 3.5%
- 이번 캔들의 change_pct <= 직전 캔들 change_pct의 절반
- 이번 캔들 거래량 >= 직전 캔들 거래량의 50% (상한 없음)

방향: 이번 캔들 방향은 무관. 직전 캔들이 음봉(종가<시가)이면 매수 신호,
     양봉(종가>시가)이면 매도 신호 (대칭 적용)

도지 조건과는 완전히 독립적으로 계산 (중첩 허용)
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_exhaustion.parquet"

PREV_MIN_PCT = 3.5
VOLUME_MIN_RATIO = 0.5


def compute_exhaustion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    change_pct = (df["close"] - df["open"]).abs() / df["open"] * 100
    df["change_pct"] = change_pct

    signals = [None] * len(df)

    for i in range(1, len(df)):
        prev_pct = change_pct.iloc[i - 1]
        curr_pct = change_pct.iloc[i]
        prev_vol = df["volume"].iloc[i - 1]
        curr_vol = df["volume"].iloc[i]

        if prev_pct < PREV_MIN_PCT:
            continue
        if curr_pct > prev_pct / 2:
            continue
        if curr_vol < prev_vol * VOLUME_MIN_RATIO:
            continue

        prev_open, prev_close = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
        if prev_close < prev_open:
            signals[i] = "buy"   # 직전 음봉 -> 매수 신호
        elif prev_close > prev_open:
            signals[i] = "sell"  # 직전 양봉 -> 매도 신호
        # prev_close == prev_open 이면 prev_pct == 0 이라 위에서 이미 걸러짐

    df["exhaustion_signal"] = signals
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_exhaustion(df)

    counts = result["exhaustion_signal"].value_counts(dropna=True)
    print(counts)

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
