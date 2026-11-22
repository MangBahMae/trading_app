"""운영 좌표·원본 사진을 사용하지 않은 수동 도형 합성 사례."""
import pandas as pd


def support_example(name):
    if name == "trendline":
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
    return frame, [dict(line, symbol="BTCUSDT", interval="1d", created_at="2022-01-01T00:00:00Z")]
