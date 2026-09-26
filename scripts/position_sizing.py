"""
기능 3 - 포지션 사이징 계산기

계산 로직(calculate_position)은 Streamlit 의존성 없는 순수 함수 - 단위
테스트/직접 호출 검증 가능. 화면 로직(render_position_sizing)은 app.py에서
사이드바 메뉴로 분기해서 호출한다.

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
import pandas as pd
import requests
import streamlit as st

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


@st.cache_data(ttl=600, show_spinner=False)
def fetch_usdt_krw_rate() -> float | None:
    """USD/KRW 환율을 조회해 USDT/KRW 근사치로 사용한다 (USDT는 달러 페그).

    10분 캐시 - 매 rerun마다 외부 API를 호출하지 않기 위함. 실패 시 None을
    반환하고, 호출부에서 기본값(EXCHANGE_RATE_KRW_PER_USDT)으로 폴백한다.
    """
    try:
        resp = requests.get(EXCHANGE_RATE_API_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"]["KRW"]
        return float(rate)
    except Exception:
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


def _render_krw_live_preview(exchange_rate: float, initial_usdt: float = 0.0, label: str = "환산 미리보기") -> None:
    """순수 HTML/JS(st.iframe)로 만든 "타이핑 즉시 원화 환산" 위젯.

    st.iframe()에 HTML 문자열을 넘기면 항상 별도 iframe에서 돌기 때문에 iframe 밖에 있는
    네이티브 st.number_input의 값을 되돌려받을 수 없다(양방향 통신 불가). 그래서
    이 위젯은 어디까지나 "입력하면서 바로 감 잡기용" 참고 표시이고, 실제
    calculate_position()에 들어가는 값은 이 위젯 바로 아래의 st.number_input에서
    별도로 받는다(호출부 참고).

    포맷팅 로직(억/만 단위 분기)은 format_krw_compact()/format_krw_with_compact()와
    반드시 동일한 결과가 나오도록 JS로 1:1 재구현했다 - 케이스 대조 검증 완료
    (5,000,000 -> "500만원", 1,625,000 -> "162.5만원", 150,000,000 -> "1.5억원" 등).
    """
    html = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <div style="font-size: 0.8rem; color: #6b7280; margin-bottom: 4px;">{label}</div>
  <input id="krw_preview_input" type="number" value="{initial_usdt}" step="1"
         style="width: 100%; box-sizing: border-box; padding: 8px 10px; font-size: 1rem;
                border: 1px solid #d1d5db; border-radius: 6px; outline: none;" />
  <div id="krw_preview_output" style="margin-top: 6px; font-size: 0.85rem; color: #374151;">
    &nbsp;
  </div>
</div>
<script>
  (function() {{
    const rate = {exchange_rate};

    function formatKrwFull(amount) {{
      return Math.round(amount).toLocaleString('en-US') + '원';
    }}

    function formatKrwCompact(amount) {{
      if (amount === 0) return '0원';
      const sign = amount < 0 ? '-' : '';
      const a = Math.abs(amount);
      let text;
      if (a >= 100000000) {{
        const eok = a / 100000000;
        text = eok.toFixed(2).replace(/0+$/, '').replace(/\\.$/, '');
        return sign + text + '억원';
      }}
      if (a >= 10000) {{
        const man = a / 10000;
        if (Math.abs(man - Math.round(man)) < 1e-9) {{
          text = Math.round(man).toLocaleString('en-US');
        }} else {{
          text = man.toFixed(2).replace(/0+$/, '').replace(/\\.$/, '');
        }}
        return sign + text + '만원';
      }}
      return sign + Math.round(a).toLocaleString('en-US') + '원';
    }}

    function formatKrwWithCompact(amount) {{
      return formatKrwFull(amount) + ' (' + formatKrwCompact(amount) + ')';
    }}

    function update() {{
      const input = document.getElementById('krw_preview_input');
      const output = document.getElementById('krw_preview_output');
      const usdt = parseFloat(input.value) || 0;
      const krw = usdt * rate;
      output.textContent = usdt.toLocaleString('en-US') + ' USDT ≈ ' + formatKrwWithCompact(krw);
    }}

    document.getElementById('krw_preview_input').addEventListener('input', update);
    update();
  }})();
</script>
"""
    st.iframe(html, height=95)


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


def _init_list(key: str, default_price: float, min_items: int) -> None:
    if key not in st.session_state:
        st.session_state[key] = [
            {"id": i, "price": default_price, "weight": 100.0 if min_items == 1 else 0.0}
            for i in range(min_items)
        ]
        st.session_state[f"{key}_next_id"] = min_items


