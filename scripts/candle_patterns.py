"""
캔들패턴 4종 (도지/망치형/역망치형) - 롱/숏 각각. 신호2(일반도지)/9(고점도지)/
10(고점스피닝탑)을 전부 폐기하고 대체하는 통합 모듈.

모양 판정 (몸통비율<=10% 후보, range 대비):
    몸통비율 = |종가-시가| / (고가-저가)
    위꼬리비율 = 위꼬리 / (고가-저가), 아래꼬리비율 = 아래꼬리 / (고가-저가)
    대칭도 = min(위꼬리비율,아래꼬리비율) / max(위꼬리비율,아래꼬리비율)
    도지: 대칭도 >= 1/3
    망치형: 대칭도 < 1/3 AND 아래꼬리비율 > 위꼬리비율
    역망치형: 대칭도 < 1/3 AND 위꼬리비율 > 아래꼬리비율
(몸통 대비 꼬리 배수 방식은 몸통<=10%와 수학적으로 양립 불가라 폐기됨 -
 두 꼬리 합이 range의 90% 이상인데 "몸통의 2배 미만"은 나올 수 없었음.)

추세판정 (OR, 방향 일치 필수 - 롱은 "직전 하락 완료", 숏은 "직전 상승 완료"):
    1. N봉(1~5, 하나라도 만족하면 인정) 누적등락률 하락<=-8%(롱) 또는 상승>=+8%(숏)
    2. sr_touch.py의 EMA50/EMA200 방향 판정 재사용 - signal="long"/"short"만 인정,
       None(gray_zone)은 불인정 (sr_touch.py 자체 로직은 안 건드림, 그대로 재사용)
    3. 수평선 지지/저항 근접, 방향 있게 (manual_signals의 direction 그대로 재사용)

위치판정에 스윙저점/고점 근접은 쓰지 않는다 (확정 지연으로 인한 미래참조 위험 -
스윙 확정에는 우측 N봉이 더 필요해서, 그 시점엔 아직 몰랐을 정보이기 때문).

시세분출(volatility_expansion.py) 무효화 필터는 숏 3종(도지숏/망치형숏/역망치형숏)
에만 적용한다 - pipeline.py의 _emit_bearish_signal()과 동일한 패턴을 이 파일에
소규모로 복제해서 씀(private 헬퍼를 다른 모듈이 직접 끌어다 쓰는 커플링을 피하기
위함, volatility_expansion.py 자체 로직은 그대로 재사용). 완전히 죽이지 않고
direction="reference"로 강등 + 텍스트에 "시세분출 구간 - 카운트 제외" 표시 -
카운트만 빠지고 화면엔 여전히 보임. 롱 3종은 이번 범위에 해당하는 대칭(하락형)
필터가 아직 없어서 미적용 - 별도 작업으로 남김.

이 모듈의 신호 계산은 app.py의 언캐시드 경로에서 호출된다(pipeline.py의
build_signals_by_date 캐시 흐름 밖) - 수평선 방향 조건이 사용자가 그은 선
(manual_signals)에 의존해서 세션마다 동적으로 바뀌기 때문. 기존 "유효 도지"
(doji.py의 compute_valid_doji_long, 거래량+스윙저점 조건)도 같은 이유로 캐시
밖에 있었고 이번에 완전히 폐기, 되살리지 않는다.

번호(참고용, app.py 표시 순서): 9.도지롱 10.도지숏 11.망치형롱 12.망치형숏
13.역망치형롱 14.역망치형숏
"""
import pandas as pd

import sr_touch
import volatility_expansion
from signal_types import Signal

BODY_MAX_PCT = 0.10
SYMMETRY_MIN = 1 / 3
TREND_PCT = 8.0
TREND_N_RANGE = range(1, 6)

PATTERN_LABEL_KR = {
    "doji": "도지",
    "hammer": "망치형",
    "inverted_hammer": "역망치형",
}


def compute_candle_shape(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()

    body = (df["close"] - df["open"]).abs()
    candle_range = df["high"] - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]

    nonzero_range = candle_range != 0
    body_ratio = pd.Series(0.0, index=df.index)
    upper_wick_ratio = pd.Series(0.0, index=df.index)
    lower_wick_ratio = pd.Series(0.0, index=df.index)
    body_ratio[nonzero_range] = body[nonzero_range] / candle_range[nonzero_range]
    upper_wick_ratio[nonzero_range] = upper_wick[nonzero_range] / candle_range[nonzero_range]
    lower_wick_ratio[nonzero_range] = lower_wick[nonzero_range] / candle_range[nonzero_range]

    shape = pd.Series([None] * len(df), dtype=object)
    for i in df.index:
        if body_ratio.iloc[i] > BODY_MAX_PCT:
            continue
        uw, lw = upper_wick_ratio.iloc[i], lower_wick_ratio.iloc[i]
        bigger, smaller = max(uw, lw), min(uw, lw)
        if bigger == 0:
            continue  # 두 꼬리 다 0(사실상 점) - 대칭도 정의 불가, 판정 제외
        symmetry = smaller / bigger
        if symmetry >= SYMMETRY_MIN:
            shape.iloc[i] = "doji"
        elif lw > uw:
            shape.iloc[i] = "hammer"
        else:
            shape.iloc[i] = "inverted_hammer"

    df["body_ratio"] = body_ratio
    df["upper_wick_ratio"] = upper_wick_ratio
    df["lower_wick_ratio"] = lower_wick_ratio
    df["shape"] = shape
    return df


