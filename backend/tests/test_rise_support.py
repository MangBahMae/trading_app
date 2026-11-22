"""수동 추세선·지지 버전의 사건 날짜, 기존 패널 해석, 소급/중복 방지."""
import json

import pandas as pd
import pytest

from app.services import dashboard, rapid_drop_support_history as journal
from app.services.rise_support import support_days
from app.services.rise_market import market_days
from rise_support_examples import support_example


def versions(path, day="2022-01-31"):
    return journal.load_drawing_versions(day, path)["versions"]


def example(tmp_path, name):
    frame, lines = support_example(name)
    path = tmp_path / "drawings.jsonl"
    journal.record_snapshot(lines, "2022-01-01T00:00:00Z", path)
    return frame, path, support_days(frame, versions(path))


def kinds(row):
    return [e["kind"] for e in row["events"]]


def test_ascending_trend_wick_then_close_exit_and_rebound(tmp_path):
    frame, _, rows = example(tmp_path, "trendline")
    assert rows[0]["details"]["trendline_status"] == "추세선 미확인"
    assert kinds(rows[2]) == ["trendline_wick_recovery"]
    assert kinds(rows[3]) == ["trendline_exit_long"]
    assert rows[3]["details"]["levels"][0]["price"] == 102
    assert "숏" not in rows[3]["events"][0]["label"]
    assert not rows[4]["events"] and not rows[4]["active_short_ids"]
    _, lines = support_example("trendline")
    legacy = dashboard.manual_lines.compute_manual_line_state_signals(frame, lines)
    assert any(signal.direction == "short" and "하향 이탈" in signal.text for signal in legacy[3])
    assert rows[3]["events"][0]["date"] == "2022-01-04"


@pytest.mark.parametrize(("name", "expected"), [
    ("support_fail", ["support_retest_touch", "support_retest_short"]),
    ("support_recover", ["support_retest_touch", "support_reclaimed"]),
    ("support_no_retest", []),
])
def test_same_support_break_three_distinct_outcomes(tmp_path, name, expected):
    _, _, rows = example(tmp_path, name)
    assert kinds(rows[1]) == ["support_break"]
    assert kinds(rows[2]) == expected
    if name == "support_fail":
        issued = rows[2]["events"][1]
        assert issued["related"] == rows[2]["events"][0]["id"]
        assert rows[2]["events"][0]["related"] == rows[1]["events"][0]["id"]
        assert not rows[3]["events"]
        assert rows[3]["active_short_ids"] == [issued["id"]]
        assert kinds(rows[4]) == ["support_reclaimed"] and not rows[4]["active_short_ids"]
    else:
        assert not any(r["active_short_ids"] for r in rows)


def test_zone_entry_requires_a_later_decline_below_bottom(tmp_path):
    frame, path, _ = example(tmp_path, "support_fail")
    frame.loc[2, ["open", "high", "low", "close"]] = [98, 101.5, 97, 101]
    rows = support_days(frame, versions(path))
    assert kinds(rows[2]) == ["support_retest_touch"]
    assert kinds(rows[3]) == ["support_retest_short"]


def test_gap_below_trendline_and_body_recovery_is_not_a_wick(tmp_path):
    frame, path, _ = example(tmp_path, "trendline")
    frame.loc[2, ["open", "low"]] = [100, 99]
    assert not support_days(frame, versions(path))[2]["events"]


def test_gap_above_zone_does_not_prove_bottom_up_retest(tmp_path):
    frame, path, _ = example(tmp_path, "support_fail")
    frame.loc[2, ["open", "high", "low", "close"]] = [103, 104, 96, 97]
    assert not support_days(frame, versions(path))[2]["events"]


def test_horizontal_recovery_accepts_equality(tmp_path):
    frame, _ = support_example("support_recover")
    frame.loc[2, "close"] = 100
    path = tmp_path / "support.jsonl"
    journal.record_snapshot([dict(id=5, line_type="horizontal", price1=100)], "2022-01-01T00:00:00Z", path)
    rows = support_days(frame, versions(path))
    assert kinds(rows[1]) == ["support_break"]
    assert kinds(rows[2]) == ["support_retest_touch", "support_reclaimed"]


