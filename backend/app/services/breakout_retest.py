"""마감 일봉에서 당시 알던 한 도형 버전의 돌파와 후속 시험을 연결한다."""
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import isfinite

from app.services import dashboard, rise_support

# 급락 실험의 8봉 추적 기한을 비교용으로 재사용한다. 발행봉+8까지 포함한다.
RETEST_WAIT_BARS = 8
CANDIDATE_DISPLAY_BARS = 8
LONG = "롱 후보 · 돌파 가격 지지 확인"
SHORT = "숏 후보 · 지지 재시험 실패"


@dataclass
class Attempt:
    start: int
    opening: dict
    above: bool
    reclaim: dict | None = None
    touch: dict | None = None
    candidate: dict | None = None
    issued: int | None = None
    in_zone: bool = False
    last_step: dict | None = None

    def latest(self):
        return self.last_step or self.opening

    def elapsed(self, index):
        return index - (self.issued if self.candidate else self.start)

    def expired(self, index):
        limit = CANDIDATE_DISPLAY_BARS if self.candidate else RETEST_WAIT_BARS
        return self.elapsed(index) > limit


class Close:
    """선택일의 봉·경계와 이미 발행한 근거만으로 사건을 기록한다."""

    def __init__(self, row, bar, version, bounds, market, canonical):
        self.row, self.bar, self.version = row, bar, version
        self.day = bar.open_time.date().isoformat()
        self.bottom, self.top = bounds
        self.shape = market["details"]["market"]["candle_shape"]
        volume = getattr(bar, "volume", None)
        self.volume = float(volume) if volume is not None and isfinite(volume) else None
        self.canonical = canonical

    def emit(self, kind, label, attempt=None, *, parents=(), source=None, ended=False,
             evidence=(), retest=False):
        day, v, lo, hi = self.day, self.version, self.bottom, self.top
        own_id = f"breakout:{v['key']}:{kind}:{day}"
        event_id = source["id"] if source else own_id
        step = dict(id=event_id, type=kind, label=label, date=day, bottom=lo, top=hi,
                    open=float(self.bar.open), high=float(self.bar.high),
                    low=float(self.bar.low), close=float(self.bar.close))
        steps = {}
        for ancestor in parents:
            # 다른 시도로 넘어갈 때는 직전 연결만 보존해 장기간 기록이 무한히 커지지 않게 한다.
            trail = ancestor["steps"]
            if not attempt:
                trail = [s for s in trail if s["id"] in (ancestor["attempt_id"], ancestor["id"])]
            steps.update((s["id"], s) for s in trail)
        linked = list(steps)
        steps[event_id] = step
        anchor = attempt.opening if attempt else None
        new_attempt = kind in ("breakout_up", "break_down")
        opening_step = anchor["steps"][-1] if anchor else None
        if new_attempt:
            opening_step = step
        touch = attempt.touch if attempt else None
        if kind == "long_candidate" or (retest and not touch):
            touch = dict(confirmed_date=day, bottom=lo, top=hi)
        elif attempt and attempt.candidate:
            original = attempt.candidate
            touch = dict(confirmed_date=original["retest_date"], bottom=original["retest_bottom"],
                         top=original["retest_top"])
        if kind == "breakdown_failed":
            touch = None
        item = dict(id=event_id, type=kind, label=label, drawing_id=v["support_id"],
                    version_id=v["key"], drawing_kind=v["kind"], confirmed_date=day,
                    attempt_id=opening_step["id"] if opening_step else None,
                    breakout_date=opening_step["date"] if opening_step else None,
                    breakout_bottom=opening_step["bottom"] if opening_step else None,
                    breakout_top=opening_step["top"] if opening_step else None,
                    retest_date=touch["confirmed_date"] if touch else None,
                    retest_bottom=touch["bottom"] if touch else None, retest_top=touch["top"] if touch else None,
                    linked_ids=linked, steps=list(steps.values()), bottom=lo, top=hi,
                    current_bottom=lo, current_top=hi, close=step["close"],
                    candle_shape=self.shape, volume=self.volume,
                    evidence=[*(source.get("evidence", []) if source else []), *evidence],
                    status="ended" if ended else "new", origin="rise_response" if source else "breakout_retest")
        self.row["events"].append(item)
        return item

    def show(self, attempt, index):
        active = [attempt.candidate or attempt.latest()]
        if active[0]["type"] == "long_exit":
            active = [attempt.opening]
        if attempt.candidate and attempt.in_zone and attempt.latest() is not attempt.candidate:
            active.append(attempt.latest())
        for original in active:
            self.row["active"].append(dict(original, status="new" if original["confirmed_date"] == self.day
                                           else "maintained", current_bottom=self.bottom, current_top=self.top,
                                           age_bars=attempt.elapsed(index) + 1))


