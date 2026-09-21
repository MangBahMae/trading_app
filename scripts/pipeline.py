"""
12개 신호 로직을 하나로 묶어 실행하고, 날짜별로 그날 충족된 신호 목록을 만든다.

각 신호의 판정 로직 자체는 이미 검증 완료된 scripts/*.py의 함수를 그대로
가져다 쓴다 (로직 재구현/변경 없음). 이 파일은 그것들을 순서대로 실행해서
결과를 하나의 "날짜 -> Signal 목록" 구조로 모아주는 역할만 한다.

Signal(text, direction)의 direction("long"/"short"/"reference")이 롱/숏 카운트
포함 여부를 결정하는 유일한 기준 - 표시 문구가 바뀌어도 카운트 로직은 안 바뀐다.

8개 카운트 신호 (RSI 다이버전스는 유효성 검증 결과 MAE가 목표폭보다 커서
카운트 신호에서 제외 - 차트 참고 표시(get_divergence_markers)로만 남음):
1. 매물소진 매수/매도 (exhaustion.py)
2. 정배열 진입/유지 (ma_regime.py - bullish_trigger/bullish_state, 유지되는 동안 매일 표시)
3. 역배열 진입/유지 (ma_regime.py - bearish_trigger/bearish_state, 유지되는 동안 매일 표시)
4. 이동평균(EMA50/EMA200) 터치 롱/숏 (sr_touch.py)
5. 다우이론 HH/LH/HL/LL (dow_theory.py - 표시 전용, direction="reference")
6. RSI 과매도 (rsi_overbought_oversold.py)
7. RSI 과매수 (rsi_overbought_oversold.py - 표시 전용, direction="reference")
8. 장악형 하락 - 숏 (bearish_engulfing.py)

옛 신호2(도지캔들)/9(고점 도지)/10(고점 스피닝탑)은 완전 폐기됨 - 캔들패턴
4종(도지/망치형/역망치형 x 롱/숏, 9~14번)으로 재설계돼서 candle_patterns.py로
이전. 이 신호들은 수평선 방향 조건(사용자가 그은 선)에 의존해서 여기(캐시된
흐름) 말고 app.py의 언캐시드 경로에서 계산된다 - candle_patterns.py 참고.

무효화 필터:
- 시세 분출(volatility_expansion.py) 구간에서는 bearish_engulfing을 발생시키지
  않는다. 무효화된 케이스는 invalidated_log 인자를 넘기면 그 리스트에 기록된다
  (검토용, 기본 동작에는 영향 없음). 캔들패턴 6종 중 숏 3종에도 동일 필터가
  candle_patterns.py 안에서 별도로 적용된다(롱 3종은 대칭 필터 없어서 미적용).

RSI 다이버전스(divergence.py)는 로직 자체는 정확하지만(구조발생일/확정일 분리,
born-invalid 필터, 은닉 비활성화까지 검증 완료), MAE(반대 방향 최대 역행폭)가
중앙값 6.32%로 목표 움직임 폭(2~3%)보다 훨씬 커서 단독 카운트 신호로는 부적합
판단 - get_divergence_markers()가 차트 표시용 데이터만 별도로 만든다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import swing_points
import dow_theory
import ma_regime
import sr_touch
import bearish_engulfing
import volatility_expansion
import exhaustion
import rsi
import rsi_swings
import divergence
import rsi_overbought_oversold
from data_fetcher import ensure_fresh_data
from signal_types import Signal

DOW_LABEL_KR = {
    "HH": "신고점 갱신",
    "LH": "고점갱신 실패",
    "HL": "저점 상승",
    "LL": "저점 하락",
}
DIV_LABEL_KR = {
    "regular_bullish": "RSI 다이버전스 - 정상 강세",
    "regular_bearish": "RSI 다이버전스 - 정상 약세",
    "hidden_bullish": "RSI 다이버전스 - 은닉 강세",
    "hidden_bearish": "RSI 다이버전스 - 은닉 약세",
}


def _volatility_expansion_matches(vol_exp_df: pd.DataFrame, i: int) -> list[dict]:
    """i번째 캔들이 걸린 시세 분출 창(N) 목록. 없으면 빈 리스트."""
    matches = []
    for window in volatility_expansion.WINDOWS:
        if vol_exp_df[f"expansion_{window}"].iloc[i]:
            matches.append(
                {
                    "n": window,
                    "cum_pct": vol_exp_df[f"cum_pct_{window}"].iloc[i],
                    "cum_pct_per_n": vol_exp_df[f"cum_pct_per_n_{window}"].iloc[i],
                }
            )
    return matches


def _emit_bearish_signal(
    i: int,
    text: str,
    base_df: pd.DataFrame,
    vol_exp_df: pd.DataFrame,
    signals: dict,
    invalidated_log: list | None,
) -> None:
    """시세 분출 구간이면 신호를 발생시키지 않고 invalidated_log에만 기록."""
    matches = _volatility_expansion_matches(vol_exp_df, i)
    if matches:
        if invalidated_log is not None:
            for m in matches:
                invalidated_log.append(
                    {
                        "index": i,
                        "date": base_df["open_time"].iloc[i],
                        "signal_text": text,
                        "n": m["n"],
                        "cum_pct": m["cum_pct"],
                        "cum_pct_per_n": m["cum_pct_per_n"],
                    }
                )
        return
    signals[i].append(Signal(text, "short"))


def build_signals_by_date(
    base_df: pd.DataFrame,
    regime_df: pd.DataFrame | None = None,
    invalidated_log: list | None = None,
) -> dict:
    base_df = base_df.reset_index(drop=True)
    n = len(base_df)

    swings_df = swing_points.find_swing_points(base_df, n=2)
    dow_events = dow_theory.compute_dow_events(swings_df)

    if regime_df is None:
        regime_df = ma_regime.compute_ma_regime(base_df)
    touch_df = sr_touch.compute_sr_touch(regime_df)

    bearish_engulfing_df = bearish_engulfing.compute_bearish_engulfing(base_df)
    vol_exp_df = volatility_expansion.compute_volatility_expansion(base_df)
    exhaustion_df = exhaustion.compute_exhaustion(base_df)

    rsi_df = rsi.compute_rsi_signals(base_df)
    ob_os_df = rsi_overbought_oversold.compute_ob_os_signals(rsi_df)

    signals = {i: [] for i in range(n)}

    for i in range(n):
        sig = exhaustion_df["exhaustion_signal"].iloc[i]
        if sig == "buy":
            signals[i].append(Signal("매물소진 - 매수 신호", "long"))
        elif sig == "sell":
            signals[i].append(Signal("매물소진 - 매도 신호", "short"))

    for i in range(n):
        if bearish_engulfing_df["is_bearish_engulfing"].iloc[i]:
            _emit_bearish_signal(i, "장악형 하락 - 숏 신호", base_df, vol_exp_df, signals, invalidated_log)

    for i in range(n):
        if regime_df["bullish_state"].iloc[i]:
            ratchet = int(regime_df["bullish_suspicion_ratchet"].iloc[i])
            label = "정배열 진입" if regime_df["bullish_trigger"].iloc[i] else "정배열 유지 중"
            signals[i].append(Signal(f"{label} · 이력 {ratchet}단계", "long"))
            if regime_df["bullish_suspicion"].iloc[i] == 2:
                signals[i].append(Signal("⚠ 오늘 EMA 이탈 (위험)", "reference"))
        if regime_df["bullish_exit_trigger"].iloc[i]:
            signals[i].append(Signal("정배열 종료", "reference"))

    for i in range(n):
        if regime_df["bearish_state"].iloc[i]:
            text = "역배열 진입" if regime_df["bearish_trigger"].iloc[i] else "역배열 유지 중"
            signals[i].append(Signal(text, "short"))

    for ma_col in ["EMA50", "EMA200"]:
        signal_col = f"{ma_col}_signal"
        case_col = f"{ma_col}_case"
        for i in range(n):
            sig = touch_df[signal_col].iloc[i]
            case = touch_df[case_col].iloc[i]
            if case == "touch_reject" and sig == "long":
                signals[i].append(Signal(f"{ma_col} 지지", "long"))
            elif case == "touch_reject" and sig == "short":
                signals[i].append(Signal(f"{ma_col} 저항 (거부)", "short"))
            elif case == "breakout" and sig == "long":
                signals[i].append(Signal(f"{ma_col} 상향 돌파", "long"))
            elif case == "breakout" and sig == "short":
                signals[i].append(Signal(f"{ma_col} 하향 이탈", "short"))
            elif case == "gray_zone":
                signals[i].append(Signal(f"{ma_col} 근접했으나 회색지대라 신호 제외", "reference"))

    for i in range(n):
        if ob_os_df["oversold_state"].iloc[i]:
            text = "RSI 과매도 진입" if ob_os_df["oversold_trigger"].iloc[i] else "RSI 과매도 유지 중"
            signals[i].append(Signal(text, "long"))
        if ob_os_df["rsi_sell"].iloc[i]:
            signals[i].append(Signal("RSI 과매수 (RSI>=80)", "reference"))

    # 다우이론: 표시 전용/카운트 제외 확정 (기획서 3-4). 스윙 확정 시점 1회만이 아니라,
    # 그 라벨이 다음 라벨로 바뀌기 전까지 매일 표시.
    dow_state_df = dow_theory.compute_dow_state(base_df, dow_events)
    for i in range(n):
        label = dow_state_df["dow_label"].iloc[i]
        if label is not None:
            signals[i].append(Signal(f"다우이론 {DOW_LABEL_KR[label]} (참고)", "reference"))

    return signals


def get_divergence_markers(base_df: pd.DataFrame, rsi_df: pd.DataFrame | None = None) -> list[dict]:
    """정상 RSI 다이버전스(현재 lbL=lbR=3 기준 36건)를 차트 마커용 데이터로 변환.

    신호 카운트(build_signals_by_date)에는 안 들어간다 - MAE가 목표 움직임 폭보다
    커서 유효성 검증 결과 단독 카운트 신호로 부적합 판단, 차트 참고 표시로만 남김.
    계산 로직(divergence.compute_divergences/compute_divergence_state)은 그대로
    재사용 - 여기서는 결과를 표시용 dict로 변환만 한다.

    lbR(우측 확인 봉수)=3 - rsi_swings.py 기본값(N=5, 다른 용도의 표준 대조에 계속
    쓰임)은 그대로 두고, 여기 표시 전용 호출에서만 n=3으로 국소 적용한다(사용자
    확인 실험 결과: 5봉 대비 이벤트 27->36건 증가, 확정 2일 단축, 다만 3봉 피벗의
    35.7%가 5봉 기준으론 재역전되는 "가짜 피벗" - 그래도 육안 확인 후 3봉으로 결정).
    """
    base_df = base_df.reset_index(drop=True)
    if rsi_df is None:
        rsi_df = rsi.compute_rsi_signals(base_df)
    rsi_swings_df = rsi_swings.find_rsi_swings(rsi_df, n=3)
    events, _excluded = divergence.compute_divergences(rsi_swings_df)
    state_events = divergence.compute_divergence_state(rsi_swings_df, events)

    markers = []
    for _, ev in state_events.iterrows():
        prev_idx = int(ev["prev_index"])
        structure_idx = int(ev["structure_idx"])
        confirmed_idx = int(ev["confirmed_idx"])
        markers.append({
            "type": ev["type"],
            "label": DIV_LABEL_KR[ev["type"]],
            "prev_date": base_df["open_time"].iloc[prev_idx].strftime("%Y-%m-%d"),
            "prev_price": float(ev["prev_price"]),
            "prev_rsi": float(ev["prev_rsi"]),
            "structure_date": base_df["open_time"].iloc[structure_idx].strftime("%Y-%m-%d"),
            "price": float(ev["price"]),
            "rsi": float(ev["rsi"]),
            "confirmed_date": base_df["open_time"].iloc[confirmed_idx].strftime("%Y-%m-%d"),
        })
    return markers


EMA_COLS = ["EMA9", "EMA20", "EMA50", "EMA200"]


def load_dashboard_data(invalidated_log: list | None = None):
    """대시보드에서 쓸 (OHLCV+EMA+RSI 데이터프레임, 날짜별 Signal 목록 dict,
    다이버전스 차트 마커 목록)를 반환.

    EMA9/20/50/200은 ma_regime.py가 이미 계산하는 값을 그대로 가져다 붙인다
    (차트 표시용으로 별도 재계산하지 않음 - 4-3에서 검증된 것과 동일한 값).

    invalidated_log: 리스트를 넘기면 시세 분출로 무효화된 약세 신호 케이스가
    거기에 기록된다 (검토용, 기본 동작에는 영향 없음).
    """
    base_df = ensure_fresh_data().reset_index(drop=True)
    regime_df = ma_regime.compute_ma_regime(base_df)
    signals = build_signals_by_date(base_df, regime_df=regime_df, invalidated_log=invalidated_log)

    base_df = base_df.copy()
    for col in EMA_COLS:
        base_df[col] = regime_df[col]

    rsi_df = rsi.compute_rsi_signals(base_df)
    base_df["rsi"] = rsi_df["rsi"]
    divergence_markers = get_divergence_markers(base_df, rsi_df=rsi_df)

    return base_df, signals, divergence_markers


if __name__ == "__main__":
    df, signals, divergence_markers = load_dashboard_data()
    total = sum(1 for lst in signals.values() for s in lst if s.direction != "reference")
    ref_total = sum(1 for lst in signals.values() for s in lst if s.direction == "reference")
    print(f"캔들 {len(df)}개, 신호 총 {total}건 (참고 지표 {ref_total}건 별도)")
    print(f"다이버전스 차트 마커 {len(divergence_markers)}건 (카운트 제외, 차트 표시 전용)")
    for i, sigs in signals.items():
        if sigs:
            print(df["open_time"].iloc[i].date(), [f"{s.text} [{s.direction}]" for s in sigs])