def test_support_replacement_cannot_inherit_break_or_candidate(tmp_path):
    frame, path, rows = example(tmp_path, "support_fail")
    _, lines = support_example("support_fail")
    journal.record_snapshot([dict(lines[0], price1=103)], "2022-01-03T12:00:00Z", path)
    switched = support_days(frame, versions(path))
    assert rows[:2] == switched[:2] and kinds(switched[1]) == ["support_break"]
    assert not switched[2]["events"] and switched[2]["active_short_ids"] == []


@pytest.mark.parametrize("name", ["trendline", "support_fail", "support_recover", "support_no_retest"])
def test_prefix_and_late_drawing_never_change_earlier_days(tmp_path, name):
    frame, path, original = example(tmp_path, name)
    _, lines = support_example(name)
    journal.record_snapshot([dict(lines[0], id=73)], "2022-02-03T00:00:00Z", path)
    for i in range(1, len(frame) + 1):
        day = frame["open_time"].iloc[i - 1].date()
        assert support_days(frame.iloc[:i], versions(path, day)) == original[:i]
    assert support_days(frame, versions(path, "2022-02-05")) == original


def test_nonascending_and_newly_registered_trends_do_not_backfill(tmp_path):
    frame, lines = support_example("trendline")
    path = tmp_path / "late.jsonl"
    journal.record_snapshot([dict(lines[0], price2=98)], "2022-01-01T00:00:00Z", path)
    journal.record_snapshot(lines, "2022-01-04T12:00:00Z", path)
    rows = support_days(frame, versions(path))
    assert all(not r["events"] for r in rows[:4])
    assert rows[2]["details"]["trendline_status"] == "추세선 미확인"


def test_legacy_hash_chain_uses_trend_only_from_first_known_geometry(tmp_path):
    # v1에서는 추세선 ID만 기록했다. 구버전 바이트를 그대로 둔 채 새 좌표부터 append한다.
    frame, lines = support_example("trendline")
    path = tmp_path / "legacy.jsonl"
    state = {"lines": [], "unsupported_line_ids": ["41"]}
    body = dict(schema_version=1, observed_at="2022-01-01T00:00:00.000000Z",
                state=state, fingerprint=journal._hash(state), previous_hash=None)
    legacy = journal._canonical(dict(body, record_hash=journal._hash(body))) + b"\n"
    path.write_bytes(legacy)
    assert not versions(path, "2022-01-03")
    before = journal.load_levels("2022-01-03", path)
    journal.record_snapshot(lines, "2022-01-04T00:00:00Z", path)
    assert path.read_bytes().startswith(legacy)
    assert [json.loads(line)["schema_version"] for line in path.read_bytes().splitlines()] == [1, 2]
    assert journal.load_levels("2022-01-03", path) == before
    after = journal.load_levels("2022-01-04", path)
    assert after["levels"] == [] and after["unsupported_line_ids"] == ["41"]
    assert versions(path)[0]["known_from"] == "2022-01-04"
    assert not support_days(frame, versions(path))[3]["events"]


def test_rise_only_crud_records_geometry_both_off_skip(tmp_path, monkeypatch):
    path = tmp_path / "onoff.jsonl"
    monkeypatch.setenv(journal.ENV_PATH, str(path))
    monkeypatch.setattr(dashboard.feature_flags, "ENABLE_RAPID_DROP_SIGNALS", False)
    monkeypatch.setattr(dashboard.feature_flags, "ENABLE_RISE_RESPONSE", False)
    identity = dashboard.add_trend_line("2022-01-01", 99, "2022-01-02", 100)
    assert not path.exists()
    monkeypatch.setattr(dashboard.feature_flags, "ENABLE_RISE_RESPONSE", True)
    dashboard.update_trend(identity, "2022-01-02", 100, "2022-01-01", 98)
    recorded = versions(path, "2099-01-01")
    assert len(recorded) == 1 and recorded[0]["price1"] == 98 and recorded[0]["price2"] == 100
    assert journal.load_levels("2099-01-01", path)["unsupported_line_ids"] == [str(identity)]
    dashboard.delete_line(identity)
    assert versions(path, "2099-01-01") == []


