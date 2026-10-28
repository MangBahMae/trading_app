"""
캔들패턴 4종 (도지/망치형/역망치형) - 롱/숏 각각. 신호2(일반도지)/9(고점도지)/
10(고점스피닝탑)을 전부 폐기하고 대체하는 통합 모듈.

모양 판정 (모든 비율은 캔들 범위 = 고가 - 저가 대비, 기준값은 아래 상수):
    몸통비율 = |종가-시가| / 범위, 위꼬리비율 = 위꼬리 / 범위, 아래꼬리비율 = 아래꼬리 / 범위
    망치형:   몸통비율 <= 35%  AND 위꼬리비율 <= 10%  AND 아래꼬리 >= 몸통 x 2
    역망치형: 몸통비율 <= 35%  AND 아래꼬리비율 <= 10%  AND 위꼬리 >= 몸통 x 2
    도지:     위 둘이 아니면서 몸통비율 <= 15%, 또는 15% < 몸통비율 <= 25%인데 당일 거래량 >= 직전 20일 평균거래량
              (당일 제외)의 1.5배. 도지는 대칭도 조건이 없다 - 망치형/역망치형 조건(꼬리 10%/배수)에 못 미치는
              몸통 15% 이하 캔들은 전부 도지가 된다.
    망치형/역망치형에는 도지의 거래량 조건을 적용하지 않는다. 고가 == 저가(범위 0)인 캔들은 모양 없음.
    (2026-10 이전에는 "대칭도 < 1/3이고 한쪽 꼬리가 더 길면 망치형/역망치형, 몸통 15~25%는 거래량 조건"이었다.)

위치 판정 (몸통만 사용, 꼬리는 안 씀) - 2026-10 새 방식으로 교체 (N봉 ±8%/EMA 터치/선 근접은 제거):
    몸통 상단 = max(시가, 종가), 몸통 하단 = min(시가, 종가)
    고점 캔들: 당일 몸통 상단 > 직전 N개 캔들 몸통 상단의 최댓값 (당일 제외, 엄격 초과)
    저점 캔들: 당일 몸통 하단 < 직전 N개 캔들 몸통 하단의 최솟값
    N = POSITION_LOOKBACK_N (한 곳에서 바꾼다). 처음 N개 캔들은 직전 N개가 없어 고점/저점 캔들이 될 수 없다.

신호 (모양이 도지/망치형/역망치형이면 - 모양 자체는 방향이 없다):
    숏: 고점 캔들 t가 모양이면 t에 신호. 아니면 t+1이 모양일 때 t+1에 신호("(다음 봉)" 표시, next_bar=True).
        둘 다 모양이면 t에서만(1번). t+1이 또 고점 캔들이면 t+1을 새 고점 캔들로 다시 판정(그 신호는 당일 신호).
    롱: 저점 캔들 기준으로 대칭.
    같은 캔들에서 롱과 숏이 따로 나는 경우(아웃사이드 바 등)는 둘 다 낸다.
    미래 참조 없음: t+1 신호는 t+1 마감 시점까지의 정보(t+1의 모양, 직전 N개 몸통)만 쓴다.
    위치판정에 스윙저점/고점은 쓰지 않는다 (확정 지연으로 인한 미래참조 위험).

시세분출 무효: 숏 신호가 나는 캔들(당일 신호면 t, 다음 봉 신호면 t+1)이 시세분출(volatility_expansion.py)
    구간이면 "{모양} - 숏 후보" 대신 "{모양} - 시세분출 무효"(reference, 카운트 제외)를 낸다. 롱에는 적용하지 않는다.

표시: "{모양} - 롱 후보"/"{모양} - 숏 후보"(카운트됨), 다음 봉 신호는 뒤에 " (다음 봉)".
    위치 조건(고점/저점 캔들)을 못 채워 신호가 하나도 안 난 모양 캔들에는 "{모양} - 참고 (고점/저점 아님)"
    (reference, 카운트 제외, near_zone 부착)을 낸다. 같은 캔들에 신호가 났으면 참고는 안 낸다.
    feature_flags.ENABLE_CANDLE_REFERENCE=False로 끌 수 있다(끄면 아무것도 안 낸다).

제거된 예전 조건(함수/상수는 코드에 남겨 두되 판정에는 안 씀 - 필요하면 되살릴 수 있다): N봉(1~5) 누적등락률 ±8%,
    EMA50/EMA200 터치 방향(sr_touch.py, EMA 신호 자체는 pipeline에 그대로 있다), 수평선/추세선 근접 방향(manual_signals).

이 모듈의 신호 계산은 app.py의 언캐시드 경로에서 호출된다(pipeline.py의 build_signals_by_date 캐시 흐름 밖).

번호(참고용, app.py 표시 순서): 9.도지롱 10.도지숏 11.망치형롱 12.망치형숏 13.역망치형롱 14.역망치형숏
"""
import pandas as pd

