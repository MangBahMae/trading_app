"""
9개 신호 로직을 하나로 묶어 실행하고, 날짜별로 그날 충족된 신호 목록을 만든다.

각 신호의 판정 로직 자체는 이미 검증 완료된 scripts/*.py의 함수를 그대로
가져다 쓴다 (로직 재구현/변경 없음). 이 파일은 그것들을 순서대로 실행해서
결과를 하나의 "날짜 -> 신호 목록" 구조로 모아주는 역할만 한다.

9개 신호:
1. 매물소진 매수/매도 (exhaustion.py)
2. 도지캔들 (doji.py)
3. 정배열 전환 (ma_regime.py - 전날과 다른 상태로 "바뀐 날"만, 지속 상태 아님)
4. 역배열 전환 (ma_regime.py - 위와 동일)
5. 이동평균(MA50/MA200) 터치 롱/숏 (sr_touch.py)
6. RSI 다이버전스 4종 (rsi_swings.py + divergence.py)
7. 다우이론 HH/LH/HL/LL (dow_theory.py)
8. RSI 과매도 (rsi_overbought_oversold.py)
9. RSI 과매수 (rsi_overbought_oversold.py)
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
import exhaustion
import rsi
import rsi_swings
import divergence
import rsi_overbought_oversold
from data_fetcher import ensure_fresh_data

DOW_LABEL_KR = {
    "HH": "다우이론 HH (신고점 갱신)",
    "LH": "다우이론 LH (저항 갱신)",
    "HL": "다우이론 HL (지지 갱신)",
    "LL": "다우이론 LL (신저점 갱신)",
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
    exhaustion_df = exhaustion.compute_exhaustion(base_df)

    rsi_df = rsi.compute_rsi_signals(base_df)
    rsi_swings_df = rsi_swings.find_rsi_swings(rsi_df, n=5)
    divergence_events, _excluded = divergence.compute_divergences(rsi_swings_df)
    ob_os_df = rsi_overbought_oversold.compute_ob_os_signals(rsi_df)

    signals = {i: [] for i in range(n)}

    for i in range(n):
        sig = exhaustion_df["exhaustion_signal"].iloc[i]
        if sig == "buy":
            signals[i].append("매물소진 - 매수 신호")
        elif sig == "sell":
            signals[i].append("매물소진 - 매도 신호")

    for i in range(n):
        if doji_df["is_doji"].iloc[i]:
            signals[i].append("도지캔들")

    regimes = regime_df["ma_regime"].tolist()
    for i in range(1, n):
        prev_regime, curr_regime = regimes[i - 1], regimes[i]
        if curr_regime == "bullish" and prev_regime != "bullish":
            signals[i].append("정배열 전환")
        if curr_regime == "bearish" and prev_regime != "bearish":
            signals[i].append("역배열 전환")

    for ma_col in ["MA50", "MA200"]:
        signal_col = f"{ma_col}_signal"
        for i in range(n):
            sig = touch_df[signal_col].iloc[i]
            if sig == "long":
                signals[i].append(f"{ma_col} 터치 - 롱 신호")
            elif sig == "short":
                signals[i].append(f"{ma_col} 터치 - 숏 신호")

    for _, ev in divergence_events.iterrows():
        idx = int(ev["index"])
        if idx in signals:
            signals[idx].append(DIV_LABEL_KR[ev["type"]])

    for _, ev in dow_events.iterrows():
        label = ev["label"]
        if label in DOW_LABEL_KR:
            idx = int(ev["index"])
            if idx in signals:
                signals[idx].append(DOW_LABEL_KR[label])

    for i in range(n):
        if ob_os_df["rsi_buy"].iloc[i]:
            signals[i].append("RSI 과매도 (RSI<=25)")
        if ob_os_df["rsi_sell"].iloc[i]:
            signals[i].append("RSI 과매수 (RSI>=80)")

    return signals


EMA_COLS = ["MA9", "MA20", "MA50", "MA200"]


def load_dashboard_data():
    """대시보드에서 쓸 (OHLCV+EMA 데이터프레임, 날짜별 신호 dict)를 반환.

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
    total = sum(len(v) for v in signals.values())
    print(f"캔들 {len(df)}개, 신호 총 {total}건")
    for i, sigs in signals.items():
        if sigs:
            print(df["open_time"].iloc[i].date(), sigs)
