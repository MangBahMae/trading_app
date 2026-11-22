"""급락 실험 API: 임시 지지 이력과 합성/고정 일봉으로 실제 라우터를 검사한다."""
import hashlib
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import rapid_drop_signals as svc
from app.services import rapid_drop_support_history as journal
from test_rapid_drop_signals import BOUNCE, DOJI, HAMMER, synthetic_frame

REAL_CAPTURE = svc.capture_support_snapshot
REAL_CLOSED_FRAME = svc.closed_frame


@pytest.fixture
def api(tmp_path, monkeypatch):
    history = tmp_path / 'support_versions.jsonl'
    monkeypatch.setenv(journal.ENV_PATH, str(history))
    monkeypatch.setattr(svc.dashboard.feature_flags, 'ENABLE_RAPID_DROP_SIGNALS', True)
    monkeypatch.setattr(svc, 'DATA_SOURCE', 'synthetic_demo')
    monkeypatch.setattr(svc, 'capture_support_snapshot', lambda: None)
    frame = synthetic_frame(DOJI, BOUNCE, HAMMER, HAMMER)
    monkeypatch.setattr(svc.dashboard, '_get_base_data', lambda *_: (frame.copy(), {}, []))
    original_closed = svc.closed_frame
    monkeypatch.setattr(svc, 'closed_frame', lambda candles, now=None: original_closed(candles, pd.Timestamp('2022-02-01', tz='UTC')))
    return TestClient(app), history


def record_support(path, observed_at='2022-01-01T00:00:00+00:00', price=96):
    journal.record_snapshot([dict(id=7, symbol='BTCUSDT', interval='1d', line_type='horizontal',
                                  price1=price, created_at='2000-01-01T00:00:00Z')], observed_at=observed_at, path=path)


def test_feature_off_skips_market_and_support_access_and_preserves_daily_weekly_output(monkeypatch, tmp_path, weekly_offline):
    client = TestClient(app)
    monkeypatch.setattr(svc.dashboard.feature_flags, 'ENABLE_RAPID_DROP_SIGNALS', False)
    history = tmp_path / 'off_history.jsonl'
    monkeypatch.setenv(journal.ENV_PATH, str(history))
    before_daily = client.get('/api/dashboard').json()
    before_weekly = client.get('/api/dashboard/weekly').json()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('OFF이면 시장·지지 계산을 호출하면 안 됨')
    with monkeypatch.context() as guard:
        guard.setattr(svc.dashboard, '_get_base_data', forbidden)
        guard.setattr(svc, 'capture_support_snapshot', forbidden)
        response = client.get('/api/rapid-drop?date=2023-06-11')
    assert response.status_code == 200
    assert response.json()['enabled'] is False
    assert response.json()['signals'] == response.json()['maintained_candidates'] == []
    assert not history.exists()
    assert client.get('/api/dashboard').json() == before_daily
    assert client.get('/api/dashboard/weekly').json() == before_weekly


@pytest.mark.parametrize('query', ['', '?date=not-a-date', '?date=2022-02-30', '?date=2022-03-01'])
def test_api_rejects_missing_invalid_or_unavailable_date(api, query):
    client, _ = api
    assert client.get('/api/rapid-drop' + query).status_code == 422


def test_api_reports_data_source_schema_confirmation_and_maintained_candidate(api):
    client, history = api
    record_support(history)
    born = client.get('/api/rapid-drop?date=2022-01-06')
    assert born.status_code == 200
    payload = born.json()
    assert payload['enabled'] is True and payload['schema_version'] == '0.3'
    assert payload['symbol'] == 'BTCUSDT' and payload['interval'] == '1d'
    assert payload['data_source'] == 'synthetic_demo'
    assert payload['support']['status'] == 'known'
    candidate, = [s for s in payload['signals'] if s['type'] == 'manual_first_long']
    assert candidate['confirmed_at'] == '2022-01-07T00:00:00+00:00'
    assert candidate['reference']['support_id'] == 'manual:7'
    assert candidate['event_ids']
    later = client.get('/api/rapid-drop?date=2022-01-07').json()
    assert candidate in later['maintained_candidates']
    assert candidate in later['history']
    assert not [s for s in later['signals'] if s['type'] == 'manual_first_long']
    assert client.get('/api/rapid-drop?date=2022-01-06').json() == payload


def test_api_records_retest_once_with_explicit_draft_policy_source(api):
    client, history = api
    record_support(history)
    data = client.get('/api/rapid-drop?date=2022-01-08').json()
    candidate, = [s for s in data['signals'] if s['type'] == 'manual_retest_long']
    later = client.get('/api/rapid-drop?date=2022-01-09').json()
    assert candidate in later['maintained_candidates']
    assert not [s for s in later['signals'] if s['type'] == 'manual_retest_long']
    assert data['policy_source'].startswith('rapid-drop-v03-draft')


def test_enabled_experimental_api_preserves_existing_daily_and_weekly_payloads(monkeypatch, tmp_path, weekly_offline):
    monkeypatch.setattr(svc.dashboard.feature_flags, 'ENABLE_RAPID_DROP_SIGNALS', True)
    monkeypatch.setenv(journal.ENV_PATH, str(tmp_path / 'independent_history.jsonl'))
    client = TestClient(app)
    daily = client.get('/api/dashboard').json()
    weekly = client.get('/api/dashboard/weekly').json()
    response = client.get('/api/rapid-drop?date=2023-06-11')
    assert response.status_code == 200 and response.json()['enabled'] is True
    assert [s['type'] for s in response.json()['signals'] if s['direction'] == 'long'] == ['auto_retest_long']
    assert response.json()['support']['status'] == 'unconfirmed'
    assert client.get('/api/dashboard').json() == daily
    assert client.get('/api/dashboard/weekly').json() == weekly


