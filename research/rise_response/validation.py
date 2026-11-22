"""고정·합성 BTCUSDT 일봉을 임시 저장소에서만 재생하는 검증 서버."""
import argparse
from contextlib import ExitStack, contextmanager
import gc
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests')]

from app.services import dashboard, rapid_drop_signals, rapid_drop_support_history as journal
from app.services import rise_response, trades
import golden_support
import requests
import weekly_data

CASES = ('fixed', 'surge_doji', 'high_retry', 'trendline', 'support_fail', 'support_recover',
         'support_no_retest')


def example(case):
    if case == 'fixed':
        return golden_support.load_daily_df(), []
    if case in ('surge_doji', 'high_retry'):
        from rise_examples import market_example
        return market_example(case), []
    from rise_support_examples import support_example
    return support_example(case)


@contextmanager
def isolated(case):
    frame, lines = example(case)
    weekly = golden_support.load_candles_csv(golden_support.WEEKLY_FIXTURE)
    source = 'fixed_fixture' if case == 'fixed' else 'synthetic_demo'
    with ExitStack() as stack:
        work = Path(stack.enter_context(TemporaryDirectory(prefix='ccx-rise-')))
        stack.callback(gc.collect)
        enter = stack.enter_context
        enter(patch.object(trades, 'DB_PATH', work / 'trades.db'))
        enter(patch.object(dashboard.lines_store, 'DB_PATH', work / 'manual_lines.db'))
        enter(patch.dict(os.environ, {journal.ENV_PATH: str(work / 'history.jsonl')}))
        enter(patch.dict(dashboard._cache, data=None, computed_at=0.0))
        enter(patch.object(dashboard.feature_flags, 'ENABLE_RISE_RESPONSE', True))
        enter(patch.object(dashboard.feature_flags, 'ENABLE_RAPID_DROP_SIGNALS', True))
        enter(patch.object(rise_response, 'DATA_SOURCE', source))
        enter(patch.object(rapid_drop_signals, 'DATA_SOURCE', source))
        enter(patch.object(dashboard.pipeline, 'ensure_fresh_data', lambda *a, **kw: frame.copy()))
        # 주봉 합성 서버도 실제 주봉 다운로드를 하지 않는다.
        import data_fetcher
        enter(patch.object(data_fetcher, 'ensure_fresh_data', lambda *a, **kw: frame.copy()))
        enter(patch.object(weekly_data, 'ensure_fresh_weekly_data', lambda *a, **kw: weekly.copy()))
        enter(patch.object(requests.sessions.Session, 'send',
                           side_effect=requests.RequestException('검증 서버 외부 요청 차단')))
        dashboard.lines_store.list_lines('BTCUSDT', '1d')
        if lines:
            golden_support.seed_lines_db(lines)
            journal.record_snapshot(rapid_drop_signals.read_manual_lines(),
                                    observed_at=frame.open_time.iloc[0].to_pydatetime())
        yield frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, default='fixed')
    parser.add_argument('--port', type=int, default=18741)
    parser.add_argument('--frontend', action='store_true', help='같은 주소에서 frontend/dist 제공')
    args = parser.parse_args()
    from app.main import app
    from fastapi.staticfiles import StaticFiles
    import uvicorn
    with isolated(args.case):
        if args.frontend:
            app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True))
        uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
