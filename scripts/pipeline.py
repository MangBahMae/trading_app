"""
12개 신호 로직을 하나로 묶어 실행하고, 날짜별로 그날 충족된 신호 목록을 만든다.

각 신호의 판정 로직 자체는 이미 검증 완료된 scripts/*.py의 함수를 그대로
가져다 쓴다 (로직 재구현/변경 없음). 이 파일은 그것들을 순서대로 실행해서
결과를 하나의 "날짜 -> Signal 목록" 구조로 모아주는 역할만 한다.

Signal(text, direction)의 direction("long"/"short"/"reference")이 롱/숏 카운트
포함 여부를 결정하는 유일한 기준 - 표시 문구가 바뀌어도 카운트 로직은 안 바뀐다.

12개 신호:
1. 매물소진 매수/매도 (exhaustion.py)
2. 도지캔들 (doji.py - 필터링 미완이라 reference로 취급, 미결 사항 참고)
3. 정배열 진입/유지 (ma_regime.py - bullish_trigger/bullish_state, 유지되는 동안 매일 표시)
4. 역배열 진입/유지 (ma_regime.py - bearish_trigger/bearish_state, 유지되는 동안 매일 표시)
5. 이동평균(MA50/MA200) 터치 롱/숏 (sr_touch.py)
6. RSI 다이버전스 4종 (rsi_swings.py + divergence.py - 무효화 전까지 매일 표시)
7. 다우이론 HH/LH/HL/LL (dow_theory.py - 표시 전용, direction="reference")
8. RSI 과매도 (rsi_overbought_oversold.py)
9. RSI 과매수 (rsi_overbought_oversold.py - 표시 전용, direction="reference")
10. 고점 도지 (거부 캔들) - 숏 (doji_spinning_top_at_high.py)
11. 고점 스피닝탑 (거부 캔들) - 숏 (doji_spinning_top_at_high.py)
12. 장악형 하락 - 숏 (bearish_engulfing.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

import swing_points
import dow_theory
import ma_regime
import sr_touch
import doji
import doji_spinning_top_at_high
import bearish_engulfing
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


def build_signals_by_date(base_df: pd.DataFrame, regime_df: pd.DataFrame | None = None) -> dict:
    base_df = base_df.reset_index(drop=True)
    n = len(base_df)

    swings_df = swing_points.find_swing_points(base_df, n=2)
    dow_events = dow_theory.compute_dow_events(swings_df)

    if regime_df is None:
        regime_df = ma_regime.compute_ma_regime(base_df)
    touch_df = sr_touch.compute_sr_touch(regime_df)

    doji_df = doji.compute_doji(base_df)
    rejection_at_high_df = doji_spinning_top_at_high.compute_doji_spinning_top_at_high(base_df)
    bearish_engulfing_df = bearish_engulfing.compute_bearish_engulfing(base_df)
    exhaustion_df = exhaustion.compute_exhaustion(base_df)

    rsi_df = rsi.compute_rsi_signals(base_df)
    rsi_swings_df = rsi_swings.find_rsi_swings(rsi_df, n=5)
    divergence_events, _excluded = divergence.compute_divergences(rsi_swings_df)
    ob_os_df = rsi_overbought_oversold.compute_ob_os_signals(rsi_df)

    signals = {i: [] for i in range(n)}

    for i in range(n):
        sig = exhaustion_df["exhaustion_signal"].iloc[i]
        if sig == "buy":
            signals[i].append(Signal("매물소진 - 매수 신호", "long"))
        elif sig == "sell":
            signals[i].append(Signal("매물소진 - 매도 신호", "short"))

    for i in range(n):
        if doji_df["is_doji"].iloc[i]:
            signals[i].append(Signal("도지캔들", "reference"))

    for i in range(n):
        if rejection_at_high_df["is_doji_at_high"].iloc[i]:
            signals[i].append(Signal("고점 도지 (거부 캔들) - 숏 신호", "short"))
        if rejection_at_high_df["is_spinning_top_at_high"].iloc[i]:
            signals[i].append(Signal("고점 스피닝탑 (거부 캔들) - 숏 신호", "short"))

    for i in range(n):
        if bearish_engulfing_df["is_bearish_engulfing"].iloc[i]:
            signals[i].append(Signal("장악형 하락 - 숏 신호", "short"))

    for i in range(n):
        if regime_df["bullish_state"].iloc[i]:
            text = "정배열 진입" if regime_df["bullish_trigger"].iloc[i] else "정배열 유지 중"
            signals[i].append(Signal(text, "long"))

    for i in range(n):
        if regime_df["bearish_state"].iloc[i]:
            text = "역배열 진입" if regime_df["bearish_trigger"].iloc[i] else "역배열 유지 중"
            signals[i].append(Signal(text, "short"))

    for ma_col in ["MA50", "MA200"]:
        signal_col = f"{ma_col}_signal"
        case_col = f"{ma_col}_case"
        for i in range(n):
            sig = touch_df[signal_col].iloc[i]
            if sig == "long":
                signals[i].append(Signal(f"{ma_col} 터치 - 롱 신호", "long"))
            elif sig == "short":
                signals[i].append(Signal(f"{ma_col} 터치 - 숏 신호", "short"))
            elif touch_df[case_col].iloc[i] == "gray_zone":
                signals[i].append(Signal(f"{ma_col} 근접했으나 회색지대라 신호 제외", "reference"))

    divergence_state_events = divergence.compute_divergence_state(rsi_swings_df, divergence_events)
    for _, ev in divergence_state_events.iterrows():
        label = DIV_LABEL_KR[ev["type"]]
        direction = "long" if ev["type"] in divergence.BULLISH_TYPES else "short"
        trigger_idx = int(ev["index"])
        end_idx = int(ev["state_end_index"])
        for day_idx in range(trigger_idx, end_idx + 1):
            if day_idx in signals:
                suffix = "진입" if day_idx == trigger_idx else "유지 중"
                signals[day_idx].append(Signal(f"{label} {suffix}", direction))

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


EMA_COLS = ["MA9", "MA20", "MA50", "MA200"]


def load_dashboard_data():
    """대시보드에서 쓸 (OHLCV+EMA 데이터프레임, 날짜별 Signal 목록 dict)를 반환.

    EMA9/20/50/200은 ma_regime.py가 이미 계산하는 값을 그대로 가져다 붙인다
    (차트 표시용으로 별도 재계산하지 않음 - 4-3에서 검증된 것과 동일한 값).
    """
    base_df = ensure_fresh_data().reset_index(drop=True)
    regime_df = ma_regime.compute_ma_regime(base_df)
    signals = build_signals_by_date(base_df, regime_df=regime_df)

    base_df = base_df.copy()
    for col in EMA_COLS:
        base_df[col] = regime_df[col]

    return base_df, signals


if __name__ == "__main__":
    df, signals = load_dashboard_data()
    total = sum(1 for lst in signals.values() for s in lst if s.direction != "reference")
    ref_total = sum(1 for lst in signals.values() for s in lst if s.direction == "reference")
    print(f"캔들 {len(df)}개, 신호 총 {total}건 (참고 지표 {ref_total}건 별도)")
    for i, sigs in signals.items():
        if sigs:
            print(df["open_time"].iloc[i].date(), [f"{s.text} [{s.direction}]" for s in sigs])
