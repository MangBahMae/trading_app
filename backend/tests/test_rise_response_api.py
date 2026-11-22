from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services import dashboard, rapid_drop_signals, rapid_drop_support_history as journal, rise_response
from rise_support_examples import support_example


def test_disabled_rise_does_not_read_candles_or_drawings(monkeypatch):
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_RISE_RESPONSE', False)
    def unexpected(*args):
        raise AssertionError('꺼진 실험은 데이터를 읽지 않는다.')
    monkeypatch.setattr(dashboard, '_get_base_data', unexpected)
    monkeypatch.setattr(rapid_drop_signals, 'capture_support_snapshot', unexpected)
    response = TestClient(app).get('/api/rise-response?date=2022-01-03')
    assert response.status_code == 200
    assert response.json()['enabled'] is False
    assert response.json()['events'] == []


def test_incomplete_day_and_invalid_dates(monkeypatch, frozen_daily_data):
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_RISE_RESPONSE', True)
    frame = frozen_daily_data.iloc[:4]
    monkeypatch.setattr(dashboard, '_get_base_data', lambda _: (frame, {}, []))
    day = frame.open_time.iloc[-1].date()
    with pytest.raises(ValueError, match='마감된'):
        rise_response.response_for_date(day, datetime(2022, 1, 4, 18, tzinfo=timezone.utc))
    client = TestClient(app)
    for value in ['2100-01-01', 'invalid']:
        assert client.get('/api/rise-response', params={'date': value}).status_code == 422


def test_api_date_projection_and_corrupt_journal(monkeypatch, frozen_daily_data, tmp_path):
    frame = frozen_daily_data.iloc[:21].copy()
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_RISE_RESPONSE', True)
    monkeypatch.setattr(dashboard, '_get_base_data', lambda _: (frame, {}, []))
    history = tmp_path / 'bad.jsonl'
    history.write_text('bad record', encoding='utf-8')
    monkeypatch.setenv('CCX_RAPID_DROP_SUPPORT_HISTORY', str(history))
    client = TestClient(app)
    day = frame.open_time.iloc[15].date().isoformat()
    response = client.get('/api/rise-response', params={'date': day})
    assert response.status_code == 200
    result = response.json()
    expected = rise_response.build_timeline(frame.iloc[:16])[-1]
    for field in ('date', 'events', 'market', 'long_exit', 'short_signal'):
        assert result[field] == expected[field]
    assert result['enabled'] and result['details']['warnings']
    assert history.read_text(encoding='utf-8') == 'bad record'


def test_known_past_survives_current_drawing_read_error(monkeypatch):
    frame, lines = support_example('trendline')
    journal.record_snapshot(lines, observed_at=frame.open_time.iloc[0].to_pydatetime())
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_RISE_RESPONSE', True)
    monkeypatch.setattr(dashboard.feature_flags, 'ENABLE_RAPID_DROP_SIGNALS', False)
    monkeypatch.setattr(dashboard, '_get_base_data', lambda _: (frame, {}, []))

    def unavailable():
        raise OSError('오늘 도형 조회 실패')
    monkeypatch.setattr(rapid_drop_signals, 'capture_support_snapshot', unavailable)
    client = TestClient(app)
    day = {'date': '2022-01-04'}
    data = client.get('/api/rise-response', params=day).json()
    assert data['long_exit'] == '기존 롱 종료 검토 · 상승 추세선 이탈'
    assert data['short_signal'] == '해당 없음' and data['details']['warnings']
    assert client.get('/api/rapid-drop', params=day).json()['enabled'] is False
