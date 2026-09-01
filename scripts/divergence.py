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

import rsi_swings

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


BULLISH_TYPES = {"regular_bullish", "hidden_bullish"}


def compute_divergence_state(rsi_swings_df: pd.DataFrame, events_df: pd.DataFrame) -> pd.DataFrame:
    """확정된 다이버전스마다 state가 유지되는 마지막 캔들 인덱스(state_end_index)를 붙인다.

    해제는 둘 중 먼저 오는 것:
    ① 가격 이탈: 종가가 무효화 가격(다이버전스를 구성한 pivot의 가격 - 강세는 저가,
       약세는 고가 = compute_divergences()가 계산해둔 "price" 컬럼)을 이탈. trigger
       캔들 자체의 종가로는 무효화될 수 없으므로(그 캔들의 저가/고가가 곧 price) 다음
       캔들부터 스캔한다.
    ② 반대 방향 RSI pivot 확정: 강한 추세 구간에서는 ①이 오래도록 안 와서 다이버전스
       state가 수십~백일씩 유지되며 같은 방향 다이버전스가 계속 새로 겹쳐 쌓이는 문제가
       있었음 - 다음 반대 방향 RSI pivot(강세 계열은 다음 고점, 약세 계열은 다음 저점)이
       "확정"되는 시점(pivot 당일 j가 아니라 우측 N봉이 마감돼 확정되는 j+N - rsi_swings.py의
       confirmed_at과 동일한 원칙, look-ahead 방지)에 자동 종료. 아직 데이터 범위 안에서
       확정 안 됐으면(j+N이 마지막 캔들을 넘어가면) 이 조건은 적용하지 않는다.

    두 후보 중 더 빠른(작은) 인덱스를 최종 state_end_index로 채택하고, 어느 쪽이었는지
    end_reason에 "reverse"/"opposite_pivot"로 남긴다. 둘 다 안 왔으면 "ongoing"(진행 중).
    """
    df = rsi_swings_df.reset_index(drop=True)
    n = len(df)
    close = df["close"]

    high_idx = df.index[df["rsi_swing_high"]].tolist()
    low_idx = df.index[df["rsi_swing_low"]].tolist()

    events_df = events_df.copy()
    invalidation_price = []
    state_end_index = []
    end_reason = []

    for _, ev in events_df.iterrows():
        trigger_idx = int(ev["index"])
        price = ev["price"]
        is_bullish = ev["type"] in BULLISH_TYPES

        # ① 가격 이탈
        reverse_end = n - 1
        reverse_found = False
        for j in range(trigger_idx + 1, n):
            broken = close.iloc[j] < price if is_bullish else close.iloc[j] > price
            if broken:
                reverse_end = j - 1
                reverse_found = True
                break

        # ② 반대 방향 RSI pivot 확정
        opposite_pivots = high_idx if is_bullish else low_idx
        next_opposite = next((j for j in opposite_pivots if j > trigger_idx), None)
        opposite_confirm_end = None
        if next_opposite is not None:
            confirm_idx = next_opposite + rsi_swings.N
            if confirm_idx <= n - 1:
                opposite_confirm_end = confirm_idx

        candidates = [(reverse_end, "reverse" if reverse_found else "ongoing")]
        if opposite_confirm_end is not None:
            candidates.append((opposite_confirm_end, "opposite_pivot"))
        end_idx, reason = min(candidates, key=lambda c: c[0])

        invalidation_price.append(price)
        state_end_index.append(end_idx)
        end_reason.append(reason)

    events_df["invalidation_price"] = invalidation_price
    events_df["state_end_index"] = state_end_index
    events_df["end_reason"] = end_reason
    return events_df


if __name__ == "__main__":
    rsi_swings_df = pd.read_parquet(RSI_SWINGS_PATH)

    result, excluded = compute_divergences(rsi_swings_df)
    print(result["type"].value_counts())
    print()
    print(result[["open_time", "type", "rsi", "prev_rsi", "price", "prev_price", "gap"]].to_string())

    print()
    print(f"간격(5~60봉) 벗어나 제외된 케이스: {len(excluded)}건")
    if len(excluded):
        print(excluded.to_string())

    result.to_parquet(OUT_PATH, index=False)
    print(f"\n저장 완료: {OUT_PATH}")
