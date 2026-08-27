"""
4-8. RSI 다이버전스 (v3 - 트레이딩뷰 표준 방식 이식)

참고 원본: https://github.com/iamc1oud/Tradingview-Scripts/blob/master/rsi-indicator.pine
(MPL-2.0, 원작 (c) systemalphatrader) - RSI pivot 기반 다이버전스 판정 로직을 이식.

절차 (기존 "가격 스윙 ↔ RSI 스윙 짝짓기" 방식은 폐기):
1. RSI 자체의 pivot(rsi_swings.py, lbL=lbR=5)만 사용. 가격 쪽은 별도 스윙 탐지 없이,
   RSI pivot이 확정된 바로 그 캔들의 그날 저가/고가를 그대로 사용
2. 직전 RSI pivot과 이번 RSI pivot, 딱 1쌍만 비교 (그 사이 다른 pivot은 보지 않음)
3. 두 pivot 사이 캔들 간격이 5~60봉 사이여야 인정 (너무 가까우면 노이즈, 너무 멀면
   무의미한 비교로 간주 - 원본 그대로 적용)
4. 70/30(또는 65/35) 기준선은 다이버전스 판정에서 완전히 분리 - 정상/은닉 모두
   pivot 방향 비교만으로 판정 (기준선은 RSI<=25/>=80 별도 신호에서만 사용, rsi.py 참고)

4가지 유형 (모두 기준선 없음):
- 정상 강세: 이번 RSI저점 확정 캔들의 저가 < 직전 RSI저점 확정 캔들의 저가 (가격 LL)
            + 이번 RSI저점 > 직전 RSI저점 (RSI HL)
- 정상 약세: 이번 RSI고점 확정 캔들의 고가 > 직전 RSI고점 확정 캔들의 고가 (가격 HH)
            + 이번 RSI고점 < 직전 RSI고점 (RSI LH)
- 은닉 강세: 이번 RSI저점 확정 캔들의 저가 > 직전 RSI저점 확정 캔들의 저가 (가격 HL)
            + 이번 RSI저점 < 직전 RSI저점 (RSI LL)
- 은닉 약세: 이번 RSI고점 확정 캔들의 고가 < 직전 RSI고점 확정 캔들의 고가 (가격 LH)
            + 이번 RSI고점 > 직전 RSI고점 (RSI HH)
- 가격 또는 RSI가 직전과 정확히 같으면(동률) 다이버전스 아님(스킵)

회귀분석(slope, r²)/각도 제한/cross-check 등 추가 조건 없음 (단순 신호 탐지 원칙 유지)
"""
from pathlib import Path

import pandas as pd

RSI_SWINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_rsi_swings.parquet"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "merged" / "BTCUSDT_1d_divergence.parquet"

GAP_MIN = 5
GAP_MAX = 60


def compute_divergences(df: pd.DataFrame):
    df = df.reset_index(drop=True)
    events = []
    excluded_by_gap = []

    high_idx = df.index[df["rsi_swing_high"]].tolist()
    for i in range(1, len(high_idx)):
        prev_idx, curr_idx = high_idx[i - 1], high_idx[i]
        gap = curr_idx - prev_idx

        price_prev, price_curr = df["high"].iloc[prev_idx], df["high"].iloc[curr_idx]
        rsi_prev, rsi_curr = df["rsi"].iloc[prev_idx], df["rsi"].iloc[curr_idx]

        if price_curr > price_prev and rsi_curr < rsi_prev:
            kind = "regular_bearish"
        elif price_curr < price_prev and rsi_curr > rsi_prev:
            kind = "hidden_bearish"
        else:
            continue

        if not (GAP_MIN <= gap <= GAP_MAX):
            excluded_by_gap.append({
                "open_time": df["open_time"].iloc[curr_idx], "type": kind, "gap": gap,
                "prev_index": prev_idx, "index": curr_idx,
            })
            continue

        events.append({
            "index": curr_idx, "open_time": df["open_time"].iloc[curr_idx], "type": kind,
            "rsi": rsi_curr, "prev_rsi": rsi_prev, "price": price_curr, "prev_price": price_prev,
            "prev_index": prev_idx, "gap": gap,
            "rsi_swing_index": curr_idx, "prev_rsi_swing_index": prev_idx,
        })

    low_idx = df.index[df["rsi_swing_low"]].tolist()
    for i in range(1, len(low_idx)):
        prev_idx, curr_idx = low_idx[i - 1], low_idx[i]
        gap = curr_idx - prev_idx

        price_prev, price_curr = df["low"].iloc[prev_idx], df["low"].iloc[curr_idx]
        rsi_prev, rsi_curr = df["rsi"].iloc[prev_idx], df["rsi"].iloc[curr_idx]

        if price_curr < price_prev and rsi_curr > rsi_prev:
            kind = "regular_bullish"
        elif price_curr > price_prev and rsi_curr < rsi_prev:
            kind = "hidden_bullish"
        else:
            continue

        if not (GAP_MIN <= gap <= GAP_MAX):
            excluded_by_gap.append({
                "open_time": df["open_time"].iloc[curr_idx], "type": kind, "gap": gap,
                "prev_index": prev_idx, "index": curr_idx,
            })
            continue

        events.append({
            "index": curr_idx, "open_time": df["open_time"].iloc[curr_idx], "type": kind,
            "rsi": rsi_curr, "prev_rsi": rsi_prev, "price": price_curr, "prev_price": price_prev,
            "prev_index": prev_idx, "gap": gap,
            "rsi_swing_index": curr_idx, "prev_rsi_swing_index": prev_idx,
        })

    result = pd.DataFrame(events).sort_values("index").reset_index(drop=True)
    excluded = pd.DataFrame(excluded_by_gap).sort_values("open_time").reset_index(drop=True) if excluded_by_gap else pd.DataFrame(excluded_by_gap)
    return result, excluded


if __name__ == "__main__":
    rsi_swings = pd.read_parquet(RSI_SWINGS_PATH)

    result, excluded = compute_divergences(rsi_swings)
    print(result["type"].value_counts())
    print()
    print(result[["open_time", "type", "rsi", "prev_rsi", "price", "prev_price", "gap"]].to_string())

    print()
    print(f"간격(5~60봉) 벗어나 제외된 케이스: {len(excluded)}건")
    if len(excluded):
        print(excluded.to_string())

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
