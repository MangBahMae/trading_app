"""기존 판별기와 검증 화면에서 함께 재생하는 합성 일봉. 실제 차트 사진의 시세가 아니다."""
import pandas as pd
from math import pi, sin


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
    if name == 'gentle_rise':
        # 8봉마다 작은 계단을 밟으며 상승, 끝에 분리된 눌림·고점 재시도·밀림.
        closes = [100 + 0.28*i + 0.85*sin(2*pi*i/8) for i in range(65)]
        closes.extend([119, 120.5, 121.5, 119.3, 118, 119.1, 120.9, 120.1, 117.8])
    elif name in ('mixed_structure', 'mixed_fall'):
        # 수평 준비 구간 뒤 하락, 반등, 상승과 재하락. 배열 전환 중의 구조를 확인한다.
        closes = [110.] * 55
        for length, drift in [(32, -0.35), (40, 0.32), (32, -0.3), (32, 0.28)]:
            start = closes[-1]
            closes.extend(start + drift*i + 1.2*sin(2*pi*i/8) for i in range(1, length+1))
        if name == 'mixed_fall':
            closes = [220 - close for close in closes]
    else:
        closes = None
    rows = EXAMPLES[name] if closes is None else _bars_from_closes(closes)
    frame = pd.DataFrame(rows, columns=['open', 'high', 'low', 'close'])
    frame['volume'] = 100.0
    frame['open_time'] = pd.date_range('2022-01-01', periods=len(frame), tz='UTC')
    frame['close_time'] = frame.open_time + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    return frame


def _bars_from_closes(closes):
    bars = []
    for i, close in enumerate(closes):
        op = closes[i-1] if i else close
        # 선형 구간 양 끝의 종가와 다음 시가가 같더라도 꼬리의 방향은 구별한다.
        high = max(op, close) + (0.18 if close > op else 0.08)
        low = min(op, close) - (0.18 if close < op else 0.08)
        bars.append((op, high, low, close))
    return bars