def _bounds(version, bar):
    if version["kind"] == "trend":
        price = dashboard.manual_lines._trend_line_price(version["time1"], version["price1"],
                                                        version["time2"], version["price2"], bar.open_time)
        return float(price), float(price)
    return version["bottom"], version["top"]


def _above(attempt, today, index):
    """이전 마감에서 위로 넘어선 시도의 유지·주의·실패와 롱 후보를 판정한다."""
    bar, lo, hi = today.bar, today.bottom, today.top
    if bar.close < lo:
        last = attempt.latest()
        if attempt.candidate:
            last = today.emit("invalidated", "롱 후보 무효 · 반대 경계 종가 이탈", attempt,
                              parents=[last], ended=True, evidence=["종가 < 당일 하단"])
        kind, label = ("reclaim_failed", "회복 후 재이탈 관찰") if attempt.reclaim else ("breakout_failed", "상향 돌파 실패 관찰")
        failed = today.emit(kind, label, attempt, parents=[last],
                            evidence=["종가 < 당일 하단"])
        return None, failed
    if bar.close < hi:
        if not attempt.in_zone:
            attempt.last_step = today.emit("breakout_caution", "돌파 유지 주의", attempt,
                                           parents=[attempt.latest()], evidence=["하단 ≤ 종가 < 상단"])
        attempt.in_zone = True
    else:
        if not attempt.candidate and bar.low <= hi and bar.high >= lo:
            facts = [f"저가 {bar.low:g}~고가 {bar.high:g}가 당일 경계와 교차 · 종가 ≥ 상단"]
            if attempt.in_zone:
                facts.append("존 내부 복귀 이후 상단 이상 마감")
            attempt.candidate = today.emit("long_candidate", LONG, attempt, parents=[attempt.latest()],
                                           evidence=facts)
            attempt.issued = index
            attempt.last_step = attempt.candidate
        elif attempt.in_zone:
            attempt.last_step = today.emit("returned_above", "돌파 가격 상단 회복", attempt,
                                           parents=[attempt.latest()], evidence=["당일 종가 ≥ 상단"])
        attempt.in_zone = False
    return attempt, None


def _below(attempt, today, index, previous_close, previous_bottom):
    """수평선·존의 아래쪽 시험은 기존 사건을 투영하고, 추세선은 같은 가격 규칙을 적용한다."""
    bar, lo, hi = today.bar, today.bottom, today.top
    trend = today.version["kind"] == "trend"
    touch = today.canonical.get("support_retest_touch")
    if touch and touch["break_date"] != attempt.opening["confirmed_date"]:
        touch = None
    line_touch = trend and rise_support.touched_from_below(bar, previous_close, previous_bottom, lo)
    if not attempt.touch and (touch or line_touch):
        attempt.touch = today.emit("retest_below", "이탈 지지 아래쪽 재시험", attempt,
                                   parents=[attempt.latest()], source=touch, retest=True)
        attempt.last_step = attempt.touch
    if bar.close >= hi:
        parent = attempt.latest()
        if attempt.candidate:
            parent = today.emit("invalidated", "숏 후보 무효 · 지지 회복", attempt, parents=[parent],
                                source=today.canonical.get("support_reclaimed"), ended=True)
        recovery = today.canonical.get("support_reclaimed")
        if recovery and (attempt.candidate or recovery.get("related") not in parent["linked_ids"] + [parent["id"]]):
            recovery = None
        attempt.reclaim = today.emit("breakdown_failed", "하향 이탈 실패 관찰", attempt, parents=[parent], source=recovery,
                                     evidence=["이탈 이후 별도 마감봉에서 종가 ≥ 당일 상단"])
        attempt.last_step = attempt.reclaim
        # 회복일은 후속 롱 후보의 재시험일로 재사용하지 않는다.
        attempt.above = True
        attempt.candidate = attempt.touch = attempt.issued = None
        attempt.start = index
    elif attempt.touch and not attempt.candidate:
        short = today.canonical.get("support_retest_short")
        if short and (short["break_date"] != attempt.opening["confirmed_date"] or short["related"] != attempt.touch["id"]):
            short = None
        if short or (trend and rise_support.rejected_below(bar, previous_close, lo)):
            attempt.candidate = today.emit("short_candidate", SHORT, attempt, source=short,
                                           parents=[attempt.touch], evidence=["하단 아래 · 전일보다 낮은 종가"])
            attempt.issued = index
            attempt.last_step = attempt.candidate


