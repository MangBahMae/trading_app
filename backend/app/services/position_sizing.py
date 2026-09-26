"""
포지션 사이징 계산기 - 순수 계산 로직 (FastAPI/Streamlit 어디에도 의존하지 않음)

scripts/position_sizing.py의 calculate_position()과 포맷팅/환율 조회 함수를
그대로 이식한 것. 계산식 자체는 한 글자도 바꾸지 않았다 - Streamlit 의존
부분(st.cache_data, render_* 함수들)만 제거/대체했다.

계산 순서:
1. avg_entry = Σ(entries 가격 × 비중/100)
2. stop_pct = |avg_entry - stop_loss| / avg_entry
3. risk_amount(1R) = balance × risk_pct/100
4. position_size = risk_amount / stop_pct
5. btc_quantity = position_size / avg_entry
6. leverage = position_size / margin (margin 없으면 None)
7. 각 TP: tp_r = (tp가격-avg_entry)/avg_entry/stop_pct (숏이면 부호 반전 -
   숏은 가격 하락이 이익이므로, tp가격이 avg_entry보다 낮을 때 양(+)의 R이
   나와야 함)
8. weighted_avg_r = Σ(tp_r × 그 TP 비중/100)

범위 제외(이번 단계 아님): 바이낸스 API 잔고 조회, 최소 주문금액 검증,
복구수익률/연속손실 시뮬레이션/Risk of Ruin, 기능2 연계, 손절 트레일링.
"""
import time

import requests

WARNING_MESSAGES_KR = {
    "entries_sum_invalid": "진입 비중 합이 100%가 아닙니다",
    "tp_sum_invalid": "TP 비중 합이 100%가 아닙니다",
    "unfavorable_risk_reward": "손익비가 1:1 미만입니다 (기대값 불리)",
    "risk_pct_deviation": "기본값(1%)에서 벗어났습니다",
    "invalid_stop_direction": "손절가 방향이 진입 방향과 맞지 않습니다",
}

WEIGHT_SUM_TOLERANCE = 0.01  # 부동소수점 오차 흡수용(예: 33.33*3)

# USDT/KRW 환율 기본값(폴백) - 실시간 조회가 실패했을 때만 사용된다.
# USDT는 달러 페그 스테이블코인이므로 USD/KRW 환율로 근사한다.
EXCHANGE_RATE_KRW_PER_USDT = 1350.0
EXCHANGE_RATE_API_URL = "https://api.exchangerate-api.com/v4/latest/USD"

# st.cache_data(ttl=600) 대체 - 모듈 전역에 마지막 조회 시각/값을 저장해두고
# TTL 안에서는 재조회 없이 캐시된 값을 반환한다.
_RATE_CACHE_TTL_SECONDS = 600
_rate_cache: dict = {"value": None, "fetched_at": 0.0}


def fetch_usdt_krw_rate(force_refresh: bool = False) -> float | None:
    """USD/KRW 환율을 조회해 USDT/KRW 근사치로 사용한다 (USDT는 달러 페그).

    10분 캐시 - 매 호출마다 외부 API를 부르지 않기 위함. force_refresh=True면
    캐시를 무시하고 즉시 재조회한다(기존 Streamlit "환율 새로고침" 버튼 대응).
    실패 시 None을 반환하고, 호출부에서 기본값(EXCHANGE_RATE_KRW_PER_USDT)으로
    폴백한다.
    """
    now = time.time()
    if (
        not force_refresh
        and _rate_cache["value"] is not None
        and now - _rate_cache["fetched_at"] < _RATE_CACHE_TTL_SECONDS
    ):
        return _rate_cache["value"]

    try:
        resp = requests.get(EXCHANGE_RATE_API_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["KRW"])
        _rate_cache["value"] = rate
        _rate_cache["fetched_at"] = now
        return rate
    except Exception:
        # 원본(scripts/position_sizing.py)과 동일하게 실패 시 무조건 None 반환 -
        # 폴백 처리는 호출부(라우터)에서 EXCHANGE_RATE_KRW_PER_USDT로 한다.
        return None