def _cum_return(close: pd.Series, t: int, N: int):
    if t - 1 - N < 0:
        return None
    c_prev = close.iloc[t - 1]
    c_before = close.iloc[t - 1 - N]
    if c_before == 0:
        return None
    return (c_prev - c_before) / c_before * 100


def _compute_nbar_trend(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """N=1~5 중 하나라도 -8%/+8%를 만족하면 True (down/up 각각)."""
    n = len(df)
    close = df["close"]
    down_nbar = pd.Series(False, index=df.index)
    up_nbar = pd.Series(False, index=df.index)
    for t in range(n):
        for N in TREND_N_RANGE:
            r = _cum_return(close, t, N)
            if r is None:
                continue
            if r <= -TREND_PCT:
                down_nbar.iloc[t] = True
            if r >= TREND_PCT:
                up_nbar.iloc[t] = True
    return down_nbar, up_nbar


def _volatility_expansion_matches(vol_exp_df: pd.DataFrame, i: int) -> list[dict]:
    """i번째 캔들이 걸린 시세 분출 창(N) 목록. pipeline.py의 동명 헬퍼와 동일 로직
    (volatility_expansion.py 자체는 안 건드리고, 그 결과를 소비하는 패턴만 복제)."""
    matches = []
    for window in volatility_expansion.WINDOWS:
        if vol_exp_df[f"expansion_{window}"].iloc[i]:
            matches.append({
                "n": window,
                "cum_pct": vol_exp_df[f"cum_pct_{window}"].iloc[i],
                "cum_pct_per_n": vol_exp_df[f"cum_pct_per_n_{window}"].iloc[i],
            })
    return matches


def compute_candle_pattern_signals(
    df: pd.DataFrame, manual_signals: dict, invalidated_log: list | None = None,
) -> dict:
    """모양(도지/망치형/역망치형) x 방향(롱/숏) 6종 신호.

    df: open_time/open/high/low/close/volume/EMA50/EMA200 컬럼을 가진 캔들 데이터프레임
        (0-based 연속 인덱스. load_dashboard_data()가 이미 EMA50/EMA200을 붙여서 넘김)
    manual_signals: compute_manual_line_signals()의 결과 - direction별로 그대로 재사용
    invalidated_log: 리스트를 넘기면 시세분출로 무효화된 숏 케이스가 거기에 기록된다
        (롱은 이 필터 대상이 아니므로 기록 안 됨).

    반환: {row_index: [Signal("도지 - 롱 후보", "long"), ...]}
    """
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    shape_df = compute_candle_shape(df)
    down_nbar, up_nbar = _compute_nbar_trend(df)
    touch_df = sr_touch.compute_sr_touch(df)
    vol_exp_df = volatility_expansion.compute_volatility_expansion(df)

    line_long = pd.Series(False, index=df.index)
    line_short = pd.Series(False, index=df.index)
    for i in range(n):
        for s in manual_signals.get(i, []):
            if s.direction == "long":
                line_long.iloc[i] = True
            elif s.direction == "short":
                line_short.iloc[i] = True

    ema_long = (touch_df["EMA50_signal"] == "long") | (touch_df["EMA200_signal"] == "long")
    ema_short = (touch_df["EMA50_signal"] == "short") | (touch_df["EMA200_signal"] == "short")

    long_trend_ok = down_nbar | ema_long | line_long
    short_trend_ok = up_nbar | ema_short | line_short

    for i in range(n):
        shape = shape_df["shape"].iloc[i]
        if shape is None:
            continue
        label = PATTERN_LABEL_KR[shape]

        if long_trend_ok.iloc[i]:
            signals[i].append(Signal(f"{label} - 롱 후보", "long"))

        if short_trend_ok.iloc[i]:
            matches = _volatility_expansion_matches(vol_exp_df, i)
            if matches:
                if invalidated_log is not None:
                    for m in matches:
                        invalidated_log.append({
                            "index": i,
                            "date": df["open_time"].iloc[i],
                            "signal_text": f"{label} - 숏 후보",
                            "n": m["n"],
                            "cum_pct": m["cum_pct"],
                            "cum_pct_per_n": m["cum_pct_per_n"],
                        })
                # 완전히 죽이지 않고 카운트에서만 제외(reference), 텍스트로 표시
                signals[i].append(Signal(f"{label} - 숏 후보 (시세분출 구간 - 카운트 제외)", "reference"))
                continue
            signals[i].append(Signal(f"{label} - 숏 후보", "short"))

    return signals
