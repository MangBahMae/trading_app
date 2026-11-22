"""수동 추세선·지지 버전의 사건 날짜, 기존 패널 해석, 소급/중복 방지."""
import json

import pytest

from app.services import dashboard, rapid_drop_support_history as journal
from app.services.rise_support import support_days
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