def test_trendline_exit_with_actual_bullish_ema_and_no_short(tmp_path):
    frame, lines = support_example("bull_trendline")
    path = tmp_path / "drawings.jsonl"
    journal.record_snapshot(lines, frame.open_time.iloc[0].isoformat(), path)
    market = market_days(frame)
    rows = support_days(frame, versions(path, "2022-04-01"), market)
    assert kinds(rows[65]) == ["trendline_wick_recovery"]
    assert rows[66]["events"][0]["kind"] == "trendline_exit_long"
    assert market[66]["details"]["ema_regime"] == "bullish"
    assert not rows[66]["details"]["active_shorts"] and not market[66]["short_watch"]


def test_ema_touch_then_continuation_or_rejection_on_new_close():
    fail, _ = support_example("ema_resist_fail")
    rise, _ = support_example("ema_resist_rise")
    fail_market = market_days(fail)
    failed = support_days(fail, [], fail_market)
    continued = support_days(rise, [], market_days(rise))
    assert failed[:223] == continued[:223]
    assert fail_market[222]["details"]["ema_regime"] == "bearish"
    assert fail_market[222]["details"]["price_direction"] == "up"
    assert any(e["kind"] == "resistance_touch" and e["source"] == "EMA50" for e in failed[222]["events"])
    assert "resistance_rejected" not in kinds(failed[222])
    assert "resistance_rejected" not in kinds(continued[223])
    assert "resistance_broken" in kinds(continued[223])
    assert "high_retry_failed" in kinds(fail_market[223])
    assert "high_retry_failed" not in kinds(market_days(rise)[223])
    watch, = [e for e in failed[223]["events"] if e["kind"] == "resistance_rejected"]
    assert watch["date"] == "2022-08-12" and watch["touch_date"] == "2022-08-11"
    assert "resistance_rejected" not in kinds(failed[224])
    assert failed[224]["details"]["active_shorts"][0]["duration_bars"] == 2
    release, = [e for e in failed[225]["events"] if e["kind"] == "resistance_watch_released"]
    assert release["related"] == watch["id"] and release["duration_bars"] == 3
    assert release["lifecycle"] == "released" and not failed[225]["active_resistance_ids"]
    for end in range(221, len(fail) + 1):
        assert support_days(fail.iloc[:end], [], market_days(fail.iloc[:end])) == failed[:end]


def test_ema200_and_ema50_keep_independent_contact_prices():
    frame, _ = support_example("ema_resist_fail")
    frame.loc[222, "high"] = 116  # 200봉 예열 뒤 두 EMA를 동시에 관통한 윗꼬리
    rows = support_days(frame, [], market_days(frame))
    watch = [e for e in rows[223]["events"] if e["kind"] == "resistance_rejected"]
    assert {e["source"] for e in watch} == {"EMA50", "EMA200"}
    assert len({e["id"] for e in watch}) == 2
    assert {e["source"] for e in rows[-1]["details"]["active_shorts"]
            if e["kind"] == "resistance_rejected"} == {"EMA200"}


def test_ema_watch_ends_on_moving_average_reclaim_and_allows_new_attempt():
    frame, _ = support_example("ema_resist_fail")
    frame = frame.iloc[:224].copy()  # EMA50 ≈ 103 저항이 거부된 뒤 급락으로 EMA 자체가 하락
    tail = [(92, 92.4, 91.6, 92)] * 48 + [
        (92, 99.5, 91.9, 99), (92, 92.3, 90.8, 91), (91, 92.7, 90.9, 92.4),
        (92.4, 95.5, 91.9, 93), (93, 93.1, 89.6, 90)]
    extra = pd.DataFrame(tail, columns=["open", "high", "low", "close"])
    extra["open_time"] = pd.date_range(frame.open_time.iloc[-1]+pd.Timedelta(days=1), periods=len(extra))
    extra["volume"] = 100.
    bars = pd.concat([frame, extra], ignore_index=True)
    rows = support_days(bars, [], market_days(bars))

    original, = [e for e in rows[223]["events"] if e["kind"] == "resistance_rejected"]
    end, = [e for e in rows[-5]["events"] if e["kind"] == "resistance_watch_released" and e["source"] == "EMA50"]
    assert end["related"] == original["id"]
    assert end["current_price"] < end["confirmation_close"] < end["touch_price"]
    assert not rows[-5]["active_resistance_ids"]
    second, = [e for e in rows[-1]["events"] if e["kind"] == "resistance_rejected" and e["source"] == "EMA50"]
    assert second["related"] != original["related"]
    assert second["confirmation_close"] < min(second["touch_low"], second["touch_price"], second["current_price"])


