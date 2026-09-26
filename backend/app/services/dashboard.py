"""
GET /api/dashboard 응답 + 수동 선 CRUD를 만드는 오케스트레이션 계층.

scripts/*.py를 그대로 이식한(이 디렉토리의) pipeline.py, lines_store.py,
manual_lines.py, candle_patterns.py를 app.py(Streamlit 신호 스캐너 화면)와
정확히 같은 순서/방식으로 조합한다. 계산 로직 자체는 그 모듈들 안에 있고,
여기서는 합치는 역할만 한다.

이 파일 하나가 sys.path 삽입 + bare import(scripts/ 방식과 동일한 flat
네임스페이스)를 전담한다 - 다른 router가 lines_store 등을 각자
"app.services.lines_store"로 패키지 import하면, 여기서 bare import한
"lines_store"와 sys.modules상 서로 다른 모듈 객체로 이중 로드된다(파일은
같아도 식별자가 갈림). lines_store.py 자체는 상태가 없는 순수 SQLite
CRUD라 이중 로드돼도 기능상 문제는 없지만, 굳이 그럴 이유가 없어서 이
파일이 유일한 창구가 되도록 한다 - routers/*.py는 전부 이 모듈의 함수만
호출한다.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline  # noqa: E402
import lines_store  # noqa: E402
import manual_lines  # noqa: E402
import candle_patterns  # noqa: E402
from config import SYMBOL, INTERVAL  # noqa: E402

EMA_COLS = ["EMA9", "EMA20", "EMA50", "EMA200"]

# app.py의 @st.cache_data(ttl=3600)과 동일한 TTL - 캔들+9개+ 자동신호만 캐싱하고,
# 수동 선 관련(라인 근접/돌파, 캔들패턴)은 매 요청 재계산(원본과 동일한 신선도).
_CACHE_TTL_SECONDS = 3600
_cache: dict = {"data": None, "computed_at": 0.0}


def _nan_to_none(value):
    """FastAPI 기본 JSON 인코더는 NaN을 그대로 흘려보내 브라우저 JSON.parse가
    깨진다 - EMA200(첫 199일)/RSI(첫 13일)는 계산상 NaN이 나오므로 null로 바꾼다.
    (계산 로직과 무관한 직렬화 이슈)"""
    if isinstance(value, float) and value != value:  # NaN != NaN
        return None
    return value


def _get_base_data(force_refresh: bool = False):
    now = time.time()
    if not force_refresh and _cache["data"] is not None and now - _cache["computed_at"] < _CACHE_TTL_SECONDS:
        return _cache["data"]

    df, signals, divergence_markers = pipeline.load_dashboard_data()
    _cache["data"] = (df, signals, divergence_markers)
    _cache["computed_at"] = now
    return _cache["data"]


def get_dashboard_data(force_refresh: bool = False) -> dict:
    df, signals, divergence_markers = _get_base_data(force_refresh)

    lines = lines_store.list_lines(SYMBOL, INTERVAL)
    for line in lines:
        line["label"] = manual_lines.line_label(line)

    manual_signals = manual_lines.compute_manual_line_signals(df, lines) if lines else {}
    manual_state_signals = manual_lines.compute_manual_line_state_signals(df, lines) if lines else {}
    candle_pattern_signals = candle_patterns.compute_candle_pattern_signals(df, manual_signals)

    n = len(df)
    signals_by_date = {}
    for i in range(n):
        day_all = (
            signals.get(i, [])
            + manual_signals.get(i, [])
            + manual_state_signals.get(i, [])
            + candle_pattern_signals.get(i, [])
        )
        if day_all:
            date = df["open_time"].iloc[i].strftime("%Y-%m-%d")
            signals_by_date[date] = [{"text": s.text, "direction": s.direction} for s in day_all]

    candle_cols = ["open", "high", "low", "close", "volume"] + EMA_COLS + ["rsi"]
    candles = []
    for row in df.itertuples():
        entry = {"date": row.open_time.strftime("%Y-%m-%d")}
        for col in candle_cols:
            entry[col.lower()] = _nan_to_none(getattr(row, col))
        candles.append(entry)

    return {
        "candles": candles,
        "date_range": {
            "min": df["open_time"].iloc[0].strftime("%Y-%m-%d"),
            "max": df["open_time"].iloc[-1].strftime("%Y-%m-%d"),
        },
        "signals": signals_by_date,
        "divergence_markers": divergence_markers,
        "manual_lines": lines,
    }


def add_horizontal_line(price: float) -> int:
    return lines_store.add_horizontal_line(SYMBOL, INTERVAL, price)


def add_trend_line(time1: str, price1: float, time2: str, price2: float) -> int:
    return lines_store.add_trend_line(SYMBOL, INTERVAL, time1, price1, time2, price2)


def delete_line(line_id: int) -> None:
    lines_store.delete_line(line_id)
