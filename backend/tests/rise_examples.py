"""기존 판별기와 검증 화면에서 함께 재생하는 합성 일봉. 실제 차트 사진의 시세가 아니다."""
import pandas as pd


EXAMPLES = {
    'surge_doji': [
        (100, 100.9, 99.2, 100), (100, 100.5, 99.5, 100.1), (100.1, 100.7, 99.6, 100),
        (100, 105.4, 99.8, 105), (105, 105.7, 104.5, 105.03), (105.03, 107.4, 104.9, 107),
    ],
    'high_retry': [
        (100, 109.5, 99.8, 109), (109, 110, 108.6, 109.2), (109.2, 109.9, 108.7, 109.4),
        (109.4, 110.1, 108.9, 109.3), (109.3, 109.5, 106.5, 107), (107, 109.8, 106.8, 109.1),
        (109.1, 109.4, 106.1, 106.6), (106.6, 108, 105.8, 107.2), (107.2, 113, 107, 112),
    ],
}


def market_example(name):
    frame = pd.DataFrame(EXAMPLES[name], columns=['open', 'high', 'low', 'close'])
    frame['volume'] = 100.0
    frame['open_time'] = pd.date_range('2022-01-01', periods=len(frame), tz='UTC')
    frame['close_time'] = frame.open_time + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    return frame
