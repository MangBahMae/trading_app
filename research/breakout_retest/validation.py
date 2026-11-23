"""실제 사용자 저장 경로를 격리한 돌파·재시험 검증 서버와 합성 마감봉."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.rise_response import validation as rise_validation
from app.services import dashboard, rapid_drop_support_history as journal

CASES = ('fixed', 'zone_hold', 'wick', 'zone_failure', 'support_recover', 'slope_down',
         'slope_up', 'slope_short', 'version_lifecycle', 'expiry', 'gentle', 'bear_rebound')
START = '2022-01-01'


def _drawing(kind='zone', **coords):
    fields = dict(id=73, symbol='BTCUSDT', interval='1d', line_type=kind,
                  time1=START, time2='2022-12-31', price1=102., price2=100.,
                  created_at=START + 'T00:00:00Z')
    if kind == 'horizontal':
        fields.update(time1=None, time2=None, price2=None)
    return dict(fields, **coords)


def _series(closes):
    return [(closes[max(i - 1, 0)], max(closes[max(i - 1, 0)], value) + .15,
             min(closes[max(i - 1, 0)], value) - .15, value) for i, value in enumerate(closes)]


def example(case):
    """가격·기록 시점은 재현을 위한 합성 입력. 고정 BTC에는 도형을 주입하지 않는다."""
    if case == 'fixed':
        return rise_validation.example('fixed')
    line = _drawing()
    if case == 'zone_hold':
        bars = [(99, 99.8, 98.8, 99), (99, 104.4, 98.5, 104), (104, 104.5, 101.8, 103),
                (103, 105, 102.5, 104), (104, 104.4, 98.4, 99), (99, 99.4, 97, 98)]
    elif case == 'wick':
        bars = [(99, 99.8, 98.8, 99), (99, 103, 98.8, 99.5), (99.5, 99.9, 99, 99.2)]
    elif case == 'zone_failure':
        bars = [(99, 99.8, 98.8, 99), (99, 103.5, 98.7, 103), (103, 103.3, 100.5, 101),
                (101, 101.4, 98.5, 99), (99, 101, 97.8, 98.5), (98.5, 99.2, 97.5, 98)]
    elif case == 'support_recover':
        bars = [(104, 105, 103, 104), (104, 104.5, 97.6, 98), (98, 103, 97.7, 102),
                (102, 104, 101.5, 103), (103, 105, 102.5, 104)]
    elif case in ('slope_down', 'slope_up', 'slope_short'):
        if case == 'slope_down':
            # 두 좌표 확보 후 1/3 선값 102 돌파, 1/4에만 선값 100 재시험.
            line = _drawing('trend', price1=106., price2=104., time2='2022-01-02')
            bars = [(103, 103.4, 102.6, 103), (103, 103.6, 102.5, 103), (103, 104, 102.5, 103.5),
                    (103.5, 104, 99.9, 103), (103, 104, 102.8, 103.5)]
        else:
            line = _drawing('trend', price1=98., price2=99., time2='2022-01-02')
            bars = [(101, 102, 100, 101), (101, 102, 100, 101), (101, 102, 98.5, 99),
                    (99, 102.5, 98.9, 102), (102, 103.5, 101.8, 103), (103, 105, 102.5, 104)]
            if case == 'slope_short':
                bars[3:] = [(99, 101.2, 98, 98.5), (98.5, 99, 97.8, 98), (98, 99.4, 97.6, 98.5)]
    elif case == 'version_lifecycle':
        bars = _series([99, 103, 104, 106, 106.1, 106, 104.9, 105.5, 105.6, 105.7])
        bars[4] = (106, 106.4, 104.9, 106.1)
        bars[8] = (105.5, 106.2, 105, 105.6)
    elif case == 'expiry':
        line = _drawing('horizontal', price1=100.)
        bars = _series([99, 104] + [104] * 9 + [100, 104, 103] + [105] * 10)
        bars[13] = (104, 104.5, 100, 103)
    elif case == 'gentle':
        line = _drawing('horizontal', price1=102.1)
        bars = _series([round(90 + i * .2, 2) for i in range(68)])
    elif case == 'bear_rebound':
        line = _drawing('horizontal', price1=111.)
        bars = _series([round(130 - i * .3, 2) for i in range(76)] + [108.4, 109, 109.9, 111.5, 111.8, 112])
        bars[-2] = (111.5, 112, 110.95, 111.8)
    else:
        raise ValueError(f'알 수 없는 합성 입력 {case}')
    frame = pd.DataFrame(bars, columns=['open', 'high', 'low', 'close'])
    frame['open_time'] = pd.date_range(START, periods=len(bars), tz='UTC')
    frame['close_time'] = frame.open_time + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    frame['volume'] = 100.
    return frame, [line]


@contextmanager
def isolated(case):
    from app.services import breakout_signals
    fixture = example(case)
    source = 'fixed_fixture' if case == 'fixed' else 'synthetic_demo'
    with rise_validation.isolated(case, fixture=fixture) as frame, \
            patch.object(dashboard.feature_flags, 'ENABLE_BREAKOUT_RETEST', True), \
            patch.object(breakout_signals, 'DATA_SOURCE', source):
        if case == 'version_lifecycle':
            # 같은 ID의 좌표 교체, 삭제, 재등록을 각각 그 시점의 기록으로 남긴다.
            replaced = dict(fixture[1][0], price1=105., price2=104.)
            for index, drawings in [(2, [replaced]), (5, []), (6, [replaced])]:
                journal.record_snapshot(drawings, observed_at=frame.open_time.iloc[index].to_pydatetime())
            dashboard.lines_store.update_zone(73, START, '2022-12-31', 105., 104.)
        yield frame


def main():
    from app.main import app
    from fastapi.staticfiles import StaticFiles
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, default='fixed')
    parser.add_argument('--port', type=int, default=18742)
    parser.add_argument('--frontend', action='store_true')
    args = parser.parse_args()
    with isolated(args.case):
        if args.frontend:
            app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True))
        uvicorn.run(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
