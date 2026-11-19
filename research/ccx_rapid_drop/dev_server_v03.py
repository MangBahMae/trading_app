"""검증 전용 로컬 서버. 고정/합성 입력과 임시 DB만 사용하며 운영 실행 경로가 아니다."""
import argparse
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO/'backend'))
sys.path.insert(0, str(REPO/'backend/tests'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic', action='store_true', help='합성 OHLCV와 합성 지지로 표시 검사')
    args = parser.parse_args()
    os.environ['CCX_ENABLE_RAPID_DROP_SIGNALS'] = '1'
    import pandas as pd
    import uvicorn
    from app.services import dashboard, trades, rapid_drop_signals
    import data_fetcher
    import weekly_data
    import golden_support
    import requests
    from app.services import rapid_drop_support_history as journal
    from datetime import datetime, timezone
    df = golden_support.load_daily_df()
    if args.synthetic:
        values = [(108,109,107,108,100), (108,109,106,107,100), (107,108,105,106,100),
                  (106,107,101,102,100), (102,103,96,97,100), (95,97,92,95,300),
                  (95,101,94,100,80), (96,96.2,91,95.5,90)]
        df = pd.DataFrame(values, columns=['open','high','low','close','volume'])
        df['open_time'] = pd.date_range('2022-01-01', periods=len(df), tz='UTC')
        df['close_time'] = df['open_time']+pd.Timedelta(days=1)-pd.Timedelta(milliseconds=1)
    data_fetcher.ensure_fresh_data = lambda *a, **kw: df.copy()
    dashboard.pipeline.ensure_fresh_data = lambda *a, **kw: df.copy()
    weekly_df = golden_support.load_candles_csv(golden_support.WEEKLY_FIXTURE)
    weekly_data.ensure_fresh_weekly_data = lambda *a, **kw: weekly_df.copy()
    def blocked(*a, **kw):
        raise requests.RequestException('검증 전용 서버: 외부 네트워크 미사용')
    requests.get = blocked
    rapid_drop_signals.DATA_SOURCE = 'synthetic_demo' if args.synthetic else 'fixed_fixture'
    with tempfile.TemporaryDirectory(prefix='ccx-v03-') as work:
        dashboard.lines_store.DB_PATH = Path(work)/'manual_lines.db'
        trades.DB_PATH = Path(work)/'trades.db'
        os.environ['CCX_RAPID_DROP_SUPPORT_HISTORY'] = str(Path(work)/'support_history.jsonl')
        dashboard.lines_store.list_lines('BTCUSDT','1d')
        if args.synthetic:
            dashboard.lines_store.add_zone('BTCUSDT','1d','2022-01-01','2022-02-01',96,94)
            journal.record_snapshot(rapid_drop_signals.read_manual_lines(), observed_at=datetime(2022,1,1,tzinfo=timezone.utc))
        from app.main import app
        print(f'검증 입력={rapid_drop_signals.DATA_SOURCE}; 사용자 DB 미사용', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
