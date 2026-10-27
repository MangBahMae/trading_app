"""
시장 상태(상승 / 하락 / 횡보) 라벨 - 차트 배경 음영 전용.

신호가 아니다: 롱/숏 카운트에 들어가지 않고, 기존 신호 모듈(pipeline, ma_regime,
sr_touch ...)을 import하지도 않는다. 입력은 확정 캔들의 종가와 EMA9/20/50 컬럼뿐이며
(EMA 값은 호출하는 쪽이 ma_regime가 이미 계산한 것을 그대로 넘긴다), 캔들 t의 판정은
t 시점 이하의 값만 쓴다(미래 참조 없음 - tests/test_market_state.py가 "t까지 잘라서
돌린 결과 == 전체로 돌린 t번째 결과"로 증명한다).

캔들별 판정 (N=창 길이, K=교차 기준):
  A (꼬임)       EMA 9>20>50도 아니고 9<20<50도 아님
  B (간격 축소)  |EMA9-EMA50|(t) < |EMA9-EMA50|(t-N)           (엄격한 <)
  C (9 교차)     최근 N봉(t-N+1..t의 종가 N개)에서 "종가가 EMA9 위 <-> 아래"로 바뀐 횟수 >= K
                 (N개 종가 안의 전환은 최대 N-1번. 종가 == EMA9인 날은 직전 쪽을 유지)
  횡보          = A 또는 (B 그리고 C)
  횡보 아님 + 정배열(9>20>50) -> 상승 / 횡보 아님 + 역배열(9<20<50) -> 하락
  reason        A가 해당하면 "A"(B&C도 같이 해당해도 A 우선), A는 아니고 B&C면 "BC", 그 외 "없음"

데이터 부족: EMA50이 아직 없는 앞 49봉은 state=None(데이터 부족). EMA50은 있지만 N봉 이력이
모자라 B나 C를 못 구하는 구간은 그 항목을 False로 보고 A만으로 판정한다.
"""
from statistics import median

import numpy as np
import pandas as pd

DEFAULT_N = 10
DEFAULT_K = 4

STATE_UP = "상승"
STATE_DOWN = "하락"
STATE_SIDEWAYS = "횡보"
STATE_INSUFFICIENT = "데이터 부족"

REASON_A = "A"
REASON_BC = "BC"
REASON_NONE = "없음"


def validate_params(n: int, k: int) -> None:
    if n < 1:
        raise ValueError("n은 1 이상이어야 함")
    if k < 0 or k > n:
        raise ValueError("k는 0 이상 n 이하여야 함")


def compute_market_state(df: pd.DataFrame, n: int = DEFAULT_N, k: int = DEFAULT_K) -> pd.DataFrame:
    """df: close, EMA9, EMA20, EMA50 컬럼(캔들 오름차순, 연속 행). 같은 인덱스의 결과 반환.

    결과 컬럼: state, reason, a, b, c, gap_now, gap_prev, cross_count
      (state/reason은 데이터 부족이면 None, gap_prev/cross_count는 구할 수 없으면 NaN)
    """
    validate_params(n, k)

    close = df["close"].astype(float)
    e9, e20, e50 = df["EMA9"].astype(float), df["EMA20"].astype(float), df["EMA50"].astype(float)

    valid = e9.notna() & e20.notna() & e50.notna()
    bull = valid & (e9 > e20) & (e20 > e50)
    bear = valid & (e9 < e20) & (e20 < e50)
    a = valid & ~bull & ~bear

    gap_now = (e9 - e50).abs()
    gap_prev = gap_now.shift(n)
    b = valid & gap_prev.notna() & (gap_now < gap_prev)

    # C: 종가가 EMA9의 위(+1)/아래(-1). 같은 날은 직전 쪽을 유지(0을 NaN으로 바꿔 앞으로 채움).
    side = np.sign(close - e9).where(e9.notna())
    side = side.where(side != 0).ffill().where(e9.notna())
    flip = (side != side.shift(1)).astype(float).where(side.notna() & side.shift(1).notna())
    if n >= 2:
        cross_count = flip.rolling(n - 1, min_periods=n - 1).sum()
    else:
        cross_count = pd.Series(0.0, index=df.index).where(side.notna())
    c = valid & cross_count.notna() & (cross_count >= k)

    sideways = a | (b & c)
    state = pd.Series(STATE_DOWN, index=df.index, dtype=object)
    state[bull] = STATE_UP
    state[sideways] = STATE_SIDEWAYS
    state[~valid] = None

    reason = pd.Series(REASON_NONE, index=df.index, dtype=object)
    reason[b & c] = REASON_BC
    reason[a] = REASON_A  # A 우선
    reason[~valid] = None

    return pd.DataFrame({
        "state": state, "reason": reason, "a": a, "b": b, "c": c,
        "gap_now": gap_now.where(valid), "gap_prev": gap_prev.where(valid),
        "cross_count": cross_count.where(valid),
    })


