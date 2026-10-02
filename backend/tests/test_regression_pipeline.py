"""
scripts/pipeline.py(원본)과 backend/app/services/pipeline.py(이식본)이 완전히
동일한 결과(캔들 수, OHLCV+EMA+RSI 수치, 날짜별 신호, 다이버전스 마커)를
만들어내는지 검증하는 회귀 테스트.

원본/이식본을 완전히 격리된 서브프로세스 2개로 각각 실행해서(이유는
regression/dump_pipeline_result.py 상단 docstring 참고) JSON으로 저장한 뒤
그 결과를 diff한다. 둘 다 저장소 루트의 같은 data/merged/*.parquet를 보므로
입력 데이터도 완전히 동일하다.

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


def _prime_shared_cache():
    """두 서브프로세스를 돌리기 전에 data/merged/*_dashboard.parquet 캐시를
    한 번 미리 채워둔다.

    이게 없으면(실제로 처음 겪은 문제): 캐시가 비어있을 때 원본/이식본 서브
    프로세스가 각각 독립적으로 Binance 실시간 API를 호출하는데, 그 시점에
    "오늘" 캔들이 아직 정산 중이면(장 마감 직후 짧은 기간 거래소 쪽 수치가
    미세 조정됨) 몇 초 간격으로 호출한 두 서브프로세스가 서로 다른 close/volume
    스냅샷을 받아서 실제로는 코드가 완전히 동일한데도 마지막 캔들 1건이 다르게
    나왔다.

    조사해보니 원인이 하나 더 있었다 - scripts/data_fetcher.py::ensure_fresh_data()의
    기존 버그(이식 대상 코드에 원래 있던 것, 이번에 발견): 캐시 파일이 아직 없을 때
    fetch_full_history()로 받아온 직후 "이미 최신"(latest_closed_open) 체크에 걸려
    early return 하는데, 그 return이 df.to_parquet() 저장 코드보다 먼저라서 캐시
    파일이 "한 번도" 디스크에 안 써진다. 그 결과 캐시가 영영 안 생기고, 호출할
    때마다 매번 Binance에서 2022년부터 전체를 다시 받아온다(이번 포팅과 무관한
    원본 버그 - 별도로 보고, 여기서 임의 수정하지 않음). 그래서 이 헬퍼가 받아온
    DataFrame을 직접 캐시 경로에 저장해 우회한다 - 이후 두 서브프로세스는 이미
    존재하는 캐시 파일을 읽고 "이미 최신"으로 판단해 재조회 없이 반환하므로,
    완전히 동일한(고정된) 데이터를 보게 된다.
    """
    proc = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, r'{SCRIPTS_DIR}'); "
            "from data_fetcher import ensure_fresh_data; import config; "
            "df = ensure_fresh_data(); "
            "config.DASHBOARD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True); "
            "df.to_parquet(config.DASHBOARD_CACHE_PATH, index=False)",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"캐시 프라이밍 실패\nstdout: {proc.stdout}\nstderr: {proc.stderr}"


@pytest.fixture(scope="module")
def original_and_ported_results():
    _prime_shared_cache()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    original_path = OUTPUT_DIR / "original.json"
    ported_path = OUTPUT_DIR / "ported.json"

    for source_dir, out_path in [(SCRIPTS_DIR, original_path), (SERVICES_DIR, ported_path)]:
        proc = subprocess.run(
            [sys.executable, str(DUMP_SCRIPT), str(source_dir), str(out_path)],
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
INTENDED_DELETED_PREFIXES = ("RSI 과매수", "다우이론 ")

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


def _build_expected_ported_signals(original):
    """원본 결과에 의도한 차이(위 docstring 1~3)만 적용해 기대 이식본 신호를 만든다."""
    candles = original["candles"]
    index_of = {c["date"]: i for i, c in enumerate(candles)}
    expected = {}
    for i, c in enumerate(candles):
        date = c["date"]
        sigs = [
            s for s in original["signals_by_date"].get(date, [])
            if not s["text"].startswith(INTENDED_DELETED_PREFIXES)
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


def test_divergence_markers_match_exactly(original_and_ported_results):
    original, ported = original_and_ported_results
    assert original["divergence_markers"] == ported["divergence_markers"]


def test_total_signal_and_marker_counts(original_and_ported_results):
    """콘솔에서 눈으로 확인할 수 있게 총계도 출력."""
    original, ported = original_and_ported_results
    orig_count = sum(len(v) for v in original["signals_by_date"].values())
    expected_count = sum(len(v) for v in _build_expected_ported_signals(original).values())
    port_count = sum(len(v) for v in ported["signals_by_date"].values())
    print(f"\n캔들 {original['candle_count']}개, 원본 신호 {orig_count}건 / 기대 이식본 {expected_count}건 / 이식본 신호 {port_count}건")
    print(f"다이버전스 마커: 원본 {len(original['divergence_markers'])}건 / 이식본 {len(ported['divergence_markers'])}건")
    assert expected_count == port_count
