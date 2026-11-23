"""마감된 일봉에서 당시 유효했던 같은 수동 도형 버전의 이탈·재시험을 추적한다."""
from bisect import bisect_left, bisect_right

from app.services import dashboard


def _event(day, version, kind, label, *evidence, related=None, **facts):
    return dict(id=f"rise:{version['key']}:{kind}:{day}", kind=kind, label=label, date=day,
                version=version["key"], support_id=version["support_id"],
                source=version.get("source", "manual"), evidence=list(evidence), related=related, **facts)


def _active(row, event, age):
    item = {key: event[key] for key in ("id", "kind", "date", "source", "version", "price")}
    row["details"]["active_shorts"].append(dict(item, duration_bars=age))
    ids = "active_short_ids" if event["kind"] == "support_retest_short" else "active_resistance_ids"
    row[ids].append(event["id"])


def _end(day, version, kind, label, original, age, state, *evidence, **facts):
    return _event(day, version, kind, label, *evidence, related=original["id"], price=original["price"],
                  lifecycle=state, started_on=original["date"], duration_bars=age, **facts)


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
                                 f"오늘 종가 {bar.close:g} < 오늘 선 {level:g}", price=level))
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


def touched_from_below(bar, previous_close, previous_bottom, bottom):
    """전일 아래 마감 뒤 오늘 하단을 아래쪽에서 시험했는지 확인한다."""
    return previous_close < previous_bottom and bar.open <= bottom <= bar.high


def rejected_below(bar, previous_close, bottom):
    """접촉 뒤 회복 대신 하단 아래에서 전일보다 낮게 마감했는지 확인한다."""
    return bar.close < bottom and bar.close < previous_close


def _level_days(rows, bars, dates, version, start, stop, superseded=None):
    bottom, top = version["bottom"], version["top"]
    manual = version["kind"] != "swing_low"
    name = "수동 지지" if manual else "확인된 상승 저점"
    bounds = f"종가 이탈 < 하단 {bottom:g} · 아래쪽 재시험은 고가 ≥ 하단 · 종가 회복 ≥ 상단 {top:g}"
    broken = touched = candidate = None
    issued = None
    for i in range(start, stop):
        if superseded is not None and i >= superseded and broken is None:
            break  # 교체 전 이미 이탈한 기준은 회복될 때까지 같은 가격을 계속 추적한다.
        bar, day = bars[i], dates[i]
        # 버전이 갱신된 당일의 전일 종가는 그 새 지지를 사전에 알았다는 증거가 아니다.
        previous_close = bars[i - 1].close if i > start else None
        events = rows[i]["events"]
        if broken is None:
            if previous_close is not None and previous_close >= bottom and bar.close < bottom:
                broken = _event(day, version, "support_break", f"기존 롱 종료 검토 · {name} 이탈", bounds,
                                f"전일 종가 {previous_close:g} · 오늘 종가 {bar.close:g}", price=bottom,
                                pivot_date=version.get("pivot_date"), confirmed_on=version.get("confirmed_on"))
                events.append(broken)
        else:
            if touched is None and touched_from_below(bar, previous_close, bottom, bottom):
                touched = _event(day, version, "support_retest_touch", "이탈 지지 아래쪽 재시험", bounds,
                                 f"이탈일 {broken['date']} · 오늘 시가 {bar.open:g}, 고가 {bar.high:g}",
                                 related=broken["id"], price=bottom, break_date=broken["date"])
                events.append(touched)
            if bar.close >= top:
                if candidate:
                    events.append(_end(day, version, "support_reclaimed", "숏 후보 무효 · 지지 회복",
                                       candidate, i - issued + 1, "invalidated", bounds, f"종가 {bar.close:g}"))
                else:
                    events.append(_event(day, version, "support_reclaimed", "이탈 지지 종가 회복", bounds,
                                         f"종가 {bar.close:g}", related=(touched or broken)["id"], price=top))
                broken = touched = candidate = None
            elif touched and not candidate and rejected_below(bar, previous_close, bottom):
                candidate = _event(day, version, "support_retest_short", "숏 후보 · 지지 재시험 실패",
                                   bounds, f"이탈일 {broken['date']} · 재시험일 {touched['date']}",
                                   f"종가 {bar.close:g} < 전일 종가 {previous_close:g}, 하단 아래 재하락",
                                   related=touched["id"], price=bottom, lifecycle="new",
                                   break_date=broken["date"], touch_date=touched["date"], confirmation_close=bar.close)
                issued = i
                events.append(candidate)
        if candidate:
            state = "재시험 실패 후보 추적"
            _active(rows[i], candidate, i - issued + 1)
        elif touched:
            state = "재시험 후 마감 확인 중"
        elif broken:
            state = "종가 이탈 · 재시험 미확인"
        else:
            state = "지지 기준 확인"
        details = rows[i]["details"]
        if manual:
            details["support_status"] = "수동 지지 확인"
        details["levels"].append(dict(kind=version["kind"], version=version["key"],
                                      bottom=bottom, top=top, state=state, rule=bounds,
                                      pivot_date=version.get("pivot_date"), confirmed_on=version.get("confirmed_on")))
    if candidate and stop < len(bars):
        rows[stop]["events"].append(_end(dates[stop], version, "support_candidate_ended", "숏 후보 무효 · 지지 버전 종료",
                                         candidate, stop - issued + 1, "invalidated"))


