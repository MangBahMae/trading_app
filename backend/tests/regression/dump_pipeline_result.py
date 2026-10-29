"""
독립 서브프로세스로 실행되어, 주어진 소스 디렉토리(scripts/ 원본 또는
backend/app/services/ 이식본)의 pipeline.py를 import해서
load_dashboard_data() + get_divergence_markers()를 실행하고 결과를 JSON으로
저장한다.

같은 프로세스에서 두 디렉토리를 동시에 import하면 안 되는 이유: 둘 다
swing_points.py, dow_theory.py 같은 동일한 bare 모듈명을 쓰는데, Python은
sys.modules 캐시상 "먼저 import된 쪽"만 계속 재사용하므로 두 번째로 import를
시도하는 쪽도 사실은 첫 번째 것과 같은 코드를 실행하게 돼서 비교가 무의미해진다.
그래서 완전히 격리된 서브프로세스 2개(원본용/이식본용)로 나눠 실행한다
(backend/tests/test_regression_pipeline.py에서 호출).

사용법: python dump_pipeline_result.py <source_dir> <output_json_path> [--flags-on] [--daily-fixture <csv>]
  --daily-fixture: 일봉 데이터를 Binance/캐시 대신 이 CSV(tests/fixtures)로 고정한다 - 원본/이식본이 완전히 같은 입력을
  네트워크 없이 보게 된다(주지 않으면 예전처럼 data_fetcher가 캐시/Binance를 쓴다).
  --flags-on: 이식본(backend/app/services)의 feature_flags를 전부 True로 켠 채로 실행한다
  (플래그를 켜면 꺼두기 전 결과가 그대로 되살아나는지 확인하는 용도. 원본(scripts/)엔 해당 없음).
"""
import json
import sys

source_dir = sys.argv[1]
output_path = sys.argv[2]

sys.path.insert(0, source_dir)

if "--daily-fixture" in sys.argv:
    # pipeline.py가 `from data_fetcher import ensure_fresh_data`로 이름을 가져가므로 pipeline을 import하기 전에 바꾼다.
    import pandas as pd  # noqa: E402
    import data_fetcher  # noqa: E402

    _fixture = pd.read_csv(sys.argv[sys.argv.index("--daily-fixture") + 1], parse_dates=["open_time", "close_time"])
    for _col in ("open_time", "close_time"):
        _fixture[_col] = _fixture[_col].astype("datetime64[ns, UTC]")
    data_fetcher.ensure_fresh_data = lambda *_a, **_k: _fixture.copy()

import pipeline  # noqa: E402

if "--flags-on" in sys.argv:
    import feature_flags  # noqa: E402
    for _name in dir(feature_flags):
        if _name.startswith("ENABLE_"):
            setattr(feature_flags, _name, True)


def _signal_to_dict(sig):
    return {"text": sig.text, "direction": sig.direction}


def _nan_to_none(value):
    if isinstance(value, float) and value != value:  # NaN != NaN
        return None
    return value


def main():
    df, signals, divergence_markers = pipeline.load_dashboard_data()

    candle_cols = ["open", "high", "low", "close", "volume", "EMA9", "EMA20", "EMA50", "EMA200", "rsi"]
    candles = []
    for row in df.itertuples():
        entry = {"date": row.open_time.strftime("%Y-%m-%d")}
        for col in candle_cols:
            entry[col] = _nan_to_none(getattr(row, col))
        candles.append(entry)

    signals_by_date = {}
    for i, sigs in signals.items():
        if not sigs:
            continue
        date = df["open_time"].iloc[i].strftime("%Y-%m-%d")
        signals_by_date[date] = [_signal_to_dict(s) for s in sigs]

    result = {
        "candle_count": len(df),
        "first_date": df["open_time"].iloc[0].strftime("%Y-%m-%d"),
        "last_date": df["open_time"].iloc[-1].strftime("%Y-%m-%d"),
        "candles": candles,
        "signals_by_date": signals_by_date,
        "divergence_markers": divergence_markers,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
