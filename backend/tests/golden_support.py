"""
고정 일봉 데이터 / 선·존 스냅샷 / 골든값 공용 도우미 - conftest.py(테스트)와 regen_golden.py(골든값 다시 뽑기)가 같이 쓴다.

- DAILY_FIXTURE: 마감된 일봉 CSV(2022-01-01 ~ 2026-10-28). 캐시 parquet(git에 없음)이나 네트워크 없이 테스트가 돌게 한다.
- SNAPSHOT: 선/존 스냅샷(tests/fixtures/manual_lines_snapshot.json). 실제 manual_lines.db는 읽거나 쓰지 않는다.
- GOLDEN: 일봉 대시보드 신호 요약의 기대값(tests/golden/daily_golden.json). test_daily_golden.py가 지금 결과와 비교하고,
  `python tests/regen_golden.py`로 다시 뽑는다(사용법: docs/golden_tests.md).
"""
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
DAILY_FIXTURE = FIXTURES_DIR / "BTCUSDT_1d_2022-01-01_2026-10-28.csv"
WEEKLY_FIXTURE = FIXTURES_DIR / "BTCUSDT_1w_2017-08-14_2026-10-19.csv"
SNAPSHOT = FIXTURES_DIR / "manual_lines_snapshot.json"
GOLDEN = TESTS_DIR / "golden" / "daily_golden.json"


# --------------------------------------------------------------------------- 데이터 로드
def load_candles_csv(path: Path) -> pd.DataFrame:
    """고정 캔들 CSV -> data_fetcher.ensure_fresh_data()가 돌려주는 것과 같은 모양(UTC datetime64[ns])."""
    df = pd.read_csv(path, parse_dates=["open_time", "close_time"])
    for col in ("open_time", "close_time"):
        df[col] = df[col].astype("datetime64[ns, UTC]")
    return df


def load_daily_df() -> pd.DataFrame:
    return load_candles_csv(DAILY_FIXTURE)


def load_snapshot_lines() -> list[dict]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))["lines"]


def patch_offline_daily(monkeypatch, daily_df: pd.DataFrame | None = None) -> None:
    """일봉 데이터를 고정 CSV로 대체하고 네트워크 호출을 막는다(pytest MonkeyPatch 또는 같은 API 객체).
    pipeline.py는 `from data_fetcher import ensure_fresh_data`로 이름을 가져가서 두 곳을 모두 바꿔야 한다."""
    import data_fetcher
    import pipeline
    import requests

    df = load_daily_df() if daily_df is None else daily_df

    def frozen(*_args, **_kwargs):
        return df.copy()

    def blocked(*_args, **_kwargs):
        raise AssertionError("테스트 중 네트워크 호출은 막혀 있다 - 고정 데이터(tests/fixtures)를 쓰도록 고쳐야 한다")

    monkeypatch.setattr(data_fetcher, "ensure_fresh_data", frozen)
    monkeypatch.setattr(pipeline, "ensure_fresh_data", frozen)
    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests.sessions.Session, "send", blocked)


def seed_lines_db(lines: list[dict] | None = None) -> None:
    """lines_store.DB_PATH(호출 전에 임시 파일로 바뀌어 있어야 한다)에 스냅샷 선/존을 그대로(id 포함) 채운다."""
    import lines_store

    lines = load_snapshot_lines() if lines is None else lines
    lines_store.list_lines("BTCUSDT", "1d")          # 테이블 생성/마이그레이션
    conn = sqlite3.connect(lines_store.DB_PATH)
    try:
        for ln in lines:
            conn.execute(
                "INSERT INTO lines (id, symbol, interval, line_type, time1, price1, time2, price2, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ln["id"], ln["symbol"], ln["interval"], ln["line_type"], ln["time1"], ln["price1"],
                 ln["time2"], ln["price2"], ln["created_at"]),
            )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- 골든 요약
