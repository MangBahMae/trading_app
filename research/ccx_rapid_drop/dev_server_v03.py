"""검증 전용 로컬 서버. 고정/합성 입력과 임시 DB만 사용하며 운영 실행 경로가 아니다."""
import argparse
from contextlib import ExitStack
import gc
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
    demo = parser.add_mutually_exclusive_group()
    demo.add_argument('--synthetic', action='store_true', help='합성 OHLCV와 합성 지지로 표시 검사')
    demo.add_argument('--doji-example', choices=('manual', 'unknown'),
                      help='100→99→94→94(도지)→90 예시. 같은 가격에서 94 수동선의 유무를 비교')
    parser.add_argument('--port', type=int, default=8000, help='격리 검증 서버의 로컬 포트')
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
    if args.synthetic or args.doji_example:
        values = [(108,109,107,108,100), (108,109,106,107,100), (107,108,105,106,100),
                  (106,107,101,102,100), (102,103,96,97,100), (95,97,92,95,300),
                  (95,101,94,100,80), (96,96.2,91,95.5,90),
                  # 아래 네 봉은 화면 안전 확인용이다. 전략 기준은 바꾸지 않는다.
                  (96,96.2,91.5,95.5,90), (95,96,90,91,90),
                  (91,98,90,97,90), (97,98,96.5,97,90)]
        if args.doji_example:
            values = [(101,102,99,100,100), (100,101,98,99,100), (99,100,93.5,94,100),
                      (94,95,93,94,100), (94,94.5,89,90,100)]
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
    rapid_drop_signals.DATA_SOURCE = 'synthetic_demo' if args.synthetic or args.doji_example else 'fixed_fixture'
    with ExitStack() as cleanup:
        work = cleanup.enter_context(tempfile.TemporaryDirectory(prefix='ccx-v03-'))
        # 기존 선·매매 서비스가 반환한 SQLite 연결의 순환 참조를 임시 폴더 삭제 전에 해제한다.
        cleanup.callback(gc.collect)
        dashboard.lines_store.DB_PATH = Path(work)/'manual_lines.db'
        trades.DB_PATH = Path(work)/'trades.db'
        os.environ['CCX_RAPID_DROP_SUPPORT_HISTORY'] = str(Path(work)/'support_history.jsonl')
        dashboard.lines_store.list_lines('BTCUSDT','1d')
        if args.synthetic:
            dashboard.lines_store.add_zone('BTCUSDT','1d','2022-01-01','2022-02-01',96,94)
        elif args.doji_example == 'manual':
            dashboard.lines_store.add_horizontal_line('BTCUSDT', '1d', 94)
        if args.synthetic or args.doji_example == 'manual':
            journal.record_snapshot(rapid_drop_signals.read_manual_lines(), observed_at=datetime(2022,1,1,tzinfo=timezone.utc))
        from app.main import app
        print(f'검증 입력={rapid_drop_signals.DATA_SOURCE}; 사용자 DB 미사용', flush=True)
        try:
            uvicorn.run(app, host='127.0.0.1', port=args.port)
        except KeyboardInterrupt:
            pass  # Windows에서 정상 종료 후 다시 전달된 Ctrl+C


if __name__ == '__main__':
    main()