def find_blocks(states: pd.DataFrame, dates: list[str]) -> list[dict]:
    """연속된 횡보 캔들 블록 목록. reason이 바뀌면(A <-> BC) 다른 블록으로 나눈다(음영 색이 달라서).
    states와 dates는 같은 길이/순서. 반환: [{"start","end","length","reason"}, ...] 시간순."""
    blocks: list[dict] = []
    cur: dict | None = None
    for i, (st, rs) in enumerate(zip(states["state"].tolist(), states["reason"].tolist())):
        if st == STATE_SIDEWAYS:
            if cur is not None and cur["reason"] == rs and cur["_last"] == i - 1:
                cur["end"], cur["length"], cur["_last"] = dates[i], cur["length"] + 1, i
            else:
                if cur is not None:
                    blocks.append(cur)
                cur = {"start": dates[i], "end": dates[i], "length": 1, "reason": rs, "_last": i}
        elif cur is not None:
            blocks.append(cur)
            cur = None
    if cur is not None:
        blocks.append(cur)
    for blk in blocks:
        blk.pop("_last")
    return blocks


def summarize(states: pd.DataFrame, blocks: list[dict]) -> dict:
    """상태별 캔들 수/비율, 횡보 중 reason별, 횡보 블록 길이 분포(min/median/max)."""
    total = len(states)
    state_counts = {
        s: int((states["state"] == s).sum()) for s in (STATE_UP, STATE_DOWN, STATE_SIDEWAYS)
    }
    state_counts[STATE_INSUFFICIENT] = int(states["state"].isna().sum())
    evaluated = total - state_counts[STATE_INSUFFICIENT]

    side = states[states["state"] == STATE_SIDEWAYS]
    reason_counts = {r: int((side["reason"] == r).sum()) for r in (REASON_A, REASON_BC)}

    lengths = [blk["length"] for blk in blocks]
    length_stats = (
        {"min": min(lengths), "median": median(lengths), "max": max(lengths)} if lengths else None
    )
    return {
        "total": total,
        "evaluated": evaluated,
        "state_counts": state_counts,
        "reason_counts": reason_counts,
        "sideways_total": len(side),
        "block_count": len(blocks),
        "block_length_stats": length_stats,
    }


def _pct(part: int, whole: int) -> str:
    return f"{part / whole * 100:5.1f}%" if whole else "  n/a"


def format_report(states: pd.DataFrame, blocks: list[dict], dates: list[str], n: int, k: int) -> str:
    s = summarize(states, blocks)
    ev, sw = s["evaluated"], s["sideways_total"]
    lines = [
        f"시장 상태 N={n}, K={k} - 전체 캔들 {s['total']}개 ({dates[0]} ~ {dates[-1]}), "
        f"판정 가능 {ev}개 (앞 {s['state_counts'][STATE_INSUFFICIENT]}개는 EMA50 없음 = 데이터 부족)",
        "",
        "[상태별 캔들 수 / 비율(판정 가능 캔들 기준)]",
    ]
    for st in (STATE_UP, STATE_DOWN, STATE_SIDEWAYS):
        cnt = s["state_counts"][st]
        lines.append(f"  {st}: {cnt:5d}개  {_pct(cnt, ev)}")
    lines += ["", f"[횡보 {sw}개 중 reason별]"]
    for r in (REASON_A, REASON_BC):
        cnt = s["reason_counts"][r]
        lines.append(f"  {r:>2}: {cnt:5d}개  {_pct(cnt, sw)}")
    lines += ["", f"[횡보 블록 {s['block_count']}개 - 길이 분포(봉)]"]
    st = s["block_length_stats"]
    lines.append(
        "  블록 없음" if st is None else f"  최소 {st['min']} / 중앙값 {st['median']} / 최대 {st['max']}"
    )
    lines += ["", "[횡보 블록 목록 (시작일 ~ 종료일, 길이, reason)]"]
    for blk in blocks:
        lines.append(f"  {blk['start']} ~ {blk['end']}  {blk['length']:3d}봉  {blk['reason']}")
    return "\n".join(lines)


if __name__ == "__main__":
    # 전체 기간(2022-01-01~) 검증 출력. EMA는 ma_regime가 계산하는 값을 그대로 쓴다.
    import sys
    from data_fetcher import ensure_fresh_data
    import ma_regime

    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N
    k = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_K

    base = ensure_fresh_data().reset_index(drop=True)
    regime = ma_regime.compute_ma_regime(base)
    result = compute_market_state(regime, n, k)
    all_dates = [d.strftime("%Y-%m-%d") for d in base["open_time"]]
    print(format_report(result, find_blocks(result, all_dates), all_dates, n, k))
