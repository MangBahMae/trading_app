"""합성 마감봉으로 도형 역할 전환의 시점, 가격, 원래 사건 ID를 검사한다."""
import pandas as pd
import pytest

from app.services import breakout_retest, rise_response


def bars(prices):
    frame = pd.DataFrame(prices, columns=["open", "high", "low", "close"], dtype=float)
    frame["open_time"] = pd.date_range("2022-01-01", periods=len(frame), tz="UTC")
    frame["volume"] = 10.
    return frame


ZONE = dict(support_id="manual:7", key="manual:7:v1", kind="zone", bottom=100., top=102.,
            known_from="2022-01-01", through="2022-09-30")
TREND = dict(support_id="manual:8", key="manual:8:v1", kind="trend", known_from="2022-01-01",
             through="2022-09-30", time1="2022-01-01", price1=105., time2="2022-01-02", price2=104.)
BASE = [(100, 102, 99, 101), (101, 104, 100, 103)]


def run(frame, *versions):
    timeline = rise_response.build_timeline(frame, versions)
    return breakout_retest.build_days(frame, versions, timeline)


def types(row):
    return [event["type"] for event in row["events"]]


def event(row, kind):
    found, = [item for item in row["events"] if item["type"] == kind]
    return found


def test_long_then_fails_links_history_and_does_not_duplicate_canonical_short():
    frame = bars(BASE + [(103, 104, 101, 102), (102, 104, 101, 103), (103, 104, 96, 98),
                         (98, 101, 95, 97), (97, 101, 94, 96), (96, 103, 95, 102), (102, 104, 101, 103)])
    legacy = rise_response.build_timeline(frame, [ZONE])
    rows = breakout_retest.build_days(frame, [ZONE], legacy)
    assert types(rows[1]) == ["breakout_up"]
    first = event(rows[2], "long_candidate")
    assert first["breakout_date"] == "2022-01-02" and first["retest_date"] == "2022-01-03"
    assert first["volume"] == 10. and first["status"] == "new"
    assert rows[3]["active"][0]["id"] == first["id"] and rows[3]["active"][0]["status"] == "maintained"
    assert "long_candidate" not in types(rows[3])
    assert types(rows[4]) == ["invalidated", "breakout_failed", "break_down", "long_exit"]
    assert first["id"] in event(rows[4], "invalidated")["linked_ids"]
    short = event(rows[5], "short_candidate")
    original, = [e for e in legacy[5]["events"] if e["kind"] == "support_retest_short" and e["source"] == "manual"]
    assert (short["id"], short["origin"]) == (original["id"], "rise_response")
    assert event(rows[4], "breakout_failed")["id"] in short["linked_ids"]
    assert [s["type"] for s in short["steps"]] == [
        "breakout_up", "breakout_failed", "break_down", "long_exit", "retest_below", "short_candidate"]
    assert "short_candidate" not in types(rows[6]) and "long_candidate" not in types(rows[7])
    reclaim = event(rows[7], "breakdown_failed")
    assert reclaim["retest_date"] is None
    second = event(rows[8], "long_candidate")
    assert second["breakout_date"] == "2022-01-05" and second["retest_date"] == "2022-01-09"
    assert reclaim["id"] in second["linked_ids"]
    ids = [e["id"] for row in rows for e in row["events"]]
    assert len(ids) == len(set(ids))


def test_wick_sweep_and_two_sided_sweep_are_not_close_breaks():
    rows = run(bars([(101, 102, 100, 101), (101, 104, 100, 101), (101, 104, 99, 101)]), ZONE)
    assert types(rows[1]) == ["wick_sweep"] and not rows[1]["active"]
    assert not rows[2]["events"]


@pytest.mark.parametrize("opening", [101, 102])
def test_inside_caution_then_intersection_and_close_above_without_open_filter(opening):
    frame = bars(BASE + [(103, 103, 100, 101), (101, 101.5, 100, 100.5),
                         (opening, 104, 101, 103), (103, 104, 102, 103)])
    rows = run(frame, ZONE)
    caution = event(rows[2], "breakout_caution")
    assert rows[3]["active"][0]["id"] == caution["id"] and not rows[3]["events"]
    assert caution["id"] in event(rows[4], "long_candidate")["linked_ids"]
    dates = [e["confirmed_date"] for r in rows for e in r["events"] if e["type"] == "long_candidate"]
    assert dates == ["2022-01-05"]


def test_down_failure_at_upper_equality_then_rebreak_is_not_an_up_break_failure():
    rows = run(bars([(103, 104, 102, 103), (103, 104, 98, 99), (99, 102, 98, 102),
                     (102, 102, 98, 99)]), ZONE)
    assert "breakdown_failed" in types(rows[2]) and "long_candidate" not in types(rows[2])
    assert "reclaim_failed" in types(rows[3]) and "breakout_failed" not in types(rows[3])


