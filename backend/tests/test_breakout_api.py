"""마감일·독립 플래그·도형 이력의 공개 API 계약. 모든 저장소는 conftest에서 격리한다."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services import breakout_signals, dashboard, rapid_drop_signals, rapid_drop_support_history as journal
from rise_support_examples import support_example


def test_off_does_not_read_market_or_storage(monkeypatch):
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_BREAKOUT_RETEST', False)

    def forbidden(*args):
        pytest.fail('꺼진 실험이 데이터를 조회했습니다.')

    monkeypatch.setattr(dashboard, '_get_base_data', forbidden)
    monkeypatch.setattr(rapid_drop_signals, 'capture_support_snapshot', forbidden)
    result = TestClient(app).get('/api/breakout-retest?date=2022-01-01')
    assert result.status_code == 200
    assert result.json()['enabled'] is False
    assert result.json()['events'] == result.json()['active'] == []


def test_close_time_and_unknown_coordinates(monkeypatch, frozen_daily_data):
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_BREAKOUT_RETEST', True)
    frame = frozen_daily_data.iloc[:4]
    monkeypatch.setattr(dashboard, '_get_base_data', lambda _: (frame, {}, []))
    day = date(2022, 1, 4)
    with pytest.raises(ValueError, match='마감된'):
        breakout_signals.response_for_date(day, datetime(2022, 1, 4, 18, tzinfo=timezone.utc))
    client = TestClient(app)
    for value in ('2022-01-05', 'invalid'):
        assert client.get('/api/breakout-retest', params={'date': value}).status_code == 422
    data = client.get('/api/breakout-retest', params={'date': day}).json()
    assert data['enabled'] and data['market_label'] != '실험 OFF'
    assert data['history_status'] == 'unconfirmed' and not data['events']
    journal.record_snapshot([dict(id=9, line_type='horizontal', price1=100)], '2099-01-01T00:00:00Z')
    # 미래 기록을 추가한 뒤에도 해당 날짜의 결과는 같아야 한다. 현재 읽기는 여기서 고정한다.
    monkeypatch.setattr(rapid_drop_signals, 'capture_support_snapshot', lambda: None)
    assert client.get('/api/breakout-retest', params={'date': day}).json() == data


def test_breakout_only_records_current_drawing_edit(monkeypatch, tmp_path):
    for name in ('ENABLE_BREAKOUT_RETEST', 'ENABLE_RISE_RESPONSE', 'ENABLE_RAPID_DROP_SIGNALS'):
        monkeypatch.setattr(dashboard.feature_flags, name, name == 'ENABLE_BREAKOUT_RETEST')
    path = tmp_path / 'breakout-history.jsonl'
    monkeypatch.setenv(journal.ENV_PATH, str(path))
    added = dashboard.add_horizontal_line(100)
    versions = journal.load_drawing_versions('2099-01-01')['versions']
    assert len(versions) == 1 and versions[0]['support_id'] == f'manual:{added}'
    assert journal.load_drawing_versions('2022-01-01')['status'] == 'unconfirmed'


def test_panels_read_one_version_during_simultaneous_requests(monkeypatch, tmp_path):
    path = tmp_path / 'concurrent.jsonl'
    monkeypatch.setenv(journal.ENV_PATH, str(path))
    dashboard.lines_store.add_horizontal_line('BTCUSDT', '1d', 100)
    today = datetime.now(timezone.utc).date()
    start = Barrier(4)

    def read():
        start.wait(timeout=10)
        history, warnings = rapid_drop_signals.drawings_as_of(today)
        assert not warnings
        version, = history['versions']
        return version['key']

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(read) for _ in range(4)]
        assert len({f.result() for f in futures}) == 1
    assert len(path.read_bytes().splitlines()) == 1


def test_same_short_id_and_independent_legacy_endpoints(monkeypatch):
    frame, lines = support_example('support_fail')
    journal.record_snapshot(lines, frame.open_time.iloc[0].isoformat())
    monkeypatch.setattr(dashboard, '_get_base_data', lambda _: (frame, {}, []))
    client = TestClient(app)
    q = dict(date='2022-01-03')
    flags = dashboard.feature_flags
    for name in ('ENABLE_RISE_RESPONSE', 'ENABLE_RAPID_DROP_SIGNALS'):
        monkeypatch.setattr(flags, name, True)
    monkeypatch.setattr(flags, 'ENABLE_BREAKOUT_RETEST', False)
    baseline = [client.get(p, params=q).json() for p in ('/api/rise-response', '/api/rapid-drop')]
    monkeypatch.setattr(flags, 'ENABLE_BREAKOUT_RETEST', True)
    current = client.get('/api/breakout-retest', params=q).json()
    assert current['known_drawings'] == 1 and current['history_status'] == 'recorded'
    short, = [e for e in current['events'] if e['type'] == 'short_candidate']
    assert short['id'] == next(e['id'] for e in baseline[0]['events'] if e['kind'] == 'support_retest_short')
    assert [client.get(p, params=q).json() for p in ('/api/rise-response', '/api/rapid-drop')] == baseline
    monkeypatch.setattr(flags, 'ENABLE_RISE_RESPONSE', False)
    assert client.get('/api/breakout-retest', params=q).json() == current


def test_new_version_with_future_second_point_does_not_hide_replacement(tmp_path):
    path = tmp_path / 'history.jsonl'
    old = dict(id=3, line_type='horizontal', price1=100)
    new = dict(id=3, line_type='trend', time1='2022-01-02', price1=104,
               time2='2022-01-09', price2=99)
    journal.record_snapshot([old], '2022-01-01T12:00:00Z', path)
    before = journal.load_drawing_versions('2022-01-03', path)
    journal.record_snapshot([new], '2022-01-04T12:00:00Z', path)
    assert before == journal.load_drawing_versions('2022-01-03', path)
    replaced, = journal.load_drawing_versions('2022-01-05', path)['versions']
    assert replaced['end_reason'] == 'replaced' and replaced['through'] == '2022-01-03'
    assert journal.load_drawing_versions('2022-01-09', path)['versions'][-1]['known_from'] == '2022-01-09'
