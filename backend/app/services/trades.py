"""
기능 2 (Phase 2-1) - 매매 계획/기록

하나의 매매 레코드가 draft -> open -> closed로 상태 이동한다(별도 화면 두 개가
아니라 레코드 하나의 라이프사이클). 계산 로직(포지션 사이즈 환산, 1R, 실현
R배수)은 기능 3(position_sizing.py)의 calculate_position()과 동일한 정의를
재사용한다 - 새로 다른 공식을 만들지 않음.

포지션 사이즈 입력: 사용자에게는 증거금(margin) + 레버리지로 입력받고,
저장 시 quantity(수량)로 환산해 같이 저장한다(사용자 결정, 9/27) - R배수
계산은 항상 quantity 기준으로 하는 게 레버리지 개념이 안 섞여서 제일 깔끔
하기 때문. margin/leverage 원본 값도 화면 표시용으로 그대로 보존한다.

분할 진입/TP/청산은 전부 "가격 + 비중%" 배열로 통일 - 기능 3과 동일 형식이라
"계산기로 채우기" 연동 시 값 형식이 그대로 맞아떨어진다.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "trades.db"

WEIGHT_SUM_TOLERANCE = 0.01  # 기능 3(position_sizing.py)과 동일한 톨러런스

VALID_DIRECTIONS = ("long", "short")
VALID_EXIT_REASONS = ("tp", "sl", "invalidation", "manual")

# "기능1 신호 체크" 필드 - 특정 날짜에 실제 발생한 신호 인스턴스가 아니라, 신호
# "카테고리" 목록에서 다중 선택(Phase 2-2의 신호조합별 성과 통계와 바로 연결하기
# 위함). scripts/pipeline.py의 8개 카운트 신호 + candle_patterns.py 6종 + 수동선
# 근접/돌파를 총망라. 신호가 추가되면 이 목록도 같이 늘린다.
SIGNAL_TAGS = [
    "매물소진 매수/매도",
    "정배열 진입/유지",
    "역배열 진입/유지",
    "EMA50/200 터치",
    "다우이론 HH/LH/HL/LL",
    "RSI 과매도",
    "RSI 과매수",
    "장악형 하락",
    "도지 롱/숏",
    "망치형 롱/숏",
    "역망치형 롱/숏",
    "수평선/추세선 근접·돌파",
    "재량 진입 (신호 없음)",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL CHECK (status IN ('draft', 'open', 'closed')),
    direction TEXT NOT NULL CHECK (direction IN ('long', 'short')),

    entry_rationale TEXT,
    signal_tags TEXT,           -- JSON 문자열 배열
    invalidation_note TEXT,
    invalidation_price REAL,
    stop_loss REAL,
    entries TEXT,               -- JSON [{"price":, "weight":}]
    take_profits TEXT,          -- JSON [{"price":, "weight":}]
    margin REAL,
    leverage REAL,
    avg_entry REAL,             -- 파생값(표시/계산 편의용 저장)
    quantity REAL,              -- 파생값 = margin*leverage/avg_entry
    risk_amount REAL,           -- 파생값 = 1R(통화) = quantity * |avg_entry-stop_loss|
    planned_at TEXT NOT NULL,

    exits TEXT,                 -- JSON [{"price":, "weight":, "realized_pnl":}]
    exit_reason TEXT,
    exit_memo TEXT,
    realized_pnl_total REAL,    -- 파생값
    realized_r REAL,            -- 파생값 = realized_pnl_total / risk_amount
    closed_at TEXT
);
"""


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


# --- 검증 (draft 저장에는 적용 안 함 - 임시저장은 뭐가 비어있든 그대로 저장) ---

class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(", ".join(errors))


def _check_weight_sum(items: list[dict], label: str, errors: list[str]) -> None:
    if not items:
        errors.append(f"{label}_empty")
        return
    if any(item["price"] <= 0 for item in items):
        errors.append(f"{label}_price_invalid")
    total = sum(item["weight"] for item in items)
    if abs(total - 100) > WEIGHT_SUM_TOLERANCE:
        errors.append(f"{label}_weight_sum_invalid")


