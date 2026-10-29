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


# --- 고정용 주봉 데이터 (네트워크/캐시 없이 주봉 테스트가 돌도록) ---
# data/merged/*.parquet 캐시는 git에 없어서, 새로 clone한 환경/서버에서는 Binance에서 다시 받아야 한다.
# 주봉 테스트가 그 사실에 기대지 않게 확정 시점(2017-08-14 ~ 2026-10-19 마감 주봉 480개)의 데이터를 저장소에 둔다.
# 과거 주봉은 바뀌지 않으므로 이 파일이 곧 "그때의 Binance 데이터"다. 갱신이 필요하면 weekly_data로 받아서 같은 모양의 CSV로 다시 저장.
import golden_support  # noqa: E402  (tests/ 폴더의 공용 도우미 - 고정 데이터 경로/로더)

WEEKLY_FIXTURE_PATH = golden_support.WEEKLY_FIXTURE


def _load_weekly_fixture():
    return golden_support.load_candles_csv(WEEKLY_FIXTURE_PATH)


@pytest.fixture(scope="session")
def frozen_weekly_data():
    """고정용 주봉 DataFrame(open_time/open/high/low/close/volume/close_time, UTC). 읽기 전용으로 쓰고, 고치려면 .copy()."""
    return _load_weekly_fixture()


@pytest.fixture
def weekly_offline(monkeypatch, frozen_weekly_data):
    """weekly_data.ensure_fresh_weekly_data()가 네트워크/캐시 대신 고정 데이터를 돌려주게 하고 주봉 응답 캐시를 비운다."""
    import weekly
    import weekly_data
    monkeypatch.setattr(weekly_data, "ensure_fresh_weekly_data", lambda force=False: frozen_weekly_data.copy())
    monkeypatch.setitem(weekly._cache, "data", None)
    yield


# --- 고정 일봉 데이터 / 선·존 스냅샷 (네트워크, 캐시 parquet, 실제 manual_lines.db 없이 테스트가 돌도록) ---
# 일봉 캔들은 tests/fixtures/BTCUSDT_1d_2022-01-01_2026-10-28.csv(마감된 일봉), 선/존은 manual_lines_snapshot.json.
# 세션 시작 때 data_fetcher/pipeline의 ensure_fresh_data를 이 CSV로 바꾸고, 테스트 중 requests 호출은 막는다
# (고정 데이터를 안 쓰는 테스트가 몰래 네트워크에 기대면 바로 실패해서 드러난다).
@pytest.fixture(scope="session", autouse=True)
def _offline_daily_data():
    mp = pytest.MonkeyPatch()
    golden_support.patch_offline_daily(mp)
    yield
    mp.undo()


@pytest.fixture(scope="session")
def frozen_daily_data():
    """고정용 일봉 DataFrame(2022-01-01 ~ 2026-10-28 마감 일봉 1,762개, UTC). 읽기 전용으로 쓰고, 고치려면 .copy()."""
    return golden_support.load_daily_df()


@pytest.fixture(scope="session")
def snapshot_lines():
    """선/존 스냅샷 행 목록: 존 3개(id 27/28/54, 실제 DB 행) + 합성 수평선(9001)/추세선(9002)."""
    return golden_support.load_snapshot_lines()


@pytest.fixture
def seed_snapshot_db(snapshot_lines):
    """이 테스트의 임시 lines DB(_isolate_lines_db가 이미 바꿔 둔 경로)에 스냅샷 선/존을 id 그대로 채운다."""
    golden_support.seed_lines_db(snapshot_lines)
    return snapshot_lines
