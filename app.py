"""
Feature 1 - 통합 신호 대시보드

좌측: 캔들스틱 차트(+거래량) + 수동 지지선/저항선/추세선 그리기
우측: 좌측에서 클릭한 캔들의 날짜에 그날 충족된 신호만 리스트로 표시

신호 판정 로직 자체는 scripts/pipeline.py를 통해 기존 검증 완료된
scripts/*.py 함수를 그대로 재사용한다 (여기서 로직을 다시 구현하지 않음).
매수/매도 추천이나 종합 판단 문구는 표시하지 않고, "이 조건이 그날
충족됐다"는 사실만 보여준다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

import pandas as pd
import streamlit as st

from pipeline import load_dashboard_data
from config import SYMBOL, INTERVAL
import lines_store
from manual_lines import compute_manual_line_signals, compute_manual_line_state_signals, line_label
import doji

sys.path.insert(0, str(Path(__file__).resolve().parent / "components"))
from tv_chart import tv_chart

st.set_page_config(page_title=f"{SYMBOL} {INTERVAL} 신호 대시보드", layout="wide")


@st.cache_data(ttl=3600, show_spinner="데이터 갱신 중 (Binance API)...")
def get_data(refresh_token: int):
    # refresh_token은 캐시 무효화 트리거 용도 (밑줄 없는 이름이라야 캐시 키에 포함됨)
    return load_dashboard_data()


if "refresh_token" not in st.session_state:
    st.session_state["refresh_token"] = 0

df, signals = get_data(st.session_state["refresh_token"])

st.title(f"{SYMBOL} {INTERVAL} 통합 신호 대시보드")
st.caption(
    f"데이터 범위: {df['open_time'].min().date()} ~ {df['open_time'].max().date()}  "
    f"(마지막으로 마감된 캔들까지만 반영, 진행 중인 봉은 제외)"
)

top_l, top_r = st.columns([5, 1])
with top_r:
    if st.button("데이터 새로고침", width="stretch"):
        st.session_state["refresh_token"] += 1
        st.cache_data.clear()
        st.rerun()

WINDOW_OPTIONS = {"최근 3개월": 90, "최근 6개월": 180, "최근 1년": 365, "전체": None}
EMA_STYLE = {
    "MA9": ("EMA9", "#1f77ff", "solid"),
    "MA20": ("EMA20", "#ff8c00", "solid"),
    "MA50": ("EMA50", "#7d3cff", "solid"),
    "MA200": ("EMA200", "#000000", "dash"),
}
DRAW_MODE_OPTIONS = {
    "캔들 선택": "select",
    "수평선 그리기 (클릭 1번)": "horizontal",
    "추세선 그리기 (클릭 2번)": "trend",
}


# 캔들 클릭/표시기간 변경/EMA 토글/선 그리기처럼 차트+신호 패널 안에서 일어나는
# 상호작용은 전부 이 프래그먼트 안에서만 재실행되게 한다(@st.fragment). 이게 없으면
# Streamlit은 위젯 상호작용이 있을 때마다 스크립트 "전체"(제목, 새로고침 버튼 포함)를
# 다시 실행/재렌더링해서 화면 전체가 깜빡이는 것처럼 보인다. 데이터 새로고침 버튼만
# 프래그먼트 밖에 둬서, 그건 의도적으로 전체 페이지를 다시 그리게 유지한다.
@st.fragment
def render_dashboard(df: pd.DataFrame, signals: dict):
    if "selected_idx" not in st.session_state:
        st.session_state["selected_idx"] = len(df) - 1  # 최초 진입 시 가장 최근 캔들 기본 선택
    selected_idx = st.session_state.get("selected_idx")
    last_seq = st.session_state.get("tv_chart_last_seq", 0)

    left, right = st.columns([3, 1])

    with left:
        window_label = st.radio("표시 기간", list(WINDOW_OPTIONS.keys()), index=1, horizontal=True)
        window_days = WINDOW_OPTIONS[window_label]

        if window_days is None:
            plot_df = df
        else:
            cutoff = df["open_time"].max() - pd.Timedelta(days=window_days)
            plot_df = df[df["open_time"] >= cutoff]

        control_cols = st.columns([2, 1, 1, 1, 1])
        with control_cols[0]:
            draw_mode_label = st.radio(
                "차트 클릭 동작", list(DRAW_MODE_OPTIONS.keys()), horizontal=True, key="draw_mode_radio",
            )
        draw_mode = DRAW_MODE_OPTIONS[draw_mode_label]
        if draw_mode != "select":
            st.caption(
                "그리기 모드에서는 캔들 클릭이 신호 패널이 아니라 선 등록으로 쓰입니다. "
                + ("차트를 클릭해서 가격 레벨을 지정하세요." if draw_mode != "trend"
                   else "시작점과 끝점, 두 번 클릭하세요.")
            )

        # EMA9/20/50/200 온오프 - 값 자체는 ma_regime.py(4-3에서 검증된 로직)가 계산한
        # 걸 그대로 가져다 씀(pipeline.py에서 이미 df에 붙여둠). 기본은 꺼짐("깨끗한
        # 캔들만" 기본값 유지, 필요할 때만 켜서 봄).
        ema_ui_cols = st.columns(4)
        show_ema = {}
        for ema_col, ui_col in zip(EMA_STYLE, ema_ui_cols):
            label, _, _ = EMA_STYLE[ema_col]
            with ui_col:
                show_ema[ema_col] = st.checkbox(label, value=False, key=f"ema_toggle_{ema_col}")

        bars = [
            {
                "time": row.open_time.strftime("%Y-%m-%d"),
                "open": row.open, "high": row.high, "low": row.low, "close": row.close,
                "volume": row.volume,
            }
            for row in plot_df.itertuples()
        ]

        selected_date = None
        if selected_idx is not None and selected_idx in df.index:
            candidate = df.loc[selected_idx, "open_time"].strftime("%Y-%m-%d")
            if candidate in {b["time"] for b in bars}:
                selected_date = candidate

        ema_series = {}
        for ema_col, (label, color, dash) in EMA_STYLE.items():
            series_df = plot_df[["open_time", ema_col]].dropna(subset=[ema_col])
            ema_series[ema_col] = {
                "color": color,
                "dashed": dash == "dash",
                "visible": show_ema[ema_col],
                "data": [
                    {"time": r.open_time.strftime("%Y-%m-%d"), "value": getattr(r, ema_col)}
                    for r in series_df.itertuples()
                ],
            }

        # 기획서 "수동 지지선/저항선/추세선" 기능 - 자동 검출 없음, 전부 사용자가 그린 것만.
        # SQLite에 저장되어 세션이 끝나도 유지됨 (lines_store.py).
        saved_lines = lines_store.list_lines(SYMBOL, INTERVAL)
        for line in saved_lines:
            line["label"] = line_label(line)

        # lightweight-charts 기반 커스텀 컴포넌트. Streamlit 커스텀 컴포넌트는 재실행
        # 사이에도 iframe(과 그 안의 차트 인스턴스)이 유지되는 구조라, 줌/이동 상태가
        # Streamlit 재실행과 무관하게 그대로 보존된다(st.plotly_chart로는 안 됐던 부분).
        # 클릭 판정도 lightweight-charts가 시간축 기준으로 알아서 처리해줘서, 꼬리든
        # 몸통이든 캔들의 시간대 안이면 동일하게 인식된다(별도 히트박스 트릭 불필요).
        event = tv_chart(
            bars=bars,
            selected_date=selected_date,
            height=680,
            ema_series=ema_series,
            draw_mode=draw_mode,
            lines=saved_lines,
            key="tv_chart_main",
        )

        # 컴포넌트는 "캔들 선택"과 "선 추가"를 같은 채널로 다중화해서 보내므로,
        # seq(일련번호)로 이미 처리한 이벤트인지 구분한다 - 안 그러면 재실행마다
        # 마지막 클릭이 반복 처리(선이 중복 등록되거나 선택이 되풀이됨)된다.
        if event and event.get("seq", 0) != last_seq:
            st.session_state["tv_chart_last_seq"] = event["seq"]
            kind = event.get("kind")

            if kind == "select":
                match = df.index[df["open_time"].dt.strftime("%Y-%m-%d") == event["date"]]
                if len(match):
                    selected_idx = int(match[0])
                    st.session_state["selected_idx"] = selected_idx
                    st.rerun(scope="fragment")

            elif kind == "add_horizontal":
                lines_store.add_horizontal_line(SYMBOL, INTERVAL, event["price"])
                st.rerun(scope="fragment")

            elif kind == "add_trend":
                lines_store.add_trend_line(
                    SYMBOL, INTERVAL, event["time1"], event["price1"], event["time2"], event["price2"],
                )
                st.rerun(scope="fragment")

        if saved_lines:
            with st.expander(f"그은 선 관리 ({len(saved_lines)}개)"):
                for line in saved_lines:
                    line_cols = st.columns([5, 1])
                    with line_cols[0]:
                        st.write(line["label"])
                    with line_cols[1]:
                        if st.button("삭제", key=f"delete_line_{line['id']}"):
                            lines_store.delete_line(line["id"])
                            st.rerun(scope="fragment")

    # 수동 라인 근접 신호는 사용자가 언제든 선을 추가/삭제하는 동적인 데이터라
    # (9개 신호처럼 st.cache_data로 묶인 pipeline과 분리해서) 매번 새로 계산한다.
    # 캔들 수 x 라인 수 규모라 캐싱 없이도 충분히 빠르다.
    manual_signals = compute_manual_line_signals(df, saved_lines) if saved_lines else {}
    manual_state_signals = compute_manual_line_state_signals(df, saved_lines) if saved_lines else {}
    # 유효 도지(3-1-2)는 위치 조건 중 하나로 manual_signals(수평선 지지 근접)를 그대로
    # 참조하므로, 마찬가지로 pipeline 캐시 밖 - 매번 새로 계산한다.
    valid_doji_signals = doji.compute_valid_doji_long(df, manual_signals)

    with right:
        st.subheader("신호")

        if selected_idx is None:
            st.info("왼쪽 차트에서 캔들을 클릭하면\n그 날짜의 신호가 여기 표시됩니다.")
        else:
            row = df.iloc[selected_idx]
            st.markdown(f"**{row['open_time'].date()}**")
            st.caption(
                f"시가 {row['open']:,.0f}  ·  고가 {row['high']:,.0f}  ·  "
                f"저가 {row['low']:,.0f}  ·  종가 {row['close']:,.0f}"
            )
            st.divider()

            day_all = (
                signals.get(selected_idx, [])
                + manual_signals.get(selected_idx, [])
                + manual_state_signals.get(selected_idx, [])
                + valid_doji_signals.get(selected_idx, [])
            )
            long_signals = [s.text for s in day_all if s.direction == "long"]
            short_signals = [s.text for s in day_all if s.direction == "short"]
            reference_texts = [s.text for s in day_all if s.direction == "reference"]

            tab_all, tab_long, tab_short = st.tabs(["통합", "롱", "숏"])

            with tab_all:
                col_l, col_s = st.columns(2)
                col_l.metric("롱", len(long_signals))
                col_s.metric("숏", len(short_signals))

            with tab_long:
                if long_signals:
                    for s in long_signals:
                        st.markdown(f"- {s}")
                else:
                    st.write("이 날짜에 롱 신호가 없습니다.")

            with tab_short:
                if short_signals:
                    for s in short_signals:
                        st.markdown(f"- {s}")
                else:
                    st.write("이 날짜에 숏 신호가 없습니다.")

            if reference_texts:
                st.divider()
                st.caption("참고 지표 (카운트 제외)")
                for s in reference_texts:
                    st.markdown(f"- {s}")


render_dashboard(df, signals)
