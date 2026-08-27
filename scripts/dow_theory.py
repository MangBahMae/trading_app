"""
4-2. 다우이론 (HH / LH / HL / LL)

규칙 (킥오프 문서 4-2):
- 4-1에서 찾은 "확정된" 스윙 포인트들을 시간순(confirmed 순서 = 캔들 순서와 동일)으로 나열
- 새로운 스윙 하이가 확정될 때마다, 직전 스윙 하이 1개와만 비교 -> 더 높으면 HH, 더 낮으면 LH
- 새로운 스윙 로우가 확정될 때마다, 직전 스윙 로우 1개와만 비교 -> 더 높으면 HL, 더 낮으면 LL
- HH/LH/HL/LL은 각각 독립적인 개별 이벤트로 기록 (종합 추세 라벨 없음)
- 맨 처음 나오는 스윙 하이/로우는 비교 대상이 없으므로 라벨 없음(label=None)
"""
from pathlib import Path

import pandas as pd

SWINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_swings.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_dow.parquet"


def compute_dow_events(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    events = []
    ties = []

    swing_highs = df[df["swing_high"]]
    prev_high = None
    for idx, row in swing_highs.iterrows():
        label = None
        if prev_high is not None:
            if row["high"] > prev_high["high"]:
                label = "HH"
            elif row["high"] < prev_high["high"]:
                label = "LH"
            else:
                ties.append(("high", idx, prev_high.name))
        events.append({
            "index": idx,
            "open_time": row["open_time"],
            "confirmed_at": row["confirmed_at"],
            "kind": "high",
            "price": row["high"],
            "label": label,
        })
        prev_high = row

    swing_lows = df[df["swing_low"]]
    prev_low = None
    for idx, row in swing_lows.iterrows():
        label = None
        if prev_low is not None:
            if row["low"] > prev_low["low"]:
                label = "HL"
            elif row["low"] < prev_low["low"]:
                label = "LL"
            else:
                ties.append(("low", idx, prev_low.name))
        events.append({
            "index": idx,
            "open_time": row["open_time"],
            "confirmed_at": row["confirmed_at"],
            "kind": "low",
            "price": row["low"],
            "label": label,
        })
        prev_low = row

    if ties:
        print("경고: 스펙에 정의되지 않은 동률(직전 스윙과 정확히 같은 가격) 발견 -> label=None 처리됨")
        for kind, idx, prev_idx in ties:
            print(f"  - {kind}: index {prev_idx} vs {idx}")

    events_df = pd.DataFrame(events).sort_values("index").reset_index(drop=True)
    return events_df


if __name__ == "__main__":
    df = pd.read_parquet(SWINGS_PATH)
    events = compute_dow_events(df)

    counts = events["label"].value_counts(dropna=False)
    print(counts)

    events.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
