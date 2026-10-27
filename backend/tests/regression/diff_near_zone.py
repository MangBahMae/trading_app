"""
캔들 패턴 신호 near_zone 플래그 추가 전/후 diff (읽기 전용).

- 전: git HEAD의 candle_patterns.py(+signal_types.py)   후: 작업 트리
- 실제 DB 존은 sqlite 읽기 전용으로만 연다. 합성 존은 메모리에서만 만든다.
- 확인: (1) 날짜별 (text, direction, source, tier, evidence, ref) 판정 변화 0건
        (2) 존별 near_zone=True 날짜와 True/False 건수
사용법: backend 디렉토리에서  .venv/Scripts/python tests/regression/diff_near_zone.py
"""
import importlib.util
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "app" / "services"))

import candle_patterns as new_cp  # noqa: E402
import manual_lines  # noqa: E402
import pipeline  # noqa: E402

DB = REPO / "data" / "merged" / "manual_lines.db"


def load_head_candle_patterns():
    """HEAD의 candle_patterns.py는 HEAD의 signal_types.Signal(near_zone 없음)을 쓰므로 둘 다 임시 폴더에서 로드한다."""
    tmp = Path(tempfile.mkdtemp(prefix="cp_head_"))
    for name in ("candle_patterns.py", "signal_types.py"):
        src = subprocess.run(["git", "show", f"HEAD:backend/app/services/{name}"], capture_output=True, check=True,
                             cwd=REPO).stdout
        (tmp / name).write_bytes(src)
    saved = {k: sys.modules.pop(k) for k in ("candle_patterns", "signal_types") if k in sys.modules}
    sys.path.insert(0, str(tmp))
    try:
        spec = importlib.util.spec_from_file_location("candle_patterns", tmp / "candle_patterns.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["candle_patterns"] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(tmp))
        sys.modules.pop("candle_patterns", None)
        sys.modules.pop("signal_types", None)
        sys.modules.update(saved)
    return mod


def key(s):
    return (s.text, s.direction, s.source, s.tier, tuple(s.evidence), s.ref_id, s.ref_created_at)


def main():
    old_cp = load_head_candle_patterns()
    df, _, _ = pipeline.load_dashboard_data()
    df = df.reset_index(drop=True)
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    real = [dict(r) for r in conn.execute("SELECT * FROM lines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY id")]
    conn.close()
    zones = [ln for ln in real if ln["line_type"] == "zone"]
    synth = [{"id": 9100 + k, "line_type": "zone", "time1": t1, "price1": hi, "time2": t2, "price2": lo,
              "created_at": "2026-10-27T00:00:00+00:00"}
             for k, (t1, t2, hi, lo) in enumerate([("2026-09-01", "2026-09-10", 80500.0, 79000.0),
                                                   ("2025-06-01", "2025-06-20", 108000.0, 104000.0),
                                                   ("2024-03-01", "2024-04-10", 66000.0, 62000.0)])]
    print(f"캔들 {len(df)}개. 실제 존 {len(zones)}개 + 합성 존 {len(synth)}개 (실제 DB는 읽기 전용)\n")

    manual = manual_lines.compute_manual_line_signals(df, real) if real else {}
    before = old_cp.compute_candle_pattern_signals(df, manual)
    dates = df["open_time"].dt.strftime("%Y-%m-%d")

    changed_total = 0
    for label, zs in [("실제 존 전부", zones)] + [(f"존 id={z['id']} 단독", [z]) for z in zones + synth] + \
                     [("실제+합성 존 전부", zones + synth)]:
        after = new_cp.compute_candle_pattern_signals(df, manual, zones=zs)
        changed = [i for i in range(len(df)) if [key(s) for s in before[i]] != [key(s) for s in after[i]]]
        changed_total += len(changed)
        sigs = [s for v in after.values() for s in v]
        n_true = sum(1 for s in sigs if s.near_zone is True)
        n_false = sum(1 for s in sigs if s.near_zone is False)
        near_days = [dates.iloc[i] for i in range(len(df)) if any(s.near_zone for s in after[i])]
        print(f"[{label}] 판정 변화 {len(changed)}일 | 캔들 패턴 신호 {len(sigs)}건: near_zone True {n_true} / False {n_false}")
        if len(near_days) <= 12:
            print(f"    near_zone=True 날짜: {near_days}")
        else:
            print(f"    near_zone=True 날짜 {len(near_days)}일 (처음 {near_days[:3]} ... 마지막 {near_days[-3:]})")
    print(f"\n요약: 판정 변화 총 {changed_total}일 {'(OK, 0건)' if changed_total == 0 else '!!!'}")


if __name__ == "__main__":
    main()