def _version_days(rows, bars, dates, markets, version, sources):
    key = version["key"]
    first = version["known_from"]
    if version["kind"] == "trend":
        first = max(first, version["time1"], version["time2"])
    start = bisect_left(dates, first)
    stop = bisect_right(dates, version["through"])
    attempt = previous = None
    for i in range(start, stop):
        bar = bars[i]
        current = _bounds(version, bar)
        today = Close(rows[i], bar, version, current, markets[i], sources[i].get(key, {}))
        previous_close = bars[i-1].close if previous is not None else None
        up = previous is not None and previous_close <= previous[1] and bar.close > current[1]
        down = previous is not None and previous_close >= previous[0] and bar.close < current[0]
        if attempt and attempt.expired(i):
            label = "후보 표시 만료" if attempt.candidate else "재시험 대기 만료"
            today.emit("expired", label, attempt, parents=[attempt.latest()], ended=True)
            attempt = None
        failure = None
        if attempt:
            if attempt.above:
                attempt, failure = _above(attempt, today, i)
            else:
                _below(attempt, today, i, previous_close, previous[0])
        if not attempt and (up or down):
            kind, label = ("breakout_up", "상향 종가 돌파") if up else ("break_down", "하향 종가 이탈")
            opening = today.emit(kind, label, parents=[failure] if failure else [],
                                 evidence=[f"전일 종가 {previous_close:g} · 전일 경계 {previous[0]:g}~{previous[1]:g}",
                                           f"당일 종가 {bar.close:g} · 당일 경계 {current[0]:g}~{current[1]:g}"])
            attempt = Attempt(i, opening, up)
        if down:
            long_exit = today.canonical.get("trendline_exit_long") or today.canonical.get("support_break")
            if long_exit:
                exit_event = today.emit("long_exit", long_exit["label"], attempt, source=long_exit,
                                        parents=[attempt.opening] if attempt else [])
                if attempt and attempt.start == i:
                    attempt.last_step = exit_event
        if not up and not down:
            sweep = dashboard.zone_signals.sweep_direction(bar.open, bar.high, bar.low, bar.close,
                                                          current[1], current[0])
            if sweep:
                label = "저항 꼬리 스윕" if sweep == "short" else "지지 꼬리 스윕"
                wick = today.canonical.get("trendline_wick_recovery") if sweep == "long" else None
                today.emit("wick_sweep", label, attempt, parents=[attempt.opening] if attempt else [], source=wick,
                           evidence=["꼬리만 경계 통과 · 몸통은 복귀"])
        if attempt:
            today.show(attempt, i)
        previous = current
    if attempt and stop < len(bars):
        # 이 버전은 더 이상 유효하지 않다. 경계를 연장하거나 새 좌표와 섞지 않는다.
        today = Close(rows[stop], bars[stop], version, (None, None), markets[stop], {})
        replaced = version.get("end_reason") == "replaced"
        canonical_end = sources[stop].get(key, {}).get("support_candidate_ended") if attempt.candidate else None
        today.emit("version_replaced" if replaced else "version_ended",
                   "도형 버전 교체" if replaced else "도형 버전 종료",
                   attempt, parents=[attempt.latest()], source=canonical_end, ended=True)


def build_days(frame, versions, rise_days):
    """상승 실험과 같은 마감봉·도형 버전과 시장/수동 사건을 받아 일자별로 투영한다."""
    if len(frame) != len(rise_days):
        raise ValueError("마감봉과 상승 실험 일자 수가 다릅니다.")
    rows = [dict(events=[], active=[]) for _ in rise_days]
    if not versions:
        return rows
    bars = list(frame.itertuples(index=False))
    dates = [bar.open_time.date().isoformat() for bar in bars]
    sources = []
    for day in rise_days:
        by_version = {}
        for e in day["events"]:
            if e.get("version") and e.get("source") == "manual":
                by_version.setdefault(e["version"], {})[e["kind"]] = e
        sources.append(by_version)
    for version in versions:
        _version_days(rows, bars, dates, rise_days, version, sources)
    return rows