def format_krw_full(amount: float) -> str:
    """3자리마다 쉼표를 넣은 원화 표기 (예: 5,000,000원)."""
    return f"{amount:,.0f}원"


def format_krw_compact(amount: float) -> str:
    """500만원 / 1,200만원 / 1.5억원처럼 한글 축약 단위 표기."""
    if amount == 0:
        return "0원"
    sign = "-" if amount < 0 else ""
    a = abs(amount)
    if a >= 100_000_000:
        eok = a / 100_000_000
        text = f"{eok:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}억원"
    if a >= 10_000:
        man = a / 10_000
        if abs(man - round(man)) < 1e-9:
            text = f"{int(round(man)):,}"
        else:
            text = f"{man:,.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}만원"
    return f"{sign}{a:,.0f}원"


def format_krw_with_compact(amount: float) -> str:
    """"5,000,000원 (500만원)"처럼 정확한 금액 + 축약 표기를 함께 반환."""
    return f"{format_krw_full(amount)} ({format_krw_compact(amount)})"


def format_usdt_krw(usdt_amount: float, exchange_rate: float) -> str:
    """"≈ 87,750,000원 (8,775만원)"처럼 USDT 입력 옆에 붙일 원화 환산 캡션."""
    krw = usdt_amount * exchange_rate
    return f"≈ {format_krw_with_compact(krw)}"


def calculate_position(
    balance: float,
    risk_pct: float,
    direction: str,
    entries: list[tuple[float, float]],
    stop_loss: float,
    take_profits: list[tuple[float, float]],
    margin: float | None = None,
) -> dict:
    warnings: list[str] = []

    entries_weight_sum = sum(w for _, w in entries)
    if abs(entries_weight_sum - 100) > WEIGHT_SUM_TOLERANCE:
        warnings.append("entries_sum_invalid")

    if take_profits:
        tp_weight_sum = sum(w for _, w in take_profits)
        if abs(tp_weight_sum - 100) > WEIGHT_SUM_TOLERANCE:
            warnings.append("tp_sum_invalid")

    if risk_pct != 1.0:
        warnings.append("risk_pct_deviation")

    avg_entry = sum(price * (weight / 100) for price, weight in entries)

    is_long = direction == "long"
    if is_long and stop_loss >= avg_entry:
        warnings.append("invalid_stop_direction")
    elif not is_long and stop_loss <= avg_entry:
        warnings.append("invalid_stop_direction")

    stop_pct = abs(avg_entry - stop_loss) / avg_entry if avg_entry else 0.0

    risk_amount = balance * risk_pct / 100

    if stop_pct > 0:
        position_size = risk_amount / stop_pct
        btc_quantity = position_size / avg_entry
    else:
        # 손절가가 진입가와 동일(거리 0) - 포지션 사이즈 정의 불가, 크래시 대신 None 반환
        position_size = None
        btc_quantity = None

    leverage = None
    if margin and position_size is not None:
        leverage = position_size / margin

    tp_results: list[dict] = []
    weighted_avg_r = None
    if take_profits and stop_pct > 0:
        weighted_avg_r = 0.0
        for price, weight in take_profits:
            raw = (price - avg_entry) / avg_entry / stop_pct
            r_multiple = raw if is_long else -raw
            tp_results.append({"price": price, "weight_pct": weight, "r_multiple": r_multiple})
            weighted_avg_r += r_multiple * (weight / 100)

        if weighted_avg_r < 1:
            warnings.append("unfavorable_risk_reward")

    return {
        "avg_entry": avg_entry,
        "stop_pct": stop_pct,
        "risk_amount": risk_amount,
        "position_size": position_size,
        "btc_quantity": btc_quantity,
        "leverage": leverage,
        "tp_results": tp_results,
        "weighted_avg_r": weighted_avg_r,
        "warnings": warnings,
    }