def test_api_leaves_dates_before_recording_unconfirmed_despite_ancient_created_at(api):
    client, history = api
    record_support(history, '2022-01-08T12:00:00+00:00')
    payload = client.get('/api/rapid-drop?date=2022-01-06').json()
    assert payload['support']['status'] == 'unconfirmed'
    assert payload['support']['recording_started_at'] is None
    assert not [s for s in payload['signals'] if s['type'] == 'manual_first_long']


def test_future_support_versions_do_not_rewrite_an_earlier_api_response(api):
    client, history = api
    record_support(history)
    before = client.get('/api/rapid-drop?date=2022-01-06').json()
    record_support(history, '2022-01-09T12:00:00+00:00', price=80)
    assert client.get('/api/rapid-drop?date=2022-01-06').json() == before


def test_corrupt_support_journal_fails_closed_without_overwriting_it(api):
    client, history = api
    history.write_bytes(b'{broken history}\n')
    before = history.read_bytes()
    response = client.get('/api/rapid-drop?date=2022-01-06')
    assert response.status_code == 200
    payload = response.json()
    assert payload['enabled'] is True
    assert payload['support']['status'] == 'unconfirmed'
    assert any('지지 이력 확인 실패' in warning for warning in payload['warnings'])
    assert not [s for s in payload['signals'] if s['type'] == 'manual_first_long']
    assert history.read_bytes() == before


def test_api_cannot_serve_a_still_open_daily_bar(api, monkeypatch):
    client, _ = api
    frame = synthetic_frame(DOJI, BOUNCE, HAMMER)
    monkeypatch.setattr(svc.dashboard, '_get_base_data', lambda *_: (frame.copy(), {}, []))
    monkeypatch.setattr(svc, 'closed_frame', lambda candles, now=None:
                        REAL_CLOSED_FRAME(candles, pd.Timestamp('2022-01-08T12:00:00Z')))
    assert client.get('/api/rapid-drop?date=2022-01-08').status_code == 422
    assert client.get('/api/rapid-drop?date=2022-01-07').status_code == 200


@pytest.mark.parametrize('has_level', [True, False])
def test_chart_example_same_five_prices_with_and_without_known_line(api, monkeypatch, has_level):
    client, history = api
    if has_level:
        record_support(history, price=94)
    rows = [(101,102,99,100,100), (100,101,98,99,100), (99,100,93.5,94,100),
            (94,95,93,94,100), (94,94.5,89,90,100)]
    frame = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'])
    frame['open_time'] = pd.date_range('2022-01-01', periods=5, tz='UTC')
    monkeypatch.setattr(svc.dashboard, '_get_base_data', lambda *_: (frame.copy(), {}, []))
    doji = client.get('/api/rapid-drop?date=2022-01-04').json()
    after = client.get('/api/rapid-drop?date=2022-01-05').json()
    assert doji['market']['phase'] == 'sharp_drop'
    assert round(doji['market']['recent_speed'] * 100, 2) == -2.59
    assert doji['summary']['title'] == ('롱 후보 · 수동 지지 첫 반응' if has_level else '도지 관찰 · 지지 미확인')
    assert doji['summary']['badge'] == 'new'
    if has_level:
        candidate, = [s for s in doji['signals'] if s['direction'] == 'long']
        assert candidate['reaction_low'] == 93
        assert candidate['reference']['bottom'] == candidate['reference']['top'] == 94
        assert after['summary']['title'] == '기존 후보 무효'
        invalid, = [s for s in after['signals'] if s['type'] == 'candidate_invalidated']
        assert invalid['previous_candidate_ids'] == [candidate['id']]
        assert candidate in after['history'] and not after['maintained_candidates']
    else:
        assert not doji['active_anchors'] and not any(s['direction'] == 'long' for s in after['history'])
    assert client.get('/api/rapid-drop?date=2022-01-04').json() == doji


def test_readonly_manual_adapter_reads_temporary_db_without_changing_db_bytes(tmp_path, monkeypatch):
    history = tmp_path / 'captured.jsonl'
    monkeypatch.setenv(journal.ENV_PATH, str(history))
    line_id = svc.dashboard.lines_store.add_horizontal_line('BTCUSDT', '1d', 96)
    db = svc.dashboard.lines_store.DB_PATH
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    result = REAL_CAPTURE()
    assert result['recorded'] is True
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    rows = svc.read_manual_lines()
    assert [row['id'] for row in rows] == [line_id]
    recorded = journal.load_levels(as_of=datetime.now(timezone.utc).date(), path=history)
    assert recorded['levels'][0]['support_id'] == f'manual:{line_id}'


def test_readonly_manual_adapter_releases_its_sqlite_handle(monkeypatch):
    svc.dashboard.lines_store.list_lines('BTCUSDT', '1d')
    connect = sqlite3.connect
    opened = []

    def record_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, 'connect', record_connection)
    svc.read_manual_lines()
    connection, = opened
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')
