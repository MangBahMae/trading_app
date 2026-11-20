"""별도 지지 버전 기록의 시간·변경·보존 검사. 개인 DB와 기록 파일은 사용하지 않는다."""
from datetime import datetime, timezone
import json

import pytest

from app.services import rapid_drop_support_history as history


def at(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def horizontal(line_id=7, price=100):
    return dict(id=line_id, symbol="BTCUSDT", interval="1d", line_type="horizontal", price1=price,
                time1=None, time2=None, price2=None, created_at="2020-01-01T00:00:00+00:00")


def zone(line_id=8, start="2026-11-01", end="2026-11-30"):
    return dict(id=line_id, symbol="BTCUSDT", interval="1d", line_type="zone", price1=110, price2=90,
                time1=start, time2=end, created_at="2020-01-01T00:00:00+00:00")


def active(result, day):
    return [row for row in result["levels"] if row["known_from"] <= day <= row["through"]]


def test_missing_history_is_unconfirmed_without_creating_files(tmp_path):
    path = tmp_path / "missing" / "history.jsonl"
    result = history.load_levels("2026-11-18", path)
    assert result["levels"] == []
    assert result["status"] == "unconfirmed"
    assert result["recording_started_at"] is None
    assert not path.parent.exists()


def test_first_observation_never_backfills_created_at(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    earlier = history.load_levels("2026-11-18", path)
    assert earlier["levels"] == []
    assert earlier["recording_started_at"] is None
    result = history.load_levels("2026-11-19", path)
    assert len(result["levels"]) == 1
    assert result["levels"][0]["known_from"] == "2026-11-19"
    assert result["levels"][0]["support_id"] == "manual:7"


def test_datetime_query_only_includes_closed_days(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    assert history.load_levels(at("2026-11-19T18:00:00Z"), path)["levels"] == []
    assert len(history.load_levels(at("2026-11-20T00:00:00Z"), path)["levels"]) == 1


def test_duplicate_state_and_input_order_do_not_append(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal(), zone()], at("2026-11-19T12:00:00Z"), path)
    before = path.read_bytes()
    changed_label = dict(horizontal(), label="화면 라벨", created_at="2026-11-19T13:00:00Z")
    result = history.record_snapshot([zone(), changed_label], at("2026-11-19T13:00:00Z"), path)
    assert result["recorded"] is False
    assert path.read_bytes() == before


def test_future_versions_do_not_change_past_query(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    before = history.load_levels("2026-11-19", path)
    history.record_snapshot([horizontal(price=80), zone()], at("2026-11-21T12:00:00Z"), path)
    history.record_snapshot([], at("2026-11-22T12:00:00Z"), path)
    assert history.load_levels("2026-11-19", path) == before
    assert active(history.load_levels("2026-11-21", path), "2026-11-20")[0]["bottom"] == 100
    assert active(history.load_levels("2026-11-21", path), "2026-11-21")[0]["bottom"] == 80


def test_same_day_last_coordinate_version_is_used(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    history.record_snapshot([horizontal(price=80)], at("2026-11-19T18:00:00Z"), path)
    rows = history.load_levels("2026-11-19", path)["levels"]
    assert len(rows) == 1
    assert rows[0]["bottom"] == 80
    assert rows[0]["known_from"] == rows[0]["through"] == "2026-11-19"


def test_same_day_deletion_leaves_no_closed_day_level(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    history.record_snapshot([], at("2026-11-19T18:00:00Z"), path)
    assert history.load_levels("2026-11-19", path)["levels"] == []


def test_deletion_closes_old_version_but_preserves_past(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    past = history.load_levels("2026-11-19", path)
    history.record_snapshot([], at("2026-11-21T12:00:00Z"), path)
    result = history.load_levels("2026-11-21", path)
    assert active(result, "2026-11-20")
    assert not active(result, "2026-11-21")
    assert history.load_levels("2026-11-19", path) == past


def test_delete_then_restore_same_geometry_has_new_version_id(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    history.record_snapshot([], at("2026-11-20T12:00:00Z"), path)
    history.record_snapshot([horizontal()], at("2026-11-21T12:00:00Z"), path)
    rows = history.load_levels("2026-11-21", path)["levels"]
    assert len(rows) == 2
    assert rows[0]["key"] != rows[1]["key"]
    assert rows[0]["support_id"] == rows[1]["support_id"] == "manual:7"
    assert not active(history.load_levels("2026-11-21", path), "2026-11-20")


def test_new_snapshot_at_midnight_cannot_change_previous_day(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    before = history.load_levels("2026-11-19", path)
    history.record_snapshot([horizontal(price=80)], at("2026-11-20T00:00:00Z"), path)
    assert history.load_levels("2026-11-19", path) == before


def test_zone_uses_time_range_without_right_extension(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([zone(start="2026-11-20", end="2026-11-22")], at("2026-11-19T12:00:00Z"), path)
    result = history.load_levels("2026-11-25", path)
    row = result["levels"][0]
    assert row["known_from"] == "2026-11-20"
    assert row["through"] == "2026-11-22"
    assert not active(result, "2026-11-19")
    assert not active(result, "2026-11-23")


def test_past_zone_end_does_not_create_fake_historical_support(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([zone(start="2026-10-01", end="2026-10-31")], at("2026-11-19T12:00:00Z"), path)
    assert history.load_levels("2026-11-19", path)["levels"] == []


def test_trend_is_explicitly_unsupported(tmp_path):
    path = tmp_path / "history.jsonl"
    trend = dict(horizontal(), line_type="trend", time1="2026-11-01", time2="2026-11-10", price2=200)
    history.record_snapshot([trend], at("2026-11-19T12:00:00Z"), path)
    result = history.load_levels("2026-11-19", path)
    assert result["levels"] == []
    assert result["unsupported_line_ids"] == ["7"]
    assert any("추세선" in message for message in result["warnings"])


def test_other_symbol_and_interval_are_not_used(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([dict(horizontal(), symbol="ETHUSDT"), dict(zone(), interval="1w")],
                            at("2026-11-19T12:00:00Z"), path)
    assert history.load_levels("2026-11-19", path)["levels"] == []


@pytest.mark.parametrize("content", [b'{"bad":1}\n', b'{"partial":'])
def test_corrupt_or_partial_history_is_never_overwritten(tmp_path, content):
    path = tmp_path / "history.jsonl"
    path.write_bytes(content)
    with pytest.raises(history.SupportHistoryError):
        history.load_levels("2026-11-19", path)
    with pytest.raises(history.SupportHistoryError):
        history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    assert path.read_bytes() == content


def test_tampered_coordinate_hash_is_rejected(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    row = json.loads(path.read_text())
    row["state"]["lines"][0]["bottom"] = 1
    damaged = (json.dumps(row) + "\n").encode()
    path.write_bytes(damaged)
    with pytest.raises(history.SupportHistoryError):
        history.load_levels("2026-11-19", path)
    assert path.read_bytes() == damaged


def test_out_of_order_and_same_time_changes_are_rejected(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    before = path.read_bytes()
    for stamp in ("2026-11-18T12:00:00Z", "2026-11-19T12:00:00Z"):
        with pytest.raises(history.SupportHistoryError):
            history.record_snapshot([horizontal(price=80)], at(stamp), path)
    assert path.read_bytes() == before


def test_naive_observation_timestamp_is_rejected(tmp_path):
    with pytest.raises(history.SupportHistoryError):
        history.record_snapshot([horizontal()], datetime(2026, 11, 19), tmp_path / "history.jsonl")


def test_exclusive_lock_fails_closed_and_preserves_file(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-19T12:00:00Z"), path)
    before = path.read_bytes()
    lock = path.with_name(path.name + ".lock")
    lock.write_text("다른 프로세스")
    with pytest.raises(history.SupportHistoryError):
        history.record_snapshot([], at("2026-11-20T12:00:00Z"), path)
    with pytest.raises(history.SupportHistoryError):
        history.load_levels("2026-11-19", path)
    assert path.read_bytes() == before
    assert lock.exists()


def test_environment_path_uses_only_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "env_history.jsonl"
    monkeypatch.setenv(history.ENV_PATH, str(path))
    history.record_snapshot([], at("2026-11-19T12:00:00Z"))
    assert path.exists()
    assert history.load_levels("2026-11-19")["status"] == "recorded"


def test_timestamp_is_normalized_to_utc_day(tmp_path):
    path = tmp_path / "history.jsonl"
    history.record_snapshot([horizontal()], at("2026-11-20T01:00:00+09:00"), path)
    result = history.load_levels("2026-11-19", path)
    assert result["levels"][0]["known_from"] == "2026-11-19"
    assert result["recording_started_at"].endswith("Z")


@pytest.mark.parametrize("lines", [[horizontal(), horizontal()], [horizontal(price=float("nan"))],
                                  [dict(zone(), time1="wrong")], [dict(horizontal(), id=None)],
                                  [horizontal(price=True)], [dict(horizontal(), interval=None)]])
def test_invalid_snapshot_does_not_create_a_history(tmp_path, lines):
    path = tmp_path / "history.jsonl"
    with pytest.raises(history.SupportHistoryError):
        history.record_snapshot(lines, at("2026-11-19T12:00:00Z"), path)
    assert not path.exists()