import feature_flags
import volatility_expansion
from signal_types import Signal

BODY_MAX_PCT = 0.15       # 도지: 몸통비율 상한
BODY_EXT_MAX_PCT = 0.25   # 도지 확장구간 상한(15~25%) - 거래량 조건 만족 시만 도지 인정
HAMMER_BODY_MAX_PCT = 0.35         # 망치형/역망치형: 몸통비율 상한
HAMMER_OPPOSITE_WICK_MAX_PCT = 0.10  # 망치형은 위꼬리, 역망치형은 아래꼬리 비율 상한
HAMMER_WICK_BODY_MULT = 2          # 긴 꼬리(망치형은 아래꼬리) >= 몸통 x 이 배수
VOLUME_LOOKBACK = 20      # 확장구간 판정용 평균거래량 계산 기간
VOLUME_RATIO_MIN = 1.5    # 확장구간 진입에 필요한 거래량 배수(직전 20일 평균 대비)
TREND_PCT = 8.0           # (미사용: 위치 판정 교체로 제거된 N봉 추세 조건)
TREND_N_RANGE = range(1, 6)  # (미사용)

# 고점/저점 캔들 판정에 쓰는 직전 캔들 수 N - 여기 한 곳만 바꾸면 된다.
POSITION_LOOKBACK_N = 10

REFERENCE_SUFFIX = "참고 (고점/저점 아님)"   # 위치 조건을 못 채운 모양 캔들의 참고 문구

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

    # 확장구간(몸통 15~25%) 도지 판정용 거래량배수 - 당일 자신은 평균에서 제외(shift(1))
    # 해서 순수 과거 20일 평균과만 비교(미래참조 아님). 앞 20봉은 자연히 NaN.
    avg_volume = df["volume"].shift(1).rolling(VOLUME_LOOKBACK).mean()
    volume_ratio = df["volume"] / avg_volume

    shape = pd.Series([None] * len(df), dtype=object)
    for i in df.index:
        if not nonzero_range.iloc[i]:
            continue  # 고가 == 저가: 비율을 정의할 수 없음
        br = body_ratio.iloc[i]
        uw, lw = upper_wick_ratio.iloc[i], lower_wick_ratio.iloc[i]

        # 망치형/역망치형 - 거래량 조건 없음. 두 조건이 동시에 성립하는 캔들은 없다(몸통+두 꼬리 = 범위).
        if br <= HAMMER_BODY_MAX_PCT:
            if uw <= HAMMER_OPPOSITE_WICK_MAX_PCT and lw >= HAMMER_WICK_BODY_MULT * br:
                shape.iloc[i] = "hammer"
                continue
            if lw <= HAMMER_OPPOSITE_WICK_MAX_PCT and uw >= HAMMER_WICK_BODY_MULT * br:
                shape.iloc[i] = "inverted_hammer"
                continue

        # 도지 - 위 둘이 아닌 것 중 몸통 15% 이하(15~25%는 거래량 조건)
        if br > BODY_EXT_MAX_PCT:
            continue
        if br > BODY_MAX_PCT:
            vr = volume_ratio.iloc[i]
            if not (pd.notna(vr) and vr >= VOLUME_RATIO_MIN):
                continue
        if max(uw, lw) == 0:
            continue  # 두 꼬리 다 0(사실상 점) - 판정 제외
        shape.iloc[i] = "doji"

    df["body_ratio"] = body_ratio
    df["upper_wick_ratio"] = upper_wick_ratio
    df["lower_wick_ratio"] = lower_wick_ratio
    df["volume_ratio"] = volume_ratio
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


def _near_zone_flags(df: pd.DataFrame, zones: list) -> list:
    """캔들별로 고가~저가 범위가 존과 조금이라도 겹치는지(low <= 상단 and high >= 하단).
    존의 유효 범위는 zone_signals.py와 같다: time1 <= 날짜 <= time2 (time2 이후 캔들은 근처 아님)."""
    n = len(df)
    flags = [False] * n
    dates = df["open_time"].dt.strftime("%Y-%m-%d").tolist()
    highs, lows = df["high"].tolist(), df["low"].tolist()
    for z in zones:
        if z.get("line_type") != "zone" or z.get("time1") is None or z.get("price2") is None:
            continue
        top, bottom = max(z["price1"], z["price2"]), min(z["price1"], z["price2"])
        for i in range(n):
            if not flags[i] and z["time1"] <= dates[i] <= (z["time2"] or "9999-12-31") and lows[i] <= top and highs[i] >= bottom:
                flags[i] = True
    return flags


