"""
일봉 대시보드 골든값: 고정 일봉(tests/fixtures) + 선/존 스냅샷으로 계산한 신호 요약이 tests/golden/daily_golden.json과 같다.

규칙을 의도적으로 바꾸면 이 테스트가 실패하면서 "어떤 항목이 몇 -> 몇으로" 바뀌었는지 보여준다. 의도한 변경이면
`cd backend && .venv/Scripts/python tests/regen_golden.py`로 골든값을 다시 뽑아 diff를 확인하고 커밋한다(docs/golden_tests.md).
"""
import json

import pytest

import dashboard  # noqa: E402  (conftest가 services 경로를 sys.path에 넣어 둔다)
import golden_support


@pytest.fixture
def actual_summary(seed_snapshot_db):
    return golden_support.summarize(dashboard.get_dashboard_data(force_refresh=True))


@pytest.fixture(scope="module")
def expected_summary():
    return json.loads(golden_support.GOLDEN.read_text(encoding="utf-8"))


def test_daily_signals_match_the_golden_values(actual_summary, expected_summary):
    assert actual_summary == expected_summary, golden_support.failure_message(expected_summary, actual_summary)


def test_golden_covers_every_signal_family_of_the_snapshot_lines(expected_summary):
    """골든값 자체의 건전성: 스냅샷의 수평선/추세선/존이 각각 근접·돌파·유지 중(추세선은 오른쪽 연장 구간 포함)을 실제로 만든다."""
    cats = expected_summary["by_category"]
    has = lambda *needles: any(all(n in c for n in needles) for c in cats)  # noqa: E731
    assert has("수평선", "근접") and has("수평선", "진입") and has("수평선", "유지 중")
    assert has("추세선", "근접") and has("추세선", "진입") and has("추세선", "유지 중")
    assert has("존", "반응") and has("존", "이탈") and has("존", "스윕")
    assert set(expected_summary["zone_signals_by_ref"]) == {"27", "28", "54"}
    assert expected_summary["manual_line_ids"] == [27, 28, 54, 9001, 9002]
    assert expected_summary["near_zone"]["true"] > 0 and expected_summary["next_bar_true"] > 0


def test_failure_message_shows_which_item_changed_from_what_to_what():
    expected = {"signals_total": 10, "by_category": {"도지 - 롱 후보": 5, "삭제될 항목": 2}, "signals_sha256": "a"}
    actual = {"signals_total": 12, "by_category": {"도지 - 롱 후보": 3, "새 항목": 4}, "signals_sha256": "b"}
    message = golden_support.failure_message(expected, actual)
    assert "signals_total: 10 -> 12 (+2)" in message
    assert "by_category['도지 - 롱 후보']: 5 -> 3 (-2)" in message
    assert "by_category['삭제될 항목']: 2 -> (없음)" in message
    assert "by_category['새 항목']: (없음) -> 4" in message
    assert "regen_golden.py" in message and "docs/golden_tests.md" in message


def test_failure_message_notes_when_only_individual_signals_changed():
    same_counts = {"signals_total": 1, "by_category": {"x": 1}}
    message = golden_support.failure_message({**same_counts, "signals_sha256": "a"}, {**same_counts, "signals_sha256": "b"})
    assert "signals_sha256" in message and "개별 신호" in message
    assert golden_support.diff_summary({**same_counts, "signals_sha256": "a"}, {**same_counts, "signals_sha256": "a"}) == []


def test_category_keeps_ema_names_but_masks_prices_and_dates():
    cat = golden_support.category
    assert cat("EMA50 상향 돌파") == "EMA50 상향 돌파" and cat("EMA200 지지") == "EMA200 지지"
    assert cat("수평선 65,000 근접 - 지지 시험 (매수 후보)") == "수평선 # 근접 - 지지 시험 (매수 후보)"
    assert cat("추세선 (2023-10-27 33,400 → 2023-11-14 34,800) 하향 이탈 (숏) 진입") == "추세선 (#-#-# # → #-#-# #) 하향 이탈 (숏) 진입"
    assert cat("도지 - 롱 무효 (장대 음봉 10/20)") == "도지 - 롱 무효 (장대 음봉 #/#)"
