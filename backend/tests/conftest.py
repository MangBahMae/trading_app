"""
테스트 공통 설정 - 테스트가 실제 사용자 데이터(data/merged/manual_lines.db)를 건드리지 않게 한다.

사용자가 차트에 직접 그린 수평선/추세선/존이 이 DB에 들어 있다. 예전엔 test_lines_crud.py가 실제
DB 경로에 (전용 심볼 "__TEST__"로) 쓰고 지웠는데, 행은 정리돼도 SQLite 파일 자체(AUTOINCREMENT
카운터, 페이지)가 매 실행마다 바뀌어서 git에 변경으로 잡혔다.

그래서 모든 테스트에 자동으로 lines_store.DB_PATH를 임시 파일로 바꿔 끼운다:
- dashboard.py가 쓰는 bare 모듈 "lines_store"
- test_lines_crud.py가 importlib로 따로 로드하는 원본/이식본 복사본(sys.modules에 별칭으로 등록됨)
그리고 세션이 끝날 때 실제 DB 파일이 바뀌었는지 확인해서, 어떤 테스트가 또 실제 DB에 쓰면 눈에 띄게 알린다.
"""
import hashlib
import sys
from pathlib import Path

import pytest

SERVICES_DIR = Path(__file__).resolve().parents[1] / "app" / "services"
sys.path.insert(0, str(SERVICES_DIR))

import lines_store  # noqa: E402,F401  (dashboard.py가 쓰는 것과 같은 bare 모듈 객체 - 먼저 로드해 둔다)

REAL_DB_PATH = Path(lines_store.DB_PATH)


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


@pytest.fixture(autouse=True)
def _isolate_lines_db(tmp_path, monkeypatch):
    """lines_store 계열 모듈(DB_PATH 속성이 있는 *lines_store)의 DB 경로를 테스트마다 새 임시 파일로."""
    tmp_db = tmp_path / "manual_lines.db"
    for name, module in list(sys.modules.items()):
        if name.rsplit(".", 1)[-1].endswith("lines_store") and hasattr(module, "DB_PATH"):
            monkeypatch.setattr(module, "DB_PATH", tmp_db)
    yield tmp_db


def pytest_sessionstart(session):
    session.config._real_lines_db_hash = _sha256(REAL_DB_PATH)


def pytest_sessionfinish(session, exitstatus):
    before = getattr(session.config, "_real_lines_db_hash", None)
    after = _sha256(REAL_DB_PATH)
    if before != after:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        msg = (
            f"경고: 테스트 실행 중 실제 DB({REAL_DB_PATH})가 바뀌었습니다. "
            "테스트가 임시 DB를 안 쓰고 실제 DB에 썼거나, 테스트와 동시에 개발 서버/사용자가 선을 그렸을 수 있습니다."
        )
        if reporter is not None:
            reporter.write_line(msg, red=True)
        else:
            print(msg)