def _render_price_weight_list(
    key: str, label: str, default_price: float = 0.0, min_items: int = 1,
    exchange_rate: float = 0.0,
) -> list[tuple[float, float]]:
    """가격+비중% 행을 추가/삭제할 수 있는 동적 리스트 UI.

    행마다 안정적인 id(추가 순서 기반, 삭제돼도 재사용 안 함)를 위젯 key에 써서 -
    인덱스를 key로 쓰면 중간 행 삭제 시 뒤 행들의 key가 밀리면서 값이 꼬이는
    문제가 생기는데, id 기반이면 그 문제가 없다.

    가격은 USDT 표기를 그대로 유지하고, exchange_rate(>0)가 주어지면 그 아래에
    원화 환산 금액을 캡션으로만 덧붙인다 (계산에는 전혀 영향 없음).
    """
    _init_list(key, default_price, min_items)
    items = st.session_state[key]

    to_delete_id = None
    for idx, item in enumerate(items):
        item_id = item["id"]
        cols = st.columns([3, 2, 1])
        with cols[0]:
            price = st.number_input(
                f"{label} {idx + 1} 가격", min_value=0.0, value=float(item["price"]),
                key=f"{key}_price_{item_id}", step=1.0,
            )
            if price > 0 and exchange_rate > 0:
                st.caption(f"{price:,.0f} USDT {format_usdt_krw(price, exchange_rate)}")
        with cols[1]:
            if len(items) == 1:
                st.number_input(
                    f"{label} {idx + 1} 비중%", value=100.0,
                    key=f"{key}_weight_disp_{item_id}", disabled=True,
                )
                weight = 100.0
            else:
                weight = st.number_input(
                    f"{label} {idx + 1} 비중%", min_value=0.0, max_value=100.0,
                    value=float(item["weight"]), key=f"{key}_weight_{item_id}", step=1.0,
                )
        with cols[2]:
            st.write("")
            if len(items) > min_items and st.button("삭제", key=f"{key}_del_{item_id}"):
                to_delete_id = item_id
        item["price"] = price
        item["weight"] = weight

    if to_delete_id is not None:
        st.session_state[key] = [it for it in items if it["id"] != to_delete_id]
        st.rerun(scope="fragment")

    if st.button(f"+ {label} 추가", key=f"{key}_add_btn"):
        new_id = st.session_state[f"{key}_next_id"]
        st.session_state[key].append({"id": new_id, "price": default_price, "weight": 0.0})
        st.session_state[f"{key}_next_id"] = new_id + 1
        st.rerun(scope="fragment")

    if not items:
        st.caption(f"{label} 없음")

    return [(it["price"], it["weight"]) for it in st.session_state[key]]


