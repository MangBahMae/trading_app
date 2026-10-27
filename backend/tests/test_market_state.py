"""
시장 상태(상승/하락/횡보, market_state.py) 단위 테스트 + API 테스트.

단위 테스트는 EMA 컬럼을 손으로 만든 가짜 캔들을 쓴다(입력이 EMA 컬럼이라 EMA를 직접 지정 가능).
정배열 기본값: EMA9=130 > EMA20=120 > EMA50=100, 종가는 EMA9(130) 위/아래로 조절.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"
sys.path.insert(0, str(SERVICES_DIR))

import market_state as ms  # noqa: E402
from app.main import app  # noqa: E402

UP, DOWN, SIDE = ms.STATE_UP, ms.STATE_DOWN, ms.STATE_SIDEWAYS
ABOVE, BELOW = 131.0, 129.0  # 종가가 EMA9(130)의 위 / 아래


def _df(closes, e9=None, e20=None, e50=None):
    n = len(closes)

    def col(v, default):
        if v is None:
            return [default] * n
        return list(v)

    return pd.DataFrame({
        "close": closes,
        "EMA9": col(e9, 130.0), "EMA20": col(e20, 120.0), "EMA50": col(e50, 100.0),
    })


# --- A (꼬임) ---

def test_bullish_order_is_up_not_sideways():
    # 종가가 EMA9 한쪽에만 있어 교차 0 - 간격도 일정(B 아님) -> 상승
    r = ms.compute_market_state(_df([ABOVE] * 6), n=3, k=2)
    assert r["state"].tolist() == [UP] * 6
    assert r["reason"].tolist() == [ms.REASON_NONE] * 6
    assert not r["a"].any()


def test_bearish_order_is_down():
    df = _df([BELOW] * 6, e9=[70.0] * 6, e20=[80.0] * 6, e50=[100.0] * 6)
    r = ms.compute_market_state(df, n=3, k=2)
    assert r["state"].tolist() == [DOWN] * 6


def test_twisted_ema_is_sideways_with_reason_a():
    # 9>20 인데 20<50 -> 정배열도 역배열도 아님
    df = _df([ABOVE] * 4, e9=[130.0] * 4, e20=[90.0] * 4, e50=[100.0] * 4)
    r = ms.compute_market_state(df, n=3, k=2)
    assert r["state"].tolist() == [SIDE] * 4
    assert r["reason"].tolist() == [ms.REASON_A] * 4
    assert r["a"].all()


def test_equal_emas_count_as_twisted():
    df = _df([ABOVE] * 3, e9=[100.0] * 3, e20=[100.0] * 3, e50=[100.0] * 3)
    assert ms.compute_market_state(df, n=2, k=1)["state"].tolist() == [SIDE] * 3


# --- B / C / 조합 ---

# 정배열 유지 + 종가가 EMA9를 위/아래로 번갈아(교차 많음) + EMA9-EMA50 간격이 줄어드는 케이스.
SHRINKING_E9 = [150.0, 148.0, 146.0, 144.0, 142.0, 140.0]  # e50=100 고정 -> 간격 50,48,46,44,42,40 (계속 줄어듦)
ALTERNATING = [160.0, 120.0, 160.0, 120.0, 160.0, 120.0]   # EMA9 위/아래 교대


def _bullish_shrinking(closes):
    return _df(closes, e9=SHRINKING_E9, e20=[120.0] * 6, e50=[100.0] * 6)


def test_b_and_c_gives_sideways_with_reason_bc():
    r = ms.compute_market_state(_bullish_shrinking(ALTERNATING), n=3, k=2)
    # t=3 이후: 간격이 3봉 전보다 작고(B), 최근 3봉 종가의 전환 2번(C, K=2)
    row = r.iloc[3]
    assert row["b"] and row["c"] and not row["a"]
    assert (row["state"], row["reason"]) == (SIDE, ms.REASON_BC)
    assert row["cross_count"] == 2
    assert row["gap_now"] == 44.0 and row["gap_prev"] == 50.0


def test_b_without_c_is_not_sideways():
    r = ms.compute_market_state(_bullish_shrinking([ABOVE + 40] * 6), n=3, k=2)  # 교차 0
    row = r.iloc[3]
    assert row["b"] and not row["c"]
    assert (row["state"], row["reason"]) == (UP, ms.REASON_NONE)


def test_c_without_b_is_not_sideways():
    growing = [140.0, 142.0, 144.0, 146.0, 148.0, 150.0]  # 간격이 계속 커짐
    df = _df(ALTERNATING, e9=growing, e20=[120.0] * 6, e50=[100.0] * 6)
    row = ms.compute_market_state(df, n=3, k=2).iloc[3]
    assert row["c"] and not row["b"]
    assert (row["state"], row["reason"]) == (UP, ms.REASON_NONE)


def test_b_requires_strictly_smaller_gap():
    df = _df(ALTERNATING, e9=[140.0] * 6, e20=[120.0] * 6, e50=[100.0] * 6)  # 간격 40으로 동일
    assert not ms.compute_market_state(df, n=3, k=2)["b"].any()


def test_reason_a_wins_over_bc():
    # 꼬임(A)이면서 B와 C도 모두 해당 -> reason은 "A"
    df = _df(ALTERNATING, e9=SHRINKING_E9, e20=[90.0] * 6, e50=[100.0] * 6)  # 9>50 이지만 20<50 -> 꼬임
    row = ms.compute_market_state(df, n=3, k=2).iloc[3]
    assert row["a"] and row["b"] and row["c"]
    assert (row["state"], row["reason"]) == (SIDE, ms.REASON_A)


def test_cross_count_window_is_n_closes_so_max_n_minus_1_flips():
    # n=4 -> 종가 4개 안의 전환은 최대 3번. 교대 패턴이면 t=3에서 3.
    df = _df(ALTERNATING)
    r = ms.compute_market_state(df, n=4, k=3)
    assert r["cross_count"].iloc[3] == 3
    assert np.isnan(r["cross_count"].iloc[2])  # 창이 아직 다 안 찼음 -> 구할 수 없음
    assert r["c"].iloc[3] and not r["c"].iloc[2]
    # 창이 미끄러지면 오래된 전환은 빠진다: 마지막 5개가 모두 위면 전환 0
    closes = [160.0, 120.0, 160.0, 120.0] + [ABOVE] * 5
    r2 = ms.compute_market_state(_df(closes), n=4, k=1)
    assert r2["cross_count"].iloc[3] == 3
    assert r2["cross_count"].iloc[8] == 0


def test_close_equal_to_ema9_keeps_previous_side():
    # 위, 같음, 위 -> 전환 0 / 아래, 같음, 위 -> 전환 1(같은 날은 직전 쪽=아래로 보고 다음 날 위로 바뀜)
    r = ms.compute_market_state(_df([ABOVE, 130.0, ABOVE]), n=3, k=1)
    assert r["cross_count"].iloc[2] == 0
    r = ms.compute_market_state(_df([BELOW, 130.0, ABOVE]), n=3, k=1)
    assert r["cross_count"].iloc[2] == 1


def test_n_equals_1_has_no_transitions():
    r = ms.compute_market_state(_df([ABOVE, BELOW, ABOVE]), n=1, k=0)
    assert (r["cross_count"] == 0).all()
    assert r["c"].all()  # k=0 이면 항상 해당


# --- 데이터 부족 ---

def test_rows_without_ema50_are_insufficient():
    df = _df([ABOVE] * 4)
    df.loc[:1, "EMA50"] = np.nan
    r = ms.compute_market_state(df, n=2, k=1)
    assert pd.isna(r["state"].iloc[0]) and pd.isna(r["state"].iloc[1])
    assert pd.isna(r["reason"].iloc[0])
    assert r["state"].iloc[2] == UP
    s = ms.summarize(r, ms.find_blocks(r, [f"d{i}" for i in range(4)]))
    assert s["state_counts"][ms.STATE_INSUFFICIENT] == 2 and s["evaluated"] == 2


def test_lack_of_history_makes_b_and_c_false_but_a_still_works():
    # B는 N봉 전 간격이 필요(t<N이면 False), C는 종가 N개 창이 다 차야 한다(t<N-1이면 False).
    # 이력이 모자란 구간은 그 항목을 False로 보고 A만으로 판정 -> 정배열이면 상승.
    r = ms.compute_market_state(_bullish_shrinking(ALTERNATING), n=3, k=2)
    assert not r["b"].iloc[:3].any()
    assert not r["c"].iloc[:2].any()
    assert r["state"].iloc[:3].tolist() == [UP] * 3


def test_invalid_params():
    df = _df([ABOVE] * 3)
    with pytest.raises(ValueError):
        ms.compute_market_state(df, n=0, k=0)
    with pytest.raises(ValueError):
        ms.compute_market_state(df, n=3, k=4)
    with pytest.raises(ValueError):
        ms.compute_market_state(df, n=3, k=-1)


# --- 미래 참조 없음 ---

def _ema_frame(n_bars, seed):
    rng = np.random.default_rng(seed)
    close = pd.Series(30000 + np.cumsum(rng.normal(0, 400, n_bars)))
    return pd.DataFrame({
        "close": close,
        "EMA9": close.ewm(span=9, adjust=False, min_periods=9).mean(),
        "EMA20": close.ewm(span=20, adjust=False, min_periods=20).mean(),
        "EMA50": close.ewm(span=50, adjust=False, min_periods=50).mean(),
    })


@pytest.mark.parametrize("n,k", [(10, 4), (5, 2), (20, 6)])
def test_no_lookahead_truncated_run_matches_full_run(n, k):
    """캔들 t까지만 잘라서 돌린 t번째 결과 == 전체로 돌린 t번째 결과 (모든 t, 모든 컬럼).
    t 이후 데이터가 t의 판정에 영향을 주면 여기서 걸린다."""
    df = _ema_frame(260, seed=7)
    full = ms.compute_market_state(df, n, k)
    cols = list(full.columns)
    for t in range(len(df)):
        part = ms.compute_market_state(df.iloc[: t + 1].reset_index(drop=True), n, k).iloc[-1]
        for col in cols:
            a, b = full[col].iloc[t], part[col]
            both_missing = (a is None or (isinstance(a, float) and np.isnan(a))) and \
                           (b is None or (isinstance(b, float) and np.isnan(b)))
            assert both_missing or a == b, f"t={t} col={col}: 전체={a!r} 잘라서={b!r}"


def test_nonlookahead_data_after_t_does_not_change_t():
    # 같은 앞부분 + 서로 다른 뒷부분 -> 앞부분 결과 동일
    base = _ema_frame(200, seed=3)
    other = base.copy()
    other.loc[150:, "close"] = other.loc[150:, "close"] * 3 + 1000
    other["EMA9"] = other["close"].ewm(span=9, adjust=False, min_periods=9).mean()
    other["EMA20"] = other["close"].ewm(span=20, adjust=False, min_periods=20).mean()
    other["EMA50"] = other["close"].ewm(span=50, adjust=False, min_periods=50).mean()
    r1, r2 = ms.compute_market_state(base, 10, 4), ms.compute_market_state(other, 10, 4)
    pd.testing.assert_frame_equal(r1.iloc[:150], r2.iloc[:150])


# --- 블록 / 요약 ---

def _states(pairs):
    return pd.DataFrame({"state": [p[0] for p in pairs], "reason": [p[1] for p in pairs]})


def test_find_blocks_splits_on_state_gap_and_reason_change():
    A, BC, N_ = ms.REASON_A, ms.REASON_BC, ms.REASON_NONE
    pairs = [(UP, N_), (SIDE, A), (SIDE, A), (SIDE, BC), (SIDE, BC), (SIDE, BC), (DOWN, N_),
             (SIDE, A), (UP, N_), (None, None), (SIDE, A), (SIDE, A)]
    dates = [f"d{i}" for i in range(len(pairs))]
    blocks = ms.find_blocks(_states(pairs), dates)
    assert blocks == [
        {"start": "d1", "end": "d2", "length": 2, "reason": A},
        {"start": "d3", "end": "d5", "length": 3, "reason": BC},
        {"start": "d7", "end": "d7", "length": 1, "reason": A},
        {"start": "d10", "end": "d11", "length": 2, "reason": A},
    ]


def test_summarize_counts_ratios_and_length_stats():
    A, BC, N_ = ms.REASON_A, ms.REASON_BC, ms.REASON_NONE
    pairs = [(None, None), (UP, N_), (DOWN, N_), (SIDE, A), (SIDE, A), (SIDE, BC), (UP, N_), (SIDE, BC)]
    st = _states(pairs)
    blocks = ms.find_blocks(st, [f"d{i}" for i in range(len(pairs))])
    s = ms.summarize(st, blocks)
    assert s["total"] == 8 and s["evaluated"] == 7
    assert s["state_counts"] == {UP: 2, DOWN: 1, SIDE: 4, ms.STATE_INSUFFICIENT: 1}
    assert s["reason_counts"] == {A: 2, BC: 2}
    assert s["block_count"] == 3  # A(2), BC(1), BC(1)
    assert s["block_length_stats"] == {"min": 1, "median": 1, "max": 2}
    text = ms.format_report(st, blocks, [f"d{i}" for i in range(8)], 10, 4)
    assert "상승:" in text and "A:" in text and "최소 1 / 중앙값 1 / 최대 2" in text


# --- API ---

client = TestClient(app)


def test_api_market_state_matches_direct_computation():
    resp = client.get("/api/market-state", params={"n": 10, "k": 4})
    assert resp.status_code == 200
    data = resp.json()
    assert data["params"] == {"n": 10, "k": 4}

    dash = client.get("/api/dashboard").json()
    assert [c["date"] for c in data["candles"]] == [c["date"] for c in dash["candles"]]

    # 앞 49봉은 EMA50 없음 -> 데이터 부족(null)
    insufficient = [c for c in data["candles"] if c["state"] is None]
    assert len(insufficient) == 49 and data["counts"]["데이터 부족"] == 49
    assert all(c["state"] is not None for c in data["candles"][49:])

    # 블록 길이 합 == 횡보 캔들 수, 상태별 합 == 전체
    assert sum(b["length"] for b in data["blocks"]) == data["counts"]["횡보"]
    assert sum(data["counts"][s] for s in ("상승", "하락", "횡보", "데이터 부족")) == len(data["candles"])
    assert data["counts"]["reason_A"] + data["counts"]["reason_BC"] == data["counts"]["횡보"]

    # 횡보인 캔들만 reason이 A/BC, 상승/하락은 "없음"
    for c in data["candles"]:
        if c["state"] == "횡보":
            assert c["reason"] in ("A", "BC")
        elif c["state"] is not None:
            assert c["reason"] == "없음"


def test_api_params_change_result_and_defaults():
    default = client.get("/api/market-state").json()
    assert default["params"] == {"n": 10, "k": 4}
    strict = client.get("/api/market-state", params={"n": 10, "k": 9}).json()
    # K를 올리면 C 조건이 어려워져 BC 횡보가 줄거나 같다
    assert strict["counts"]["reason_BC"] <= default["counts"]["reason_BC"]
    # A는 N/K와 무관
    assert strict["counts"]["reason_A"] == default["counts"]["reason_A"]


def test_api_rejects_invalid_params():
    assert client.get("/api/market-state", params={"n": 0, "k": 0}).status_code == 422
    assert client.get("/api/market-state", params={"n": 10, "k": 11}).status_code == 422
    assert client.get("/api/market-state", params={"n": 10, "k": -1}).status_code == 422