def validate_plan(
    direction: str, entries: list[dict], stop_loss: float, take_profits: list[dict],
    entry_rationale: str | None = None, invalidation_note: str | None = None,
    invalidation_price: float | None = None, margin: float | None = None,
    leverage: float | None = None,
) -> list[str]:
    """진입 전 계획을 open 상태로 확정할 때 검증. 위반 사항 코드 리스트를 반환
    (빈 리스트면 통과). entries/take_profits: [{"price":, "weight":}, ...]

    스펙 표(진입 근거/무효화 서술+가격/SL/포지션사이즈 전부 "필수")에 맞춰
    비중 합/가격 순서뿐 아니라 필수 필드 존재 여부도 확인한다 - draft 저장
    시에는 이 함수 자체를 호출하지 않으므로(create_trade/update_trade의
    draft 분기) 임시저장에는 전혀 영향 없음.
    """
    errors: list[str] = []

    if direction not in VALID_DIRECTIONS:
        errors.append("invalid_direction")

    if not entry_rationale or not entry_rationale.strip():
        errors.append("entry_rationale_required")
    if not invalidation_note or not invalidation_note.strip():
        errors.append("invalidation_note_required")
    if invalidation_price is None:
        errors.append("invalidation_price_required")
    if stop_loss is None:
        errors.append("stop_loss_required")
    if not margin:
        errors.append("margin_required")
    if not leverage:
        errors.append("leverage_required")

    _check_weight_sum(entries, "entries", errors)
    _check_weight_sum(take_profits, "take_profits", errors)

    price_already_flagged = any(e.endswith("_price_invalid") for e in errors)
    if entries and take_profits and direction in VALID_DIRECTIONS and stop_loss is not None and not price_already_flagged:
        entry_prices = [e["price"] for e in entries]
        tp_prices = [t["price"] for t in take_profits]
        if direction == "long":
            if not (stop_loss < min(entry_prices)):
                errors.append("invalid_price_order")
            elif not (max(entry_prices) < min(tp_prices)):
                errors.append("invalid_price_order")
        else:
            if not (stop_loss > max(entry_prices)):
                errors.append("invalid_price_order")
            elif not (min(entry_prices) > max(tp_prices)):
                errors.append("invalid_price_order")

    return errors


def validate_close(exits: list[dict], exit_reason: str) -> list[str]:
    errors: list[str] = []
    _check_weight_sum(exits, "exits", errors)
    if exit_reason not in VALID_EXIT_REASONS:
        errors.append("invalid_exit_reason")
    return errors


# --- 파생값 계산 (기능 3 calculate_position()과 동일한 정의 재사용) ---

def compute_plan_derived(entries: list[dict], stop_loss: float, margin: float, leverage: float) -> dict:
    avg_entry = sum(e["price"] * (e["weight"] / 100) for e in entries) if entries else 0.0
    notional = margin * leverage
    quantity = notional / avg_entry if avg_entry else 0.0
    # risk_amount = notional * stop_pct와 동일 (stop_pct = |avg_entry-stop_loss|/avg_entry)
    risk_amount = quantity * abs(avg_entry - stop_loss)
    return {"avg_entry": avg_entry, "quantity": quantity, "risk_amount": risk_amount}


def compute_close_derived(exits: list[dict], risk_amount: float | None) -> dict:
    realized_pnl_total = sum(e["realized_pnl"] for e in exits) if exits else 0.0
    realized_r = realized_pnl_total / risk_amount if risk_amount else None
    return {"realized_pnl_total": realized_pnl_total, "realized_r": realized_r}


# --- CRUD ---

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for json_field in ("signal_tags", "entries", "take_profits", "exits"):
        d[json_field] = json.loads(d[json_field]) if d[json_field] else ([] if json_field != "exits" else None)
    return d


def create_trade(payload: dict, draft: bool = False) -> dict:
    """진입 전 계획 저장. draft=True면 검증을 건너뛰고 뭐가 비어있든 그대로 저장."""
    direction = payload["direction"]
    entries = payload.get("entries") or []
    take_profits = payload.get("take_profits") or []
    stop_loss = payload.get("stop_loss")

    margin = payload.get("margin") or 0.0
    leverage = payload.get("leverage") or 0.0

    if not draft:
        errors = validate_plan(
            direction, entries, stop_loss, take_profits,
            entry_rationale=payload.get("entry_rationale"),
            invalidation_note=payload.get("invalidation_note"),
            invalidation_price=payload.get("invalidation_price"),
            margin=margin, leverage=leverage,
        )
        if errors:
            raise ValidationError(errors)

    derived = compute_plan_derived(entries, stop_loss or 0.0, margin, leverage) if entries else {
        "avg_entry": None, "quantity": None, "risk_amount": None,
    }

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO trades (
                status, direction, entry_rationale, signal_tags, invalidation_note,
                invalidation_price, stop_loss, entries, take_profits, margin, leverage,
                avg_entry, quantity, risk_amount, planned_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "draft" if draft else "open",
                direction,
                payload.get("entry_rationale"),
                json.dumps(payload.get("signal_tags") or [], ensure_ascii=False),
                payload.get("invalidation_note"),
                payload.get("invalidation_price"),
                stop_loss,
                json.dumps(entries, ensure_ascii=False),
                json.dumps(take_profits, ensure_ascii=False),
                margin,
                leverage,
                derived["avg_entry"],
                derived["quantity"],
                derived["risk_amount"],
                now,
            ),
        )
        trade_id = cur.lastrowid
    return get_trade(trade_id)