_NUMBER = re.compile(r"(?<![A-Za-z\d])\d[\d,]*(?:\.\d+)?")   # 글자 바로 뒤에 붙은 숫자(EMA50, EMA200)는 이름의 일부라 그대로 둔다


def category(text: str) -> str:
    """신호 문구를 항목으로 묶는다: 숫자(가격/날짜)를 '#'으로 바꿔서 같은 종류끼리 센다.
    예) '수평선 65,000 근접 - 지지 시험 (매수 후보)' -> '수평선 # 근접 - 지지 시험 (매수 후보)' (EMA50/EMA200 같은 이름의 숫자는 유지)."""
    return _NUMBER.sub("#", text)


def summarize(response: dict) -> dict:
    """get_dashboard_data() 응답에서 골든값 요약을 만든다 - 건수 중심(날짜별 세부는 해시로)."""
    candles = response["candles"]
    items = [(date, s) for date, v in response["signals"].items() for s in v]
    by_category = Counter(category(s["text"]) for _, s in items)
    by_direction = Counter(s["direction"] for _, s in items)
    zone_by_ref = Counter(str(s["ref_id"]) for _, s in items if s["source"] == "zone")
    near = Counter({True: 0, False: 0, None: 0})
    for _, s in items:
        near[s["near_zone"]] += 1
    digest = hashlib.sha256(
        "\n".join(sorted(
            f"{d}|{s['direction']}|{s['text']}|{s['ref_id']}|{s['near_zone']}|{s['next_bar']}" for d, s in items
        )).encode("utf-8")
    ).hexdigest()
    return {
        "candles": len(candles),
        "first_date": candles[0]["date"],
        "last_date": candles[-1]["date"],
        "manual_line_ids": sorted(ln["id"] for ln in response["manual_lines"]),
        "signal_days": len(response["signals"]),
        "signals_total": len(items),
        "by_direction": dict(sorted(by_direction.items())),
        "near_zone": {"true": near[True], "false": near[False], "none": near[None]},
        "next_bar_true": sum(1 for _, s in items if s["next_bar"]),
        "zone_signals_by_ref": dict(sorted(zone_by_ref.items())),
        "by_category": dict(sorted(by_category.items())),
        "signals_sha256": digest,
    }


def _fmt(value) -> str:
    return "(없음)" if value is None else str(value)


def diff_summary(expected: dict, actual: dict) -> list[str]:
    """기대값과 실제 요약의 차이를 '항목: 기대 -> 실제 (증감)' 줄 목록으로 만든다. 같으면 빈 목록."""
    lines: list[str] = []

    def compare(path: str, exp, act):
        if isinstance(exp, dict) and isinstance(act, dict):
            for key in sorted(set(exp) | set(act)):
                compare(f"{path}[{key!r}]" if path else str(key), exp.get(key), act.get(key))
            return
        if exp == act:
            return
        if isinstance(exp, int) and isinstance(act, int) and not isinstance(exp, bool):
            lines.append(f"  - {path}: {exp} -> {act} ({act - exp:+d})")
        else:
            lines.append(f"  - {path}: {_fmt(exp)} -> {_fmt(act)}")

    for key in actual.keys() | expected.keys():
        if key == "signals_sha256":
            continue
        compare(key, expected.get(key), actual.get(key))
    lines.sort()
    if not lines and expected.get("signals_sha256") != actual.get("signals_sha256"):
        lines.append("  - 항목별 건수는 같지만 개별 신호(날짜/문구/방향/연결 도형)가 바뀌었다 (signals_sha256 불일치)")
    return lines


def failure_message(expected: dict, actual: dict) -> str:
    diffs = diff_summary(expected, actual)
    return (
        f"일봉 골든값이 바뀌었다 ({len(diffs)}개 항목: 기대 -> 실제):\n" + "\n".join(diffs) + "\n"
        "의도한 규칙 변경이면 골든값을 다시 뽑아 diff를 확인한 뒤 커밋한다:\n"
        "  cd backend && .venv/Scripts/python tests/regen_golden.py      (자세한 사용법: docs/golden_tests.md)"
    )
