"""
Streamlit 커스텀 컴포넌트 - TradingView의 오픈소스 lightweight-charts로 구현한
캔들스틱 차트.

st.plotly_chart(on_select=...)로는 구조적으로 해결 안 됐던 문제(캔들 클릭마다
컴포넌트가 통째로 다시 그려져서 줌/이동 상태가 유지 안 되고 화면이 깜빡이는 것)를
풀기 위해 도입. Streamlit 커스텀 컴포넌트는 프레임(iframe)이 재실행 사이에도
유지되는 구조라, 그 안의 lightweight-charts 인스턴스도 계속 살아있고 줌/이동
상태를 자체적으로 보존한다.

이 파이썬 파일은 프론트엔드(frontend/index.html)와의 얇은 연결부일 뿐이고,
신호 계산 로직과는 전혀 무관하다 - 순수하게 "차트를 그리고 클릭을 받는" 역할만 함.
"""
import os

import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_component_func = components.declare_component("tv_chart", path=_COMPONENT_DIR)


def tv_chart(bars, selected_date=None, height=680, ema_series=None, draw_mode="select", lines=None, key=None):
    """
    bars: [{"time": "YYYY-MM-DD", "open": float, "high": float, "low": float, "close": float,
             "volume": float}, ...]  (volume은 생략 가능, 없으면 0으로 처리)
          시간순 정렬, 중복 없어야 함 (lightweight-charts 요구사항)
    selected_date: 현재 강조 표시할 캔들의 "YYYY-MM-DD" 문자열, 없으면 None
    height: 차트 높이(px)
    ema_series: {"MA9": {"color": "#1f77ff", "dashed": False, "visible": bool,
                          "data": [{"time": "YYYY-MM-DD", "value": float}, ...]}, ...}
                NaN 구간은 호출 전에 걸러서 넘길 것
    draw_mode: "select"(기본, 캔들 클릭=신호 패널 갱신) | "support" | "resistance"
               (수평선, 클릭 1번) | "trend"(추세선, 클릭 2번)
    lines: [{"id": int, "line_type": "support"|"resistance"|"trend",
             "price1": float, "time1": str|None, "price2": float|None, "time2": str|None,
             "label": str}, ...] - 차트에 그릴 저장된 라인 목록 (lines_store.list_lines 결과에
            manual_lines.line_label로 만든 "label"을 얹어서 넘길 것)

    반환값 (매번 새 이벤트가 있을 때만 dict, 없으면 None):
      {"seq": int, "kind": "select", "date": "YYYY-MM-DD"}
      {"seq": int, "kind": "add_horizontal", "line_type": "support"|"resistance", "price": float}
      {"seq": int, "kind": "add_trend", "time1": str, "price1": float, "time2": str, "price2": float}
    seq는 매 이벤트마다 증가하는 일련번호 - 호출 측에서 마지막으로 처리한 seq와
    비교해서 "이미 처리한 이벤트"를 걸러내는 데 쓸 것 (안 그러면 재실행마다 중복 처리됨).
    """
    return _component_func(
        bars=bars,
        selected_date=selected_date,
        height=height,
        ema_series=ema_series or {},
        draw_mode=draw_mode,
        lines=lines or [],
        key=key,
        default=None,
    )
