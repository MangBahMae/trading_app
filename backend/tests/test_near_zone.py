"""
캔들 패턴 신호의 near_zone 플래그 (표시용): 고가~저가 범위가 존과 조금이라도 겹치면 True.

- 존은 time1부터 오른쪽 끝까지 연장(time2 무관), time1 이전 캔들은 근처가 아니다
- 경계에 닿기만 해도(low == 상단, high == 하단) 겹침
- 캔들 패턴이 아닌 신호는 None, zones를 안 넘기면 모든 캔들 패턴 신호가 None
- 플래그는 후보/참고 판정(신호 text/direction)을 절대 바꾸지 않는다
"""
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app

import lines_store  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "services"))

import candle_patterns  # noqa: E402
import pipeline  # noqa: E402

T, B = 110.0, 100.0


def _zone(time1="2025-01-01", time2="2025-01-01", top=T, bottom=B, zone_id=5):
    return {"id": zone_id, "line_type": "zone", "time1": time1, "price1": top, "time2": time2,
            "price2": bottom, "created_at": "2026-10-06T00:00:00+00:00"}


def _doji_df(candles):
    """도지 모양 캔들들(open≈close, 위아래 꼬리 긴 편) - 모양이 맞아야 캔들 패턴 신호가 난다."""
    n = len(candles)
    return pd.DataFrame({
        "open_time": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"),
        "open": [c[0] for c in candles], "high": [c[1] for c in candles],
        "low": [c[2] for c in candles], "close": [c[3] for c in candles],
        "volume": [1.0] * n, "EMA50": [None] * n, "EMA200": [None] * n,
    })


DOJI = lambda mid, wick=5.0: (mid, mid + wick, mid - wick, mid)  # noqa: E731


def test_near_zone_flags_overlap_rules():
    zs = candle_patterns._near_zone_flags
    df = _doji_df([DOJI(50), DOJI(105), DOJI(100, 0.0), DOJI(118, 8), DOJI(121, 10), DOJI(90, 10)])
    # idx0: 45~55 아래 / idx1: 100~110 안 / idx2: 100~100 하단에 닿음(high==B) / idx3: 110~126 -> low 110 == T 닿음
    # idx4: 111~131 위 / idx5: 80~100 -> high 100 == B 닿음
    assert zs(df, [_zone()]) == [False, True, True, True, False, True]


def test_zone_extends_right_beyond_time2_and_not_left_of_time1():
    df = _doji_df([DOJI(105)] * 5)  # 01-01 ~ 01-05 전부 존 안 가격
    assert candle_patterns._near_zone_flags(df, [_zone(time1="2025-01-03", time2="2025-01-03")]) == [
        False, False, True, True, True]   # time1 전날까지 False, time2(=time1)를 지나도 계속 True


def test_non_zone_rows_and_empty_list_give_all_false():
    df = _doji_df([DOJI(105)] * 3)
    hline = {"id": 1, "line_type": "horizontal", "price1": 105.0, "time1": None, "time2": None, "price2": None}
    assert candle_patterns._near_zone_flags(df, [hline]) == [False] * 3
    assert candle_patterns._near_zone_flags(df, []) == [False] * 3


def test_every_candle_pattern_signal_gets_the_flag_and_judgement_is_unchanged():
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    zones = [_zone(time1="2024-01-01", top=70000.0, bottom=60000.0), _zone(time1="2025-06-01", top=108000.0,
                                                                       bottom=104000.0, zone_id=6)]
    base = candle_patterns.compute_candle_pattern_signals(df, {})
    flagged = candle_patterns.compute_candle_pattern_signals(df, {}, zones=zones)

    def plain(m):
        return {i: [(s.text, s.direction, s.source, s.tier, s.evidence, s.ref_id, s.ref_created_at) for s in v]
                for i, v in m.items()}

    assert plain(flagged) == plain(base)                                   # 판정 변화 0건
    assert all(s.near_zone is None for v in base.values() for s in v)      # zones를 안 넘기면 None
    sigs = [s for v in flagged.values() for s in v]
    assert sigs and all(s.near_zone in (True, False) for s in sigs)        # 후보/참고/무효 모두 True/False
    assert any(s.near_zone for s in sigs) and not all(s.near_zone for s in sigs)

    lows, highs = df["low"].tolist(), df["high"].tolist()
    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    for i, v in flagged.items():
        expect = any(dates[i] >= z["time1"] and lows[i] <= max(z["price1"], z["price2"])
                     and highs[i] >= min(z["price1"], z["price2"]) for z in zones)
        assert all(s.near_zone is expect for s in v)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(lines_store, "DB_PATH", tmp_path / "manual_lines.db")
    return TestClient(app)


def test_dashboard_exposes_near_zone_only_on_candle_pattern_signals(client):
    client.post("/api/lines/zone", json={"time1": "2024-01-01", "price1": 70000.0, "time2": "2024-02-01",
                                         "price2": 60000.0})
    data = client.get("/api/dashboard").json()
    items = [s for v in data["signals"].values() for s in v]
    candle = [s for s in items if s["text"].split(" - ")[0] in ("도지", "망치형", "역망치형")]
    other = [s for s in items if s not in candle]
    assert candle and other
    assert all(s["near_zone"] in (True, False) for s in candle)
    assert any(s["near_zone"] for s in candle)
    assert all(s["near_zone"] is None for s in other)


def test_dashboard_without_any_line_still_flags_candle_signals_false_or_none(client):
    data = client.get("/api/dashboard").json()
    items = [s for v in data["signals"].values() for s in v]
    assert all(s["near_zone"] in (None, False) for s in items)
