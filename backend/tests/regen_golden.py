"""
일봉 골든값(tests/golden/daily_golden.json) 다시 뽑기 - 의도한 규칙 변경 뒤에 쓴다. 사용법: docs/golden_tests.md

    cd backend
    .venv/Scripts/python tests/regen_golden.py            # 새로 계산해 기존 골든값과의 차이를 출력하고 파일을 갱신
    .venv/Scripts/python tests/regen_golden.py --check    # 파일은 그대로 두고 차이만 출력 (다르면 종료 코드 1)

테스트와 똑같은 환경에서 계산한다: 고정 일봉 CSV(tests/fixtures) + 선/존 스냅샷을 임시 DB에 채워서 쓰고, 네트워크/캐시/실제
manual_lines.db는 쓰지 않는다.
"""
import json
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent / "app" / "services"))

import pytest  # noqa: E402

import golden_support  # noqa: E402


def compute_summary() -> dict:
    import dashboard
    import lines_store

    mp = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            mp.setattr(lines_store, "DB_PATH", Path(tmp) / "manual_lines.db")
            golden_support.patch_offline_daily(mp)
            golden_support.seed_lines_db()
            return golden_support.summarize(dashboard.get_dashboard_data(force_refresh=True))
    finally:
        mp.undo()


def main() -> int:
    check_only = "--check" in sys.argv
    actual = compute_summary()
    path = golden_support.GOLDEN
    expected = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    if expected is None:
        print(f"기존 골든값 없음 -> {path} 새로 만든다")
        diffs = []
    else:
        diffs = golden_support.diff_summary(expected, actual)
        print("변경 없음" if not diffs else f"기존 골든값과 다른 항목 {len(diffs)}개 (기대 -> 실제):\n" + "\n".join(diffs))

    if check_only:
        return 1 if diffs else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"저장: {path}  (신호 {actual['signals_total']}건, 항목 {len(actual['by_category'])}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