def _swing_supports(rows, bars, dates, market_rows):
    """직전 확인 저점보다 높은 최신 저점을 주 지지로 선정한다. 확인일 종가부터 알 수 있다."""
    points = []
    for i, row in enumerate(market_rows):
        lows = row["details"]["swing_lows"]
        if len(lows) < 2:
            continue
        prev, last = lows[-2:]
        if last["confirmed_on"] != dates[i] or last["price"] <= prev["price"]:
            continue
        key = "swing-low:" + last["date"] + ":" + dates[i]
        points.append((i, dict(key=key, support_id=key, kind="swing_low", source="swing_low",
                               bottom=last["price"], top=last["price"], pivot_date=last["date"],
                               confirmed_on=dates[i])))
    for j, (start, version) in enumerate(points):
        next_start = points[j + 1][0] + 1 if j + 1 < len(points) else None
        _level_days(rows, bars, dates, version, start, len(bars), superseded=next_start)


def _resistance(rows, bars, dates, version, start, stop, ema=None):
    """접촉 당시 근거를 보존하고, EMA 회복은 해당 EMA의 당일 종가 기준으로 판정한다."""
    source = version.get("source", "manual")
    name = "수동 저항" if source == "manual" else source
    touch = watch = None
    issued = None
    for i in range(max(start + 1, 2), stop):
        bar, day = bars[i], dates[i]
        previous = bars[i - 1]
        bottom = ema[i] if ema is not None else version["bottom"]
        top = bottom if ema is not None else version["top"]
        prior = ema[i - 1] if ema is not None else bottom
        if bottom is None or prior is None:
            continue
        events = rows[i]["events"]
        if touch is None:
            # 실제 반등(선행 상승 종가), 아래에서 출발한 접촉을 각각 확인한다.
            if not (bars[i - 2].close < previous.close < prior and bar.open <= bottom
                    and bar.low <= bottom <= bar.high and bar.high > previous.close):
                continue
            touch = _event(day, version, "resistance_touch", f"{name} 아래쪽 접촉",
                           f"선행 종가 반등 {bars[i - 2].close:g} → {previous.close:g}",
                           f"접촉 범위 {bottom:g}~{top:g}, 접촉봉 저가 {bar.low:g}",
                           price=bottom, top=top, touch_date=day, touch_low=bar.low)
            events.append(touch)
        touch_day, floor, ceiling = touch["date"], touch["price"], touch["top"]
        today_level = f"당일 {name} {top:g}" if ema is not None else f"상단 {top:g}"
        contact = dict(touch_date=touch_day, touch_low=touch["touch_low"], touch_price=floor,
                       current_price=bottom, confirmation_close=bar.close)
        state = "거부 관찰 유지" if watch else "접촉 후 거부 미확인"
        if bar.close > top:
            if watch:
                events.append(_end(day, version, "resistance_watch_released", f"숏 관찰 해제 · {name} 돌파",
                                   watch, i - issued + 1, "released", f"종가 {bar.close:g} > {today_level}",
                                   f"첫 접촉 {touch_day} · 당시 하단 {floor:g} · 저가 {touch['touch_low']:g}", **contact))
            else:
                events.append(_event(day, version, "resistance_broken", f"{name} 상방 돌파",
                                     f"종가 {bar.close:g} > {today_level}", related=touch["id"], price=top, **contact))
            state = "상방 돌파"
        elif not watch and day != touch_day and bar.close < min(touch["touch_low"], floor, bottom):
            watch = _event(day, version, "resistance_rejected", f"숏 관찰 · {name} 거부",
                           f"{touch_day} 접촉봉 저가 {touch['touch_low']:g} 및 접촉 당시 하단 {floor:g} 아래 마감",
                           f"오늘 종가 {bar.close:g} < 당일 하단 {bottom:g}",
                           related=touch["id"], price=floor, confirmation_below=touch["touch_low"],
                           lifecycle="new", **contact)
            events.append(watch)
            issued = i
            state = "종가 거부 확인"
        rule = ("종가 < 접촉봉 저가·접촉 당시 EMA·당일 EMA이면 거부, 종가 > 당일 EMA이면 돌파"
                if ema is not None else "종가 < 접촉봉 저가 및 하단이면 거부, 종가 > 상단이면 돌파")
        rows[i]["details"]["levels"].append(dict(kind="resistance", version=version["key"],
            source=source, price=floor, bottom=floor, top=ceiling, state=state, current_price=bottom,
            touch_date=touch_day, touch_low=touch["touch_low"], rule=rule))
        if bar.close > top:
            touch = watch = None
        elif watch:
            _active(rows[i], watch, i - issued + 1)
    if watch and stop < len(bars):
        rows[stop]["events"].append(_end(dates[stop], version, "resistance_watch_ended", "숏 관찰 무효 · 저항 버전 종료",
                                         watch, stop - issued + 1, "invalidated"))


def support_days(df, versions, market_rows=None):
    """마감 UTC 일봉 오름차순 입력. 날짜를 선택하면 그날까지 발행한 사건만 남는다."""
    bars = list(df.itertuples(index=False))
    dates = [bar.open_time.date().isoformat() for bar in bars]
    rows = [dict(events=[], active_short_ids=[], active_resistance_ids=[], details=dict(
        trendline_status="추세선 미확인", support_status="수동 지지 미확인", levels=[], active_shorts=[])) for _ in dates]
    for version in versions:
        start = bisect_left(dates, version["known_from"])
        stop = bisect_right(dates, version["through"])
        if version["kind"] == "trend":
            _trend_days(rows, bars, dates, version, start, stop)
        elif version["kind"] in ("zone", "horizontal"):
            _level_days(rows, bars, dates, version, start, stop)
            _resistance(rows, bars, dates, version, start, stop)
    if market_rows is not None:
        _swing_supports(rows, bars, dates, market_rows)
        for name in ("EMA50", "EMA200"):
            prices = [row["details"][name.lower()] for row in market_rows]
            _resistance(rows, bars, dates, dict(key=name, support_id=name, source=name), 0, len(bars), ema=prices)
    return rows
