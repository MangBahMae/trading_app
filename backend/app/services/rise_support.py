"""마감된 일봉에서 당시 유효했던 같은 수동 도형 버전의 이탈·재시험을 추적한다."""
from bisect import bisect_left, bisect_right

from app.services import dashboard


def _event(day, version, kind, label, *evidence, related=None):
    return dict(id=f"rise:{version['key']}:{kind}:{day}", kind=kind, label=label, date=day,
                version=version["key"], support_id=version["support_id"],
                evidence=list(evidence), related=related)


def _trend_days(rows, bars, dates, version, start, stop):
    """두 좌표 일자와 관찰 시점이 지난 뒤 같은 버전의 직전 종가가 선 위였는지 본다."""
    if version["price2"] <= version["price1"]:
        return
    coords = (version["time1"], version["price1"], version["time2"], version["price2"])
    previous_level = None
    previous_wick = False
    for i in range(start, stop):
        bar, day = bars[i], dates[i]
        level = float(dashboard.manual_lines._trend_line_price(*coords, bar.open_time))
        before = previous_level is not None and bars[i - 1].close >= previous_level
        wick = before and bar.low < level <= min(bar.open, bar.close)
        state = "선 위 마감" if bar.close >= level else "선 아래 마감"
        events = rows[i]["events"]
        if before and bar.close < level:
            state = "종가 이탈"
            events.append(_event(day, version, "trendline_exit_long", "기존 롱 종료 검토 · 상승 추세선 이탈",
                                 f"전일 종가 {bars[i - 1].close:g} ≥ 전일 선 {previous_level:g}",
                                 f"오늘 종가 {bar.close:g} < 오늘 선 {level:g}"))
        elif wick:
            state = "꼬리 이탈 후 회복"
            if not previous_wick:
                events.append(_event(day, version, "trendline_wick_recovery", "추세선 꼬리 이탈 후 회복",
                                     f"저가 {bar.low:g} < 선 {level:g} ≤ 종가 {bar.close:g}"))
        details = rows[i]["details"]
        details["trendline_status"] = "우상향 추세선 확인"
        details["levels"].append(dict(kind="trend", version=version["key"], price=level, state=state,
                                      time1=coords[0], price1=coords[1], time2=coords[2], price2=coords[3]))
        previous_level, previous_wick = level, wick


def _level_days(rows, bars, dates, version, start, stop):
    bottom, top = version["bottom"], version["top"]
    bounds = f"종가 이탈 < 하단 {bottom:g} · 아래쪽 재시험은 고가 ≥ 하단 · 종가 회복 ≥ 상단 {top:g}"
    broken = touched = candidate = None
    for i in range(start, stop):
        bar, day = bars[i], dates[i]
        # 버전이 갱신된 당일의 전일 종가는 그 새 지지를 사전에 알았다는 증거가 아니다.
        previous_close = bars[i - 1].close if i > start else None
        events = rows[i]["events"]
        if broken is None:
            if previous_close is not None and previous_close >= bottom and bar.close < bottom:
                broken = _event(day, version, "support_break", "수동 지지 종가 이탈", bounds,
                                f"전일 종가 {previous_close:g} · 오늘 종가 {bar.close:g}")
                events.append(broken)
        else:
            if touched is None and previous_close < bottom and bar.open <= bottom <= bar.high:
                touched = _event(day, version, "support_retest_touch", "이탈 지지 아래쪽 재시험", bounds,
                                 f"이탈일 {broken['date']} · 오늘 시가 {bar.open:g}, 고가 {bar.high:g}",
                                 related=broken["id"])
                events.append(touched)
            if bar.close >= top:
                events.append(_event(day, version, "support_reclaimed", "이탈 지지 종가 회복", bounds,
                                     f"종가 {bar.close:g}", related=(candidate or touched or broken)["id"]))
                broken = touched = candidate = None
            elif touched and not candidate and bar.close < bottom and bar.close < previous_close:
                candidate = _event(day, version, "support_retest_short", "숏 후보 · 지지 재시험 실패",
                                   bounds, f"이탈일 {broken['date']} · 재시험일 {touched['date']}",
                                   f"종가 {bar.close:g} < 전일 종가 {previous_close:g}, 하단 아래 재하락",
                                   related=touched["id"])
                events.append(candidate)
        if candidate:
            state = "재시험 실패 후보 추적"
            rows[i]["active_short_ids"].append(candidate["id"])
        elif touched:
            state = "재시험 후 마감 확인 중"
        elif broken:
            state = "종가 이탈 · 재시험 미확인"
        else:
            state = "지지 기준 확인"
        details = rows[i]["details"]
        details["support_status"] = "수동 지지 확인"
        details["levels"].append(dict(kind=version["kind"], version=version["key"],
                                      bottom=bottom, top=top, state=state, rule=bounds))


def support_days(df, versions):
    """마감 UTC 일봉 오름차순 입력. 날짜를 선택하면 그날까지 발행한 사건만 남는다."""
    bars = list(df.itertuples(index=False))
    dates = [bar.open_time.date().isoformat() for bar in bars]
    rows = [dict(events=[], active_short_ids=[], details=dict(
        trendline_status="추세선 미확인", support_status="수동 지지 미확인", levels=[])) for _ in dates]
    for version in versions:
        start = bisect_left(dates, version["known_from"])
        stop = bisect_right(dates, version["through"])
        if version["kind"] == "trend":
            _trend_days(rows, bars, dates, version, start, stop)
        elif version["kind"] in ("zone", "horizontal"):
            _level_days(rows, bars, dates, version, start, stop)
    return rows
