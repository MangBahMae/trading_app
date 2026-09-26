"""
scripts/lines_store.py(원본)과 backend/app/services/lines_store.py(이식본)이
정확히 같은 SQLite 파일(manual_lines.db)을 보고, CRUD가 서로 호환되는지 검증.

lines_store.py는 sqlite3/datetime/pathlib 표준 라이브러리만 쓰고 다른
scripts/*.py 모듈을 bare-import하지 않아서(pipeline.py 그래프와 달리 이름
충돌 위험이 없음), importlib로 원본/이식본을 별도 별칭 모듈로 같은 프로세스에
동시에 로드해도 안전하다 - pipeline.py 회귀 테스트를 서브프로세스로 격리한
이유(test_regression_pipeline.py 참고)가 여기엔 해당하지 않는다.

실제 그어두신 BTCUSDT/1d 선을 건드리지 않도록 전용 테스트 심볼을 쓰고,
끝나면(성공/실패 무관) 반드시 정리한다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

TEST_SYMBOL = "__TEST__"
TEST_INTERVAL = "__TEST__"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


original = _load_module("original_lines_store", REPO_ROOT / "scripts" / "lines_store.py")
ported = _load_module("ported_lines_store", REPO_ROOT / "backend" / "app" / "services" / "lines_store.py")


def _cleanup():
    for line in ported.list_lines(TEST_SYMBOL, TEST_INTERVAL):
        ported.delete_line(line["id"])


@pytest.fixture(autouse=True)
def cleanup_test_lines():
    _cleanup()
    yield
    _cleanup()


def test_original_and_ported_point_to_same_db_file():
    assert original.DB_PATH == ported.DB_PATH


def test_crud_is_shared_between_original_and_ported():
    # 원본으로 추가 -> 이식본으로 조회 (같은 파일을 보는지 확인)
    line_id = original.add_horizontal_line(TEST_SYMBOL, TEST_INTERVAL, 12345.0)
    ported_lines = ported.list_lines(TEST_SYMBOL, TEST_INTERVAL)
    assert any(line["id"] == line_id and line["price1"] == 12345.0 for line in ported_lines)

    # 이식본으로 추세선 추가 -> 원본으로 조회
    trend_id = ported.add_trend_line(
        TEST_SYMBOL, TEST_INTERVAL, "2024-01-01", 100.0, "2024-02-01", 200.0,
    )
    original_lines = original.list_lines(TEST_SYMBOL, TEST_INTERVAL)
    assert any(line["id"] == trend_id for line in original_lines)
    assert len(original_lines) == 2  # 수평선 1개 + 추세선 1개

    # 이식본으로 삭제 -> 원본으로 조회하면 사라짐
    ported.delete_line(line_id)
    original_lines_after = original.list_lines(TEST_SYMBOL, TEST_INTERVAL)
    assert not any(line["id"] == line_id for line in original_lines_after)
    assert any(line["id"] == trend_id for line in original_lines_after)

    # 원본으로 나머지도 삭제 -> 이식본으로 조회하면 완전히 빔
    original.delete_line(trend_id)
    assert ported.list_lines(TEST_SYMBOL, TEST_INTERVAL) == []
