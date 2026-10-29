"""
scripts/pipeline.py(원본)과 backend/app/services/pipeline.py(이식본)이 완전히
동일한 결과(캔들 수, OHLCV+EMA+RSI 수치, 날짜별 신호, 다이버전스 마커)를
만들어내는지 검증하는 회귀 테스트.

원본/이식본을 완전히 격리된 서브프로세스 2개로 각각 실행해서(이유는
regression/dump_pipeline_result.py 상단 docstring 참고) JSON으로 저장한 뒤
그 결과를 diff한다. 둘 다 저장소의 같은 고정 일봉 CSV(tests/fixtures)를 보므로
입력 데이터도 완전히 동일하다(네트워크/캐시 불필요).

[의도한 차이 - 기능1 개편 2a단계]
이식본(backend/app/services)은 개편으로 원본(scripts/)과 아래 세 가지만 의도적으로
다르다. 그 외 차이는 전부 실패로 본다. scripts/는 건드리지 않으므로 원본 결과가
기준선이고, 아래 규칙으로 "기대 이식본"을 만들어 이식본과 정확히 비교한다.
 1. RSI 과매수(reference) 신호 삭제  - 텍스트가 "RSI 과매수"로 시작하는 신호
 2. 다우이론 라벨(reference) 신호 삭제 - 텍스트가 "다우이론 "으로 시작하는 신호
 3. EMA50/200 터치/거부(|이격률|<=0.1%)의 방향 기준이 캔들 색 -> 시가 위치로 변경
    (시가>EMA = 지지/long, 시가<EMA = 저항/short, 같으면 전날 종가 쪽, 그것도 같거나
    전날이 없으면 무신호). 원본 신호를 믿지 않고, 덤프에 들어 있는 시가/고가/저가/
    종가/EMA로 테스트가 독립적으로 다시 계산한 값을 기대값으로 쓴다. 터치/거부
    판정 자체(꼬리 포함 접촉 + 이격률 0.1% 이내)와 돌파/회색지대는 그대로여야 한다.
 4. RSI 과매도 신호 비활성화 (feature_flags.ENABLE_RSI_OVERSOLD_SIGNAL=False) - "RSI 과매도"로 시작
 5. RSI 다이버전스 마커 비활성화 (feature_flags.ENABLE_DIVERGENCE_MARKERS=False) - 마커 목록이 []
    (4, 5는 코드를 지운 게 아니라 플래그로 끈 것이라, 플래그를 켠 이식본이 1~3만 적용한 기대값과
    정확히 같은지도 아래 "플래그 복원" 테스트로 확인한다)
수동선(manual_lines)과 캔들패턴은 이 덤프에 포함되지 않는다 - 시가 기준 방향은
test_direction_by_open.py가 따로 검증한다.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SERVICES_DIR = REPO_ROOT / "backend" / "app" / "services"
DUMP_SCRIPT = Path(__file__).resolve().parent / "regression" / "dump_pipeline_result.py"
OUTPUT_DIR = Path(__file__).resolve().parent / "regression" / "_output"


# 원본(scripts/)과 이식본이 보는 일봉은 저장소의 고정 CSV(tests/fixtures)다 - dump_pipeline_result.py의 --daily-fixture가
# data_fetcher.ensure_fresh_data를 이 CSV로 바꾼다. 그래서 캐시 parquet이나 Binance가 없어도 되고(오프라인 통과),
# 두 서브프로세스가 서로 다른 시점의 실시간 스냅샷을 받아 마지막 캔들이 다르게 나오던 문제(예전 _prime_shared_cache가 우회하던 것)도 없다.
DAILY_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "BTCUSDT_1d_2022-01-01_2026-10-28.csv"


@pytest.fixture(scope="module")
def original_and_ported_results():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    original_path = OUTPUT_DIR / "original.json"
    ported_path = OUTPUT_DIR / "ported.json"

    for source_dir, out_path in [(SCRIPTS_DIR, original_path), (SERVICES_DIR, ported_path)]:
        proc = subprocess.run(
            [sys.executable, str(DUMP_SCRIPT), str(source_dir), str(out_path), "--daily-fixture", str(DAILY_FIXTURE)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 0, (
            f"{source_dir} 덤프 실패\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    with open(original_path, encoding="utf-8") as f:
        original = json.load(f)
    with open(ported_path, encoding="utf-8") as f:
        ported = json.load(f)

    return original, ported


@pytest.fixture(scope="module")
def ported_flags_on():
    """이식본을 feature_flags 전부 True로 켠 채 돌린 결과(플래그 복원 확인용)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "ported_flags_on.json"
    proc = subprocess.run(
        [sys.executable, str(DUMP_SCRIPT), str(SERVICES_DIR), str(out_path), "--flags-on", "--daily-fixture", str(DAILY_FIXTURE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, (
        f"flags-on 덤프 실패 | stdout: {proc.stdout} | stderr: {proc.stderr}"
    )
    with open(out_path, encoding="utf-8") as f:
        return json.load(f)


def test_candle_count_and_range_match(original_and_ported_results):
    original, ported = original_and_ported_results
    assert original["candle_count"] == ported["candle_count"]
    assert original["first_date"] == ported["first_date"]
    assert original["last_date"] == ported["last_date"]


def test_candle_numeric_series_match_exactly(original_and_ported_results):
    original, ported = original_and_ported_results
    mismatches = []
    for o, p in zip(original["candles"], ported["candles"]):
        if o != p:
            mismatches.append((o["date"], o, p))
    assert not mismatches, f"{len(mismatches)}개 날짜에서 OHLCV/EMA/RSI 불일치: {mismatches[:5]}"


TOUCH_MAX_PCT = 0.1  # sr_touch.py의 touch_reject 상한(이격률 %) - 독립 검증용으로 별도 정의
TOUCH_REJECT_TEXT = re.compile(r"^(EMA50|EMA200) (지지|저항 \(거부\))$")
# 코드에서 삭제한 것(복원하지 않기로 결정) - 플래그를 켜도 안 나온다.
DELETED_PREFIXES = ("RSI 과매수", "다우이론 ")
# 플래그로 끈 것 - 플래그를 켜면 원본과 똑같이 나와야 한다.
FLAGGED_OFF_PREFIXES = ("RSI 과매도",)
INTENDED_DELETED_PREFIXES = DELETED_PREFIXES + FLAGGED_OFF_PREFIXES

# pipeline.build_signals_by_date가 하루 안에서 신호를 쌓는 순서(앞에서부터).
_ORDER = [
    ("매물소진", 0), ("장악형 하락", 1), ("정배열", 2), ("⚠ 오늘 EMA 이탈", 2),
    ("역배열", 3), ("EMA50 ", 4), ("EMA200 ", 5), ("RSI 과매도", 6),
]


def _rank(text):
    for prefix, rank in _ORDER:
        if text.startswith(prefix):
            return rank
    raise AssertionError(f"순서를 모르는 신호 텍스트(테스트 갱신 필요): {text!r}")


def _expected_touch_reject(candles, i, ma_col):
    """i번째 캔들의 ma_col(EMA50/EMA200) 터치/거부 신호를 시가 기준으로 독립 계산.
    터치/거부가 아니거나 방향을 못 정하면 None."""
    c = candles[i]
    ma = c[ma_col]
    if ma is None or not (c["low"] <= ma <= c["high"]):
        return None
    if abs((c["close"] - ma) / ma * 100) > TOUCH_MAX_PCT:
        return None
    if c["open"] > ma:
        long = True
    elif c["open"] < ma:
        long = False
    elif i > 0 and candles[i - 1]["close"] != ma:
        long = candles[i - 1]["close"] > ma
    else:
        return None
    if long:
        return {"text": f"{ma_col} 지지", "direction": "long"}
    return {"text": f"{ma_col} 저항 (거부)", "direction": "short"}


def _build_expected_ported_signals(original, deleted_prefixes=INTENDED_DELETED_PREFIXES):
    """원본 결과에 의도한 차이(위 docstring)만 적용해 기대 이식본 신호를 만든다.
    deleted_prefixes: 지울 신호 텍스트 접두어(기본: 삭제 + 플래그로 끈 것 전부)."""
    candles = original["candles"]
    index_of = {c["date"]: i for i, c in enumerate(candles)}
    expected = {}
    for i, c in enumerate(candles):
        date = c["date"]
        sigs = [
            s for s in original["signals_by_date"].get(date, [])
            if not s["text"].startswith(deleted_prefixes)
        ]
        for ma_col in ("EMA50", "EMA200"):
            new = _expected_touch_reject(candles, i, ma_col)
            pos = next(
                (k for k, s in enumerate(sigs)
                 if TOUCH_REJECT_TEXT.match(s["text"]) and s["text"].startswith(ma_col + " ")),
                None,
            )
            if pos is not None:
                if new is None:
                    sigs.pop(pos)
                else:
                    sigs[pos] = new
            elif new is not None:
                at = next((k for k, s in enumerate(sigs) if _rank(s["text"]) > _rank(new["text"])), len(sigs))
                sigs.insert(at, new)
        if sigs:
            expected[date] = sigs
    assert index_of  # 빈 덤프 방지
    return expected


def test_signals_match_expected_after_intended_changes(original_and_ported_results):
    original, ported = original_and_ported_results
    expected_signals = _build_expected_ported_signals(original)
    port_signals = ported["signals_by_date"]

    assert set(expected_signals.keys()) == set(port_signals.keys()), (
        f"신호가 있는 날짜 집합이 다름 - 기대에만: "
        f"{set(expected_signals) - set(port_signals)}, 이식본에만: {set(port_signals) - set(expected_signals)}"
    )

    mismatches = []
    for date in sorted(expected_signals.keys()):
        if expected_signals[date] != port_signals[date]:
            mismatches.append((date, expected_signals[date], port_signals[date]))

    assert not mismatches, f"{len(mismatches)}개 날짜에서 의도하지 않은 신호 불일치: {mismatches[:5]}"


def test_intended_deletions_actually_happened(original_and_ported_results):
    """삭제 대상이 원본엔 있었고 이식본엔 하나도 없어야 한다(삭제가 안 먹힌 경우 방지)."""
    original, ported = original_and_ported_results

    def count(result, prefix):
        return sum(1 for v in result["signals_by_date"].values() for s in v if s["text"].startswith(prefix))

    for prefix in INTENDED_DELETED_PREFIXES:
        assert count(original, prefix) > 0, f"원본에 {prefix!r} 신호가 없음 - 테스트 전제 확인 필요"
        assert count(ported, prefix) == 0, f"이식본에 {prefix!r} 신호가 남아 있음"


def test_divergence_markers_are_disabled_by_flag(original_and_ported_results):
    original, ported = original_and_ported_results
    assert len(original["divergence_markers"]) > 0, "원본에 마커가 없음 - 테스트 전제 확인 필요"
    assert ported["divergence_markers"] == []


def test_flags_on_restores_original_signals_and_markers(original_and_ported_results, ported_flags_on):
    """플래그(RSI 과매도, 다이버전스)를 켜면 꺼두기 전 결과가 그대로 돌아온다 - 영구 삭제분(과매수/
    다우)과 시가 기준 방향 변경만 원본과 다르고, 그 외 신호/마커 차이는 0건이어야 한다."""
    original, _ = original_and_ported_results
    expected = _build_expected_ported_signals(original, DELETED_PREFIXES)
    got = ported_flags_on["signals_by_date"]

    assert set(expected) == set(got)
    mismatches = [(d, expected[d], got[d]) for d in sorted(expected) if expected[d] != got[d]]
    assert not mismatches, f"{len(mismatches)}개 날짜에서 플래그 복원 불일치: {mismatches[:5]}"

    assert ported_flags_on["divergence_markers"] == original["divergence_markers"]
    assert ported_flags_on["candles"] == original["candles"]

    def count(result, prefix):
        return sum(1 for v in result["signals_by_date"].values() for s in v if s["text"].startswith(prefix))

    assert count(ported_flags_on, "RSI 과매도") == count(original, "RSI 과매도") > 0


def test_total_signal_and_marker_counts(original_and_ported_results):
    """콘솔에서 눈으로 확인할 수 있게 총계도 출력."""
    original, ported = original_and_ported_results
    orig_count = sum(len(v) for v in original["signals_by_date"].values())
    expected_count = sum(len(v) for v in _build_expected_ported_signals(original).values())
    port_count = sum(len(v) for v in ported["signals_by_date"].values())
    print(f"\n캔들 {original['candle_count']}개, 원본 신호 {orig_count}건 / 기대 이식본 {expected_count}건 / 이식본 신호 {port_count}건")
    print(f"다이버전스 마커: 원본 {len(original['divergence_markers'])}건 / 이식본 {len(ported['divergence_markers'])}건")
    assert expected_count == port_count