def test_nonhorizontal_bounds_use_each_date_and_both_anchors():
    # 선 가격은 둘째 날 104, 셋째 103, 넷째 102, 다섯째 101이다.
    frame = bars([(104, 109, 104, 106), (106, 106, 102, 103), (103, 105, 102, 104),
                  (104, 104, 102, 102), (102, 102, 100, 100.5)])
    rows = run(frame, TREND)
    assert not rows[0]["events"] and "break_down" not in types(rows[1])
    candidate = event(rows[3], "long_candidate")
    assert (candidate["breakout_top"], candidate["retest_top"]) == (103., 102.)
    assert event(rows[4], "invalidated")["bottom"] == 101.
    assert event(rows[4], "breakout_failed")["confirmed_date"] == "2022-01-05"


def test_rising_line_exit_id_and_separate_reclaim_retest():
    trend = dict(TREND, price1=100, price2=101)
    frame = bars([(101, 102, 100, 101), (102, 103, 101, 102), (102, 103, 100, 101),
                  (101, 104, 100, 103), (103, 106, 103, 105)])
    legacy = rise_response.build_timeline(frame, [trend])
    rows = breakout_retest.build_days(frame, [trend], legacy)
    original, = [e for e in legacy[2]["events"] if e["kind"] == "trendline_exit_long"]
    assert event(rows[2], "long_exit")["id"] == original["id"] and "short_candidate" not in types(rows[2])
    assert "breakdown_failed" in types(rows[3]) and "long_candidate" not in types(rows[3])
    assert event(rows[4], "long_candidate")["retest_bottom"] == 104


def test_horizontal_equality_deadlines_and_fresh_attempt():
    line = dict(ZONE, kind="horizontal", bottom=100, top=100)
    # d+8의 최초 접촉과 이후 발행일+8까지 유효하다.
    frame = bars([(99, 100, 98, 99), (99, 102, 98, 101)] + [(101, 102, 101, 101)] * 7
                 + [(101, 102, 100, 100)] + [(101, 102, 101, 101)] * 9)
    rows = run(frame, line)
    first = event(rows[9], "long_candidate")
    assert rows[17]["active"][0]["id"] == first["id"]
    assert event(rows[18], "expired")["linked_ids"][-1] == first["id"] and not rows[18]["active"]
    frame = bars([(99, 100, 98, 99), (99, 102, 98, 101)] + [(101, 102, 101, 101)] * 8
                 + [(101, 102, 100, 100), (100, 102, 100, 101), (101, 102, 100, 100)])
    rows = run(frame, line)
    assert "expired" in types(rows[10]) and "long_candidate" not in types(rows[10])
    second = event(rows[12], "long_candidate")
    assert second["attempt_id"] == event(rows[11], "breakout_up")["id"]
    assert second["attempt_id"] != event(rows[1], "breakout_up")["id"]


@pytest.mark.parametrize("reason,kind", [("replaced", "version_replaced"), ("ended", "version_ended")])
def test_end_does_not_use_old_or_future_coordinates(reason, kind):
    frame = bars(BASE + [(103, 104, 101, 103)] * 3)
    old = dict(ZONE, through="2022-01-03", end_reason=reason)
    future = dict(ZONE, known_from="2022-01-05", key="manual:7:v2", top=105)
    rows = run(frame, old, future)
    assert types(rows[3]) == [kind] and not rows[3]["active"]
    closed = event(rows[3], kind)
    assert closed["bottom"] is None and closed["retest_top"] == 102
    for n in range(1, len(frame) + 1):
        assert run(frame.iloc[:n], old, future) == rows[:n]
    assert rows[:4] == run(frame.iloc[:4], old)


def test_old_short_does_not_attach_to_new_break_after_display_expiry():
    frame = bars([(104, 105, 103, 104), (104, 105, 98, 99)] + [(99, 99.5, 98, 99)] * 9
                 + [(101, 101.5, 100.5, 101), (101, 101, 98, 99), (99, 100.5, 98, 98.5),
                    (98.5, 103, 98, 103)])
    original = rise_response.build_timeline(frame, [ZONE])
    rows = breakout_retest.build_days(frame, [ZONE], original)
    assert "expired" in types(rows[10]) and "break_down" in types(rows[12])
    old, = [e for e in original[13]["events"] if e["kind"] == "support_retest_short" and e["source"] == "manual"]
    assert old["break_date"] == "2022-01-02" and "short_candidate" not in types(rows[13])
    recovered = event(rows[14], "breakdown_failed")
    assert recovered["breakout_date"] == "2022-01-13" and recovered["origin"] == "breakout_retest"
    assert old["id"] not in recovered["linked_ids"]


def test_unknown_volume_is_optional_evidence():
    frame = bars(BASE + [(103, 104, 102, 103)])
    frame.loc[2, "volume"] = float("nan")
    assert event(run(frame, ZONE)[2], "long_candidate")["volume"] is None
