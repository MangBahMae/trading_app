"""개인 데이터 보존 guard를 가짜 세션과 임시 바이트 파일로만 검사한다."""
from types import SimpleNamespace

import pytest

import conftest as guard


RELATED_NAMES = (
    'manual-wal', 'manual-shm', 'manual-journal',
    'trades-wal', 'trades-shm', 'trades-journal',
    'history', 'history-lock',
)


@pytest.fixture
def fake_session(tmp_path, monkeypatch):
    # 실제 DB를 복사하거나 연결하지 않는다. guard가 비교할 임시 내용만 만든다.
    manual = tmp_path / 'manual-copy.db'
    trades = tmp_path / 'trades-copy.db'
    history = tmp_path / 'support-copy.jsonl'
    manual.write_bytes(b'manual baseline bytes')
    trades.write_bytes(b'trades baseline bytes')
    monkeypatch.setattr(guard, 'REAL_DB_PATH', manual)
    monkeypatch.setattr(guard, 'REAL_TRADES_DB_PATH', trades)
    monkeypatch.setenv('CCX_RAPID_DROP_SUPPORT_HISTORY', str(history))

    messages = []
    reporter = SimpleNamespace(write_line=lambda message, **_kwargs: messages.append(message))
    manager = SimpleNamespace(get_plugin=lambda name: reporter if name == 'terminalreporter' else None)
    # pytest가 실행 중인 실제 session/config를 건드리지 않는다.
    session = SimpleNamespace(config=SimpleNamespace(pluginmanager=manager), exitstatus=pytest.ExitCode.OK)
    related = {}
    for name, database in (('manual', manual), ('trades', trades)):
        related.update({f'{name}-{suffix}': database.with_name(database.name + '-' + suffix)
                        for suffix in ('wal', 'shm', 'journal')})
    related.update({'history': history, 'history-lock': history.with_name(history.name + '.lock')})
    return SimpleNamespace(session=session, manual=manual, trades=trades,
                           related=related, messages=messages)


def finish(fake):
    guard.pytest_sessionfinish(fake.session, pytest.ExitCode.OK)


def test_manual_db_mismatch_fails_the_fake_session(fake_session):
    fake = fake_session
    guard.pytest_sessionstart(fake.session)
    fake.manual.write_bytes(b'manual changed bytes')
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert any(str(fake.manual) in message for message in fake.messages)


def test_trades_db_mismatch_fails_the_fake_session(fake_session):
    fake = fake_session
    guard.pytest_sessionstart(fake.session)
    fake.trades.write_bytes(b'trades changed bytes')
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert any('매매 DB' in message for message in fake.messages)


@pytest.mark.parametrize('name', RELATED_NAMES)
def test_related_file_creation_fails_the_fake_session(fake_session, name):
    fake = fake_session
    path = fake.related[name]
    guard.pytest_sessionstart(fake.session)
    assert fake.session.config._real_related_hashes[str(path)] is None
    path.write_bytes(b'new related file')
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert any(str(path) in message for message in fake.messages)


@pytest.mark.parametrize('name', RELATED_NAMES)
def test_related_file_deletion_fails_the_fake_session(fake_session, name):
    fake = fake_session
    path = fake.related[name]
    path.write_bytes(b'existing related file')
    guard.pytest_sessionstart(fake.session)
    assert fake.session.config._real_related_hashes[str(path)] is not None
    path.unlink()
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert any(str(path) in message for message in fake.messages)


@pytest.mark.parametrize('name', RELATED_NAMES)
def test_related_file_modification_fails_the_fake_session(fake_session, name):
    fake = fake_session
    path = fake.related[name]
    path.write_bytes(b'existing related file')
    guard.pytest_sessionstart(fake.session)
    path.write_bytes(b'modified related file')
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.TESTS_FAILED
    assert any(str(path) in message for message in fake.messages)


@pytest.mark.parametrize('related_present', [False, True])
def test_unchanged_files_and_absence_preserve_success(fake_session, related_present):
    fake = fake_session
    if related_present:
        for path in fake.related.values():
            path.write_bytes(b'existing related file')
    guard.pytest_sessionstart(fake.session)
    assert len(fake.session.config._real_related_hashes) == len(RELATED_NAMES)
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.OK
    assert fake.messages == []
    assert fake.manual.read_bytes() == b'manual baseline bytes'
    assert fake.trades.read_bytes() == b'trades baseline bytes'
    assert all(path.exists() == related_present for path in fake.related.values())


def test_unchanged_guard_does_not_clear_an_existing_failure(fake_session):
    fake = fake_session
    guard.pytest_sessionstart(fake.session)
    fake.session.exitstatus = pytest.ExitCode.TESTS_FAILED
    finish(fake)
    assert fake.session.exitstatus == pytest.ExitCode.TESTS_FAILED