def _position_flags(df: pd.DataFrame, n_lookback: int) -> tuple[list, list]:
    """몸통 기준 고점/저점 캔들 플래그. 고점: 몸통 상단 > 직전 n개 몸통 상단 최댓값(엄격), 저점은 대칭."""
    n = len(df)
    top = df[["open", "close"]].max(axis=1).tolist()
    bottom = df[["open", "close"]].min(axis=1).tolist()
    is_high = [False] * n
    is_low = [False] * n
    for t in range(n_lookback, n):
        is_high[t] = top[t] > max(top[t - n_lookback:t])
        is_low[t] = bottom[t] < min(bottom[t - n_lookback:t])
    return is_high, is_low


def compute_candle_pattern_signals(
    df: pd.DataFrame, manual_signals: dict | None = None, invalidated_log: list | None = None,
    zones: list | None = None, n_lookback: int | None = None,
) -> dict:
    """모양(도지/망치형/역망치형) x 방향(롱/숏) 신호 - 고점/저점 캔들 위치 판정(모듈 docstring 참고).

    df: open_time/open/high/low/close/volume 컬럼을 가진 캔들 데이터프레임 (0-based 연속 인덱스)
    manual_signals: 호출부 호환용으로만 남긴 인자 - 선 근접 조건이 일시 제거돼 지금은 쓰이지 않는다.
    zones: lines_store.list_lines()의 결과를 넘기면 모든 캔들 패턴 신호에 near_zone(True/False)을 채운다
        (신호가 나는 캔들 기준). 표시용 플래그일 뿐 판정에는 영향이 없다. 안 넘기면 None.
    invalidated_log: 리스트를 넘기면 시세분출로 무효화된 숏 신호가 거기에 기록된다.
    n_lookback: 고점/저점 판정 N. 안 넘기면 POSITION_LOOKBACK_N.

    반환: {row_index: [Signal("도지 - 롱 후보", "long", next_bar=False), ...]}
    """
    n_lookback = POSITION_LOOKBACK_N if n_lookback is None else n_lookback
    df = df.reset_index(drop=True)
    n = len(df)
    signals = {i: [] for i in range(n)}

    shape_df = compute_candle_shape(df)
    shapes = shape_df["shape"].tolist()
    vol_exp_df = volatility_expansion.compute_volatility_expansion(df)
    near_flags = _near_zone_flags(df, zones) if zones is not None else None
    is_high, is_low = _position_flags(df, n_lookback)

    # (신호 캔들 i, 방향) -> next_bar(True면 고점/저점 캔들의 다음 봉에서 난 신호)
    events: dict[tuple[int, str], bool] = {}
    for direction, flags in (("short", is_high), ("long", is_low)):
        for t in range(n):
            if not flags[t]:
                continue
            if shapes[t] is not None:
                events[(t, direction)] = False
            elif t + 1 < n and shapes[t + 1] is not None:
                # t+1이 또 고점/저점 캔들이면 t+1 자신의 신호(당일)로 본다 - 같은 날 중복 신호가 안 생긴다
                events.setdefault((t + 1, direction), not flags[t + 1])

    for i in range(n):
        shape = shapes[i]
        if shape is None:
            continue
        label = PATTERN_LABEL_KR[shape]
        near = None if near_flags is None else near_flags[i]
        emitted = False

        for direction in ("long", "short"):  # 같은 캔들에서는 롱 -> 숏 순서
            if (i, direction) not in events:
                continue
            next_bar = events[(i, direction)]
            suffix = " (다음 봉)" if next_bar else ""
            emitted = True
            if direction == "long":
                signals[i].append(Signal(f"{label} - 롱 후보{suffix}", "long", near_zone=near, next_bar=next_bar))
                continue
            matches = _volatility_expansion_matches(vol_exp_df, i)
            if matches:
                if invalidated_log is not None:
                    for m in matches:
                        invalidated_log.append({
                            "index": i,
                            "date": df["open_time"].iloc[i],
                            "signal_text": f"{label} - 숏 후보{suffix}",
                            "n": m["n"],
                            "cum_pct": m["cum_pct"],
                            "cum_pct_per_n": m["cum_pct_per_n"],
                        })
                signals[i].append(Signal(f"{label} - 시세분출 무효{suffix}", "reference", near_zone=near, next_bar=next_bar))
            else:
                signals[i].append(Signal(f"{label} - 숏 후보{suffix}", "short", near_zone=near, next_bar=next_bar))

        # 신호가 안 된 모양 캔들의 "참고" 표시 (feature_flags.ENABLE_CANDLE_REFERENCE로 끌 수 있다)
        if not emitted and feature_flags.ENABLE_CANDLE_REFERENCE:
            signals[i].append(Signal(f"{label} - {REFERENCE_SUFFIX}", "reference", near_zone=near, next_bar=False))

    return signals