def update_trade(trade_id: int, payload: dict, draft: bool = False) -> dict:
    """draft 상태 계획 수정, 또는 draft -> open 확정. open/closed 상태 레코드의
    계획 필드 수정도 이 함수로 처리(청산 후 기록은 close_trade()가 별도로 처리)."""
    existing = get_trade(trade_id)
    if existing["status"] == "closed":
        raise ValidationError(["trade_already_closed"])

    direction = payload.get("direction", existing["direction"])
    entries = payload.get("entries", existing["entries"]) or []
    take_profits = payload.get("take_profits", existing["take_profits"]) or []
    stop_loss = payload.get("stop_loss", existing["stop_loss"])
    margin = payload.get("margin", existing["margin"]) or 0.0
    leverage = payload.get("leverage", existing["leverage"]) or 0.0

    if not draft:
        errors = validate_plan(
            direction, entries, stop_loss, take_profits,
            entry_rationale=payload.get("entry_rationale", existing["entry_rationale"]),
            invalidation_note=payload.get("invalidation_note", existing["invalidation_note"]),
            invalidation_price=payload.get("invalidation_price", existing["invalidation_price"]),
            margin=margin, leverage=leverage,
        )
        if errors:
            raise ValidationError(errors)
    derived = compute_plan_derived(entries, stop_loss or 0.0, margin, leverage) if entries else {
        "avg_entry": None, "quantity": None, "risk_amount": None,
    }

    with _connect() as conn:
        conn.execute(
            """
            UPDATE trades SET
                status = ?, direction = ?, entry_rationale = ?, signal_tags = ?,
                invalidation_note = ?, invalidation_price = ?, stop_loss = ?,
                entries = ?, take_profits = ?, margin = ?, leverage = ?,
                avg_entry = ?, quantity = ?, risk_amount = ?
            WHERE id = ?
            """,
            (
                "draft" if draft else "open",
                direction,
                payload.get("entry_rationale", existing["entry_rationale"]),
                json.dumps(payload.get("signal_tags", existing["signal_tags"]) or [], ensure_ascii=False),
                payload.get("invalidation_note", existing["invalidation_note"]),
                payload.get("invalidation_price", existing["invalidation_price"]),
                stop_loss,
                json.dumps(entries, ensure_ascii=False),
                json.dumps(take_profits, ensure_ascii=False),
                margin,
                leverage,
                derived["avg_entry"],
                derived["quantity"],
                derived["risk_amount"],
                trade_id,
            ),
        )
    return get_trade(trade_id)


def close_trade(trade_id: int, exits: list[dict], exit_reason: str, exit_memo: str | None) -> dict:
    existing = get_trade(trade_id)
    if existing["status"] == "closed":
        raise ValidationError(["trade_already_closed"])
    if existing["status"] == "draft":
        raise ValidationError(["trade_not_open"])

    errors = validate_close(exits, exit_reason)
    if errors:
        raise ValidationError(errors)

    derived = compute_close_derived(exits, existing["risk_amount"])
    now = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        conn.execute(
            """
            UPDATE trades SET
                status = 'closed', exits = ?, exit_reason = ?, exit_memo = ?,
                realized_pnl_total = ?, realized_r = ?, closed_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(exits, ensure_ascii=False),
                exit_reason,
                exit_memo,
                derived["realized_pnl_total"],
                derived["realized_r"],
                now,
                trade_id,
            ),
        )
    return get_trade(trade_id)


def get_trade(trade_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if row is None:
        raise ValidationError(["trade_not_found"])
    return _row_to_dict(row)


def list_trades(status: str | None = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM trades WHERE status = ? ORDER BY id DESC", (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_trade(trade_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
