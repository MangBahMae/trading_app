"""
4-5. 도지캔들

판정식 (킥오프 문서 4-5):
    |종가 - 시가| / (고가 - 저가) <= 10%

- 고가==저가(범위 0)인 극단적 경우는 몸통도 반드시 0이 되므로(open=close=high=low),
  0/0 형태가 되지만 몸통이 없다는 의미에서 도지로 판정한다.
"""
from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_doji.parquet"

DOJI_THRESHOLD = 0.10


def compute_doji(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    body = (df["close"] - df["open"]).abs()
    candle_range = df["high"] - df["low"]

    ratio = pd.Series(0.0, index=df.index)
    nonzero_range = candle_range != 0
    ratio[nonzero_range] = body[nonzero_range] / candle_range[nonzero_range]
    # candle_range == 0 인 경우 body도 반드시 0이므로 ratio는 0으로 둔다 (도지로 판정됨)

    df["doji_ratio"] = ratio
    df["is_doji"] = ratio <= DOJI_THRESHOLD
    return df


if __name__ == "__main__":
    df = pd.read_parquet(DATA_PATH)
    result = compute_doji(df)

    print(f"도지캔들 개수: {result['is_doji'].sum()} / 전체 {len(result)}개")

    result.to_parquet(OUT_PATH, index=False)
    print(f"저장 완료: {OUT_PATH}")