def test_manual_resistance_rejection_and_version_end(tmp_path):
    frame, lines = support_example("support_fail")
    frame[["open", "high", "low", "close"]] = [
        (95, 97, 94, 96), (96, 99, 95, 98), (98, 101, 97, 99), (99, 99.5, 95, 96), (96, 97, 94, 95)]
    path = tmp_path / "resistance.jsonl"
    journal.record_snapshot(lines, "2022-01-01T00:00:00Z", path)
    journal.record_snapshot([], "2022-01-05T00:00:00Z", path)
    rows = support_days(frame, versions(path))
    assert kinds(rows[2]) == ["resistance_touch"]
    watch, = rows[3]["events"]
    assert watch["kind"] == "resistance_rejected" and watch["source"] == "manual"
    end, = rows[4]["events"]
    assert end["kind"] == "resistance_watch_ended" and end["related"] == watch["id"]
    assert end["lifecycle"] == "invalidated" and end["started_on"] == "2022-01-04"
    assert not rows[4]["active_resistance_ids"]


def test_falling_price_touch_without_preceding_bounce_does_not_start_watch(tmp_path):
    frame, lines = support_example("support_fail")
    frame[["open", "high", "low", "close"]] = [
        (98, 99, 96, 98), (98, 99, 96, 97), (97, 101, 96, 96.5), (96.5, 98, 94, 95), (95, 96, 93, 94)]
    path = tmp_path / "resistance.jsonl"
    journal.record_snapshot(lines, "2022-01-01T00:00:00Z", path)
    rows = support_days(frame, versions(path))
    assert not any(row["active_resistance_ids"] for row in rows)
    assert not any(event["kind"].startswith("resistance_") for row in rows for event in row["events"])


def test_manual_candidate_ends_on_version_change(tmp_path):
    frame, path, _ = example(tmp_path, "support_fail")
    journal.record_snapshot([], "2022-01-04T00:00:00Z", path)
    rows = support_days(frame, versions(path))
    issued, = rows[2]["active_short_ids"]
    end, = rows[3]["events"]
    assert end["kind"] == "support_candidate_ended" and end["related"] == issued
    assert not rows[3]["active_short_ids"]


def test_retest_of_prior_rising_low_survives_new_structure_and_regime():
    frame, _ = support_example("support_fail")
    dates = frame.open_time.dt.date.astype(str).tolist()
    def low(date, confirmed, price):
        return dict(date=date, confirmed_on=confirmed, price=price)
    first = low("2021-12-22", "2021-12-24", 96.)
    second = low("2021-12-30", dates[0], 100.)
    third = low("2021-12-31", dates[1], 101.)
    rows = []
    for i in range(len(dates)):
        rows.append(dict(details=dict(swing_lows=[first, second] if i == 0 else [second, third],
                                      ema50=None, ema200=None, ema_regime="bullish" if i < 2 else "bearish")))
    result = support_days(frame, [], rows)
    broken, = [e for e in result[1]["events"] if e["kind"] == "support_break"]
    assert broken["source"] == "swing_low" and broken["price"] == 100.
    watch, = [e for e in result[2]["events"] if e["kind"] == "support_retest_short"]
    assert watch["support_id"] == broken["support_id"] and watch["price"] == 100.
    assert result[3]["active_short_ids"] == [watch["id"]]
    assert result[4]["events"][0]["related"] == watch["id"]
