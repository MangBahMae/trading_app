"""운영 좌표·원본 사진을 사용하지 않은 수동 도형 합성 사례."""
import pandas as pd


def support_example(name):
    if name == "bull_trendline":
        prices = [(100 + .2*i - .08, 100 + .2*i + .18, 100 + .2*i - .18, 100 + .2*i)
                  for i in range(65)]
        prices += [(112.8, 113.3, 111.8, 113), (113, 113.1, 111.1, 111.4),
                   (111.4, 114, 111.2, 113.5)]
        line = dict(id=43, line_type="trend", time1="2022-02-24", price1=109.8,
                    time2="2022-02-28", price2=110.6)
    elif name in ("ema_resist_rise", "ema_resist_fail"):
        # 200봉 이상 동일한 종가로 기존 EMA를 예열한다. EMA 값은 fixture에 주입하지 않는다.
        prices = [(142 - .2*i + .1, 142 - .2*i + .25, 142 - .2*i - .25, 142 - .2*i)
                  for i in range(218)]
        for i, high, low in [(210, 100.25, 95.9), (212, 102.5, 99.35), (216, 99.05, 97.5)]:
            prices[i] = (prices[i][0], high, low, prices[i][3])
        prices += [(98.6, 100, 98.5, 99.6), (99.6, 103, 99.5, 102.2),
                   (102.2, 102.3, 99.6, 99.9), (99.9, 101.4, 99.8, 101.1),
                   (101.1, 103.14, 100.9, 102.3)]
        prices += ([(102.3, 104.4, 102.1, 104), (104, 106, 103.7, 105.5)]
                   if name == "ema_resist_rise" else
                   [(102.3, 102.4, 99.1, 99.4), (99.4, 100, 98.9, 99.1),
                    (99.1, 104.3, 99, 103.8)])
        line = None
    elif name == "trendline":
        prices = [(102, 104, 101, 103), (103, 104, 101, 102), (102, 104, 100.5, 103),
                  (103, 104, 99, 100), (100, 106, 99, 105), (105, 108, 104, 107)]
        line = dict(id=41, line_type="trend", time1="2022-01-01", price1=99.0,
                    time2="2022-01-02", price2=100.0)
    else:
        # 같은 존 [100,102]과 첫 이탈일. 3일째부터 재시험 결과만 달라진다.
        prices = [(104, 105, 102.5, 104), (104, 105, 96, 98)]
        paths = {
            "support_fail": [(98, 101, 95, 97), (97, 100.5, 94, 96), (96, 103, 95, 102)],
            "support_recover": [(98, 104, 97, 102), (102, 105, 101, 104)],
            "support_no_retest": [(98, 99, 95, 96), (96, 97, 92, 93)],
        }
        prices += paths[name]
        line = dict(id=42, line_type="zone", time1="2022-01-01", time2="2022-01-31",
                    price1=102.0, price2=100.0)
    frame = pd.DataFrame(prices, columns=["open", "high", "low", "close"])
    frame["open_time"] = pd.date_range("2022-01-01", periods=len(prices), tz="UTC")
    frame["close_time"] = frame["open_time"] + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    frame["volume"] = 100.0
    lines = [dict(line, symbol="BTCUSDT", interval="1d", created_at="2022-01-01T00:00:00Z")] if line else []
    return frame, lines