@st.fragment
def render_position_sizing() -> None:
    st.title("포지션 사이징 계산기")

    # 환율은 10분 캐시로 자동 조회 - "새로고침" 버튼으로 즉시 재조회 가능하고,
    # API 실패 시 기본값(EXCHANGE_RATE_KRW_PER_USDT)으로 폴백한다.
    rate_col, refresh_col = st.columns([5, 1])
    with refresh_col:
        st.write("")
        if st.button("환율 새로고침", key="ps_refresh_rate"):
            fetch_usdt_krw_rate.clear()
    fetched_rate = fetch_usdt_krw_rate()
    with rate_col:
        if fetched_rate is not None:
            st.caption(f"환율(자동, USD/KRW 기준): 1 USDT ≈ {fetched_rate:,.2f}원")
        else:
            st.caption(f"환율 자동 조회 실패 - 기본값 사용 중: 1 USDT ≈ {EXCHANGE_RATE_KRW_PER_USDT:,.2f}원")

    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.subheader("입력")
        exchange_rate = fetched_rate if fetched_rate is not None else EXCHANGE_RATE_KRW_PER_USDT

        # 타이핑 중 실시간(엔터 없이) 원화 환산을 보여주는 참고용 미리보기 - HTML/JS라
        # 서버 왕복 없이 즉시 갱신되지만, 계산에는 반영되지 않는다(아래 실제 입력
        # 필드에 별도로 입력 필요 - 구현 배경은 함수 docstring 참고).
        _render_krw_live_preview(
            exchange_rate, initial_usdt=350.0,
            label="잔고 환산 미리보기 (참고용 - 타이핑 즉시 갱신, 계산에는 반영 안 됨)",
        )
        balance_usdt = st.number_input(
            "잔고 (USDT) - 실제 계산에 사용", min_value=0.0, value=350.0, step=10.0,
        )
        balance = balance_usdt * exchange_rate
        if balance_usdt > 0:
            st.caption(f"확정값: {format_krw_with_compact(balance)}")

        risk_pct = st.number_input("리스크 %", min_value=0.0, value=1.0, step=0.1)
        direction_label = st.radio("방향", ["롱", "숏"], horizontal=True)
        direction = "long" if direction_label == "롱" else "short"

        st.markdown("**진입가**")
        entries = _render_price_weight_list(
            "ps_entries", "진입", default_price=0.0, min_items=1, exchange_rate=exchange_rate,
        )

        stop_loss = st.number_input("손절가", min_value=0.0, value=0.0, step=1.0)
        if stop_loss > 0 and exchange_rate > 0:
            st.caption(f"{stop_loss:,.0f} USDT {format_usdt_krw(stop_loss, exchange_rate)}")

        st.markdown("**TP가**")
        take_profits = _render_price_weight_list(
            "ps_tps", "TP", default_price=0.0, min_items=0, exchange_rate=exchange_rate,
        )

        margin_input = st.number_input("투입 마진 (선택, 0이면 레버리지 생략)", min_value=0.0, value=0.0, step=10_000.0)

    result = calculate_position(
        balance=balance,
        risk_pct=risk_pct,
        direction=direction,
        entries=entries,
        stop_loss=stop_loss,
        take_profits=take_profits,
        margin=margin_input if margin_input > 0 else None,
    )

    with col_r:
        st.subheader("결과")

        m1, m2 = st.columns(2)
        m1.metric("1R (리스크 금액)", f"{result['risk_amount']:,.0f}원")
        m1.caption(format_krw_compact(result["risk_amount"]))
        if result["position_size"] is not None:
            m2.metric("포지션 사이즈", f"{result['position_size']:,.0f}원")
            m2.caption(format_krw_compact(result["position_size"]))
        else:
            m2.metric("포지션 사이즈", "계산 불가")

        st.write(f"예상 평단: {result['avg_entry']:,.2f}")
        st.write(f"손절 폭: {result['stop_pct'] * 100:.2f}%")
        if result["btc_quantity"] is not None:
            st.write(f"BTC 수량: {result['btc_quantity']:.6f}")
        else:
            st.write("BTC 수량: 계산 불가 (손절가가 진입가와 동일)")
        if result["leverage"] is not None:
            st.write(f"레버리지: {result['leverage']:.2f}배")

        if result["tp_results"]:
            st.markdown("**TP별 R값**")
            tp_df = pd.DataFrame(result["tp_results"])
            tp_df.columns = ["가격", "비중%", "R배수"]
            st.dataframe(tp_df, hide_index=True, width="stretch")
            st.write(f"가중평균 R: {result['weighted_avg_r']:.2f}")
            st.write(f"손익비: 1 : {result['weighted_avg_r']:.2f}")

        for w in result["warnings"]:
            st.warning(WARNING_MESSAGES_KR.get(w, w))


if __name__ == "__main__":
    # 테스트 케이스 1 - TP 없음
    r1 = calculate_position(
        balance=500_000, risk_pct=1.0, direction="long",
        entries=[(118_000, 100)], stop_loss=113_800, take_profits=[],
    )
    print("=== 테스트 1 (TP 없음) ===")
    print(f"avg_entry={r1['avg_entry']:.0f} (기대 118000)")
    print(f"stop_pct={r1['stop_pct']*100:.4f}% (기대 약 3.56%)")
    print(f"risk_amount={r1['risk_amount']:.0f} (기대 5000)")
    print(f"position_size={r1['position_size']:.0f} (기대 약 140449)")
    print(f"warnings={r1['warnings']}")
    assert r1["avg_entry"] == 118_000
    assert r1["risk_amount"] == 5_000
    assert abs(r1["stop_pct"] * 100 - 3.5593) < 0.01
    # 스펙의 "약 140,449"는 stop_pct를 3.56%로 반올림한 뒤 역산한 근사치 -
    # 실제 계산은 반올림 없이 풀정밀도로 하므로 140,476.19가 정확한 값(0.02% 차이).
    assert abs(r1["position_size"] - 140_476.19) < 1
    assert r1["warnings"] == []

    # 테스트 케이스 2 - TP 2개
    r2 = calculate_position(
        balance=500_000, risk_pct=1.0, direction="long",
        entries=[(118_000, 100)], stop_loss=113_800,
        take_profits=[(122_000, 50), (126_000, 50)],
    )
    print()
    print("=== 테스트 2 (TP 2개) ===")
    for tp in r2["tp_results"]:
        print(f"  TP {tp['price']}: R={tp['r_multiple']:.4f}")
    print(f"weighted_avg_r={r2['weighted_avg_r']:.4f} (기대 약 1.42~1.43)")
    print(f"warnings={r2['warnings']}")
    assert abs(r2["tp_results"][0]["r_multiple"] - 0.9524) < 0.01
    assert abs(r2["tp_results"][1]["r_multiple"] - 1.9048) < 0.01
    assert abs(r2["weighted_avg_r"] - 1.4286) < 0.01

    print()
    print("전부 통과")
