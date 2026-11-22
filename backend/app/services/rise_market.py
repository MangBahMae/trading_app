"""마감된 BTCUSDT 일봉의 상승 국면과 고점 재시도. 날짜는 모두 UTC 봉 시작일이다."""
from dataclasses import dataclass
from datetime import timedelta
from math import isfinite

from app.services import swing_points

from app.services import dashboard

patterns = dashboard.candle_patterns
expansion = patterns.volatility_expansion

# 실험 기본값. 고정 일봉 성과에 맞춰 추정한 값이 아니다.
SIDEWAYS_BARS = 3
MIN_OVERLAP = 0.50
HIGH_BAND = 0.02
MAX_HIGH_ADVANCE = 0.01
PULLBACK = 0.02
RETRACE = 0.50
SIMILAR_HIGH = 0.01

NORMAL = '일반'
RISING = '상승 추세 유지'
SIDEWAYS = '상승 둔화 · 고점 횡보'
DIPPING = '상승 구간 · 눌림'


def _event(kind, label, day, **facts):
    return dict(id=f'rise:{kind}:{day}', kind=kind, label=label, date=day, **facts)


@dataclass
class PeakAttempt:
    first: int
    dip: int | None = None
    retry: int | None = None

    def advance(self, i, days, highs, lows, closes):
        """종가로 눌림, 뒤의 별도 봉에서 반등, 그 이후 봉의 밀림을 차례로 확인."""
        first_high = highs[self.first]
        if self.dip is None:
            if highs[i] > first_high:
                self.first = i
            elif i > self.first and highs[i] < first_high and closes[i] <= first_high * (1 - PULLBACK):
                self.dip = i
            return None

        if highs[i] > first_high * (1 + SIMILAR_HIGH):
            # 허용 폭을 넘은 새 고점은 비슷하거나 낮은 고점으로 분류하지 않는다.
            self.first, self.dip, self.retry = i, None, None
            return None

        if self.retry is None:
            rebound_price = closes[self.dip] + RETRACE * (first_high - closes[self.dip])
            if highs[i] >= rebound_price and highs[i] > highs[i - 1] and closes[i] > closes[i - 1]:
                self.retry = i
            elif closes[i] < closes[self.dip]:
                self.dip = i
            return None

        if highs[i] > highs[self.retry]:
            self.retry = i
            return None
        if closes[i] >= lows[self.retry]:
            return None
        second_high = highs[self.retry]
        return _event('high_retry_failed', '숏 관찰 · 고점 재시도 실패', days[i],
                      first_peak_day=days[self.first], first_peak=first_high,
                      pullback_day=days[self.dip], pullback_close=closes[self.dip],
                      retry_day=days[self.retry], retry_peak=second_high,
                      peak_relation='비슷한 고점' if second_high >= first_high * (1 - SIMILAR_HIGH) else '낮은 고점',
                      confirmation_below=lows[self.retry], confirmation_close=closes[i],
                      watch_breakout=first_high * (1 + SIMILAR_HIGH))


def _sideways(i, start, peak_history, highs, lows, closes):
    """상승 구간 시작 후의 3봉을 검사한다. 구간 시작 봉은 겹침 창에서 제외한다."""
    if i - start < SIDEWAYS_BARS:
        return False, None, None
    window = slice(i - SIDEWAYS_BARS + 1, i + 1)
    prior_peak = peak_history[i - SIDEWAYS_BARS]
    hs, ls = highs[window], lows[window]
    narrowest = min(h - l for h, l in zip(hs, ls))
    if narrowest == 0:
        return False, None, None
    overlap = max(0.0, min(hs) - max(ls)) / narrowest
    advance = max(0.0, max(hs) / prior_peak - 1.0)
    near_peak = min(closes[window]) >= prior_peak * (1 - HIGH_BAND)
    return near_peak and overlap >= MIN_OVERLAP and advance <= MAX_HIGH_ADVANCE, overlap, advance * 100


def _advance_swings(i, swings, flags, days, highs, lows):
    # 계산 결과는 중심 봉에 붙어 있다. 우측 2개 봉이 마감된 오늘 처음 읽는다.
    center = i - swing_points.N
    if center < swing_points.N:
        return
    high, low = flags[center]
    if high == low:  # 일봉 하나가 고점·저점 모두이면 두 가격의 선후를 모른다.
        return
    kind, price = ('high', highs[center]) if high else ('low', lows[center])
    point = dict(kind=kind, price=price, date=days[center], confirmed_on=days[i])
    if swings and swings[-1]['kind'] == kind:
        previous = swings[-1]['price']
        if (high and price > previous) or (low and price < previous):
            swings[-1] = point
    else:
        swings.append(point)
        if len(swings) > 4:
            swings.pop(0)


def _price_direction(highs, lows):
    if len(highs) < 2 or len(lows) < 2:
        return 'unknown'
    high_move = highs[-1]['price'] - highs[-2]['price']
    low_move = lows[-1]['price'] - lows[-2]['price']
    if high_move > 0 and low_move > 0:
        return 'up'
    if high_move < 0 and low_move < 0:
        return 'down'
    return 'mixed'


def _market_label(regime, direction, phase, weaker_high):
    if regime is None:
        label = '배열 미확인'
    elif regime == 'bullish':
        label = '롱 우세 · 정배열 유지'
        if weaker_high:
            label += ' · 고점 갱신 둔화'
        if direction == 'down':
            label += ' · 가격 하락 구조'
    elif regime == 'bearish':
        label = '역배열 속 반등' if direction == 'up' else '하락 우세 · 역배열'
    else:
        label = {'up': '상승 우세', 'down': '하락 우세'}.get(direction, '방향 미확인')
        label += ' · ' + ('수렴' if regime == 'convergence' else '혼조')
    if phase == SIDEWAYS:
        label += ' · ' + SIDEWAYS
    return label


def _surge(i, opens, closes):
    body = (closes[i] - opens[i]) / opens[i] * 100
    sources = []
    floors = []
    if body >= patterns.BIG_CANDLE_MIN_PCT:
        sources.append('장대양봉')
        floors.append(opens[i])
    window_returns = {}
    for n in expansion.WINDOWS:
        if i + 1 >= n:
            window_open = opens[i - n + 1]
            pct, _, matched = expansion.expansion_window(window_open, closes[i], n)
            window_returns[str(n)] = pct
            if matched:
                sources.append(f'{n}봉 누적 급등')
                floors.append(window_open)
    return body, sources, floors, window_returns


def market_days(df):
    """마감 시점의 배열·가격 구조·관찰 상태. 급등은 강도 근거로만 사용한다."""
    if df.empty:
        return []
    shapes = patterns.compute_candle_shape(df)['shape'].tolist()
    regime_frame = dashboard.pipeline.ma_regime.compute_ma_regime(df)
    regimes = regime_frame[['ma_regime', 'EMA50', 'EMA200']].itertuples(index=False, name=None)
    swing_input = df if 'close_time' in df else df.assign(close_time=df.open_time + timedelta(days=1))
    swings_frame = swing_points.find_swing_points(swing_input)
    flags = list(swings_frame[['swing_high', 'swing_low']].itertuples(index=False, name=None))
    days = df.open_time.dt.strftime('%Y-%m-%d').tolist()
    opens, highs, lows, closes = (df[col].astype(float).tolist() for col in ('open', 'high', 'low', 'close'))
    swings = []
    start = floor = attempt = leg_watch_id = sideways_ceiling = None
    impulse_floor = last_surge = None
    pending = []
    watches = {}
    peak_history = []
    rows = []
    for i, (regime, ema50, ema200) in enumerate(regimes):
        # 혼합 문자열 열에 있는 None은 pandas 버전에 따라 NaN으로 전달된다.
        regime = regime if isinstance(regime, str) else None
        day = days[i]
        events = []
        body, sources, floors, window_returns = _surge(i, opens, closes)
        if sources:
            last_surge = i
            if impulse_floor is None:
                impulse_floor = min(floors)
                events.append(_event('rise_start', '강한 상승 시작', day, surge_sources=sources, impulse_floor=impulse_floor))
            else:
                impulse_floor = max(impulse_floor, min(floors))
        if impulse_floor is not None and closes[i] < impulse_floor:
            impulse_floor = None

        _advance_swings(i, swings, flags, days, highs, lows)
        swing_highs = [p for p in swings if p['kind'] == 'high']
        swing_lows = [p for p in swings if p['kind'] == 'low']
        direction = _price_direction(swing_highs, swing_lows)
        for watch_id, (opened, watch) in list(watches.items()):
            if closes[i] > watch['watch_breakout']:
                released = _event('high_watch_released', '숏 관찰 해제 · 상방 돌파', day,
                                  related_id=watch_id, watch_breakout=watch['watch_breakout'],
                                  confirmation_close=closes[i], started_on=days[opened], age_bars=i-opened+1)
                suffix = watch_id.removeprefix('rise:high_retry_failed:')
                released['id'] += ':' + suffix
                events.append(released)
                del watches[watch_id]
                if watch_id == leg_watch_id:
                    leg_watch_id = None
                    attempt = PeakAttempt(i)

        advancing = closes[i] > (closes[i-1] if i else opens[i])
        if start is None and advancing:
            start, floor, attempt = i, (lows[i-1] if i else lows[i]), PeakAttempt(i)
        if start is not None and swing_lows and swing_lows[-1]['date'] >= days[start]:
            floor = max(floor, swing_lows[-1]['price'])

        # 예전 구간에서 이미 관찰한 눌림은 새 구간·배열 전환 뒤에도 추적한다.
        # 이전 고점이 허용 범위를 넘어 갱신되면 그 옛 기준의 재시도는 끝난다.
        pending = [a for a in pending if highs[i] <= highs[a.first] * (1 + SIMILAR_HIGH)]
        trackers = pending + ([attempt] if attempt is not None else [])
        for anchor in trackers:
            failure = anchor.advance(i, days, highs, lows, closes)
            if failure is None:
                continue
            # 같은 첫 고점 가격대의 관찰이 살아 있을 때 더 많은 접촉을 새 알림으로 세지 않는다.
            existing = next((key for key, (_, w) in watches.items()
                             if abs(failure['first_peak'] / w['first_peak'] - 1) <= SIMILAR_HIGH), None)
            if existing is None:
                if failure['id'] in watches:
                    failure['id'] += ':' + failure['first_peak_day']
                failure['surge_since_peak'] = last_surge is not None and last_surge >= anchor.first
                events.append(failure)
                watches[failure['id']] = (i, failure)
                existing = failure['id']
            if anchor is attempt:
                leg_watch_id, attempt = existing, None
            else:
                pending.remove(anchor)

        phase = '가격 상승 근거 미확인'
        overlap = high_advance = None
        if start is not None:
            if closes[i] < floor:
                if attempt is not None and attempt.dip is not None:
                    pending.append(attempt)
                start = floor = attempt = leg_watch_id = sideways_ceiling = None
            else:
                sideways, overlap, high_advance = _sideways(i, start, peak_history, highs, lows, closes)
                if sideways_ceiling is not None and closes[i] > sideways_ceiling * (1 + MAX_HIGH_ADVANCE):
                    sideways_ceiling = None
                if sideways and sideways_ceiling is None:
                    sideways_ceiling = max(highs[i - SIDEWAYS_BARS + 1:i + 1])
                    events.append(_event('high_sideways', SIDEWAYS, day,
                                         overlap_ratio=overlap, high_advance_pct=high_advance))
                phase = DIPPING if leg_watch_id or (attempt and attempt.dip is not None) else RISING
                if sideways:
                    phase = SIDEWAYS
        previous_peak = peak_history[-1] if start is not None and i > start else highs[i]
        peak_history.append(max(previous_peak, highs[i]))
        weaker = len(swing_highs) == 2 and swing_highs[-1]['price'] <= swing_highs[0]['price']
        active = [dict(id=w['id'], date=days[opened], watch_breakout=w['watch_breakout'], age_bars=i-opened+1)
                  for opened, w in watches.values()]
        latest = active[-1] if active else {}
        facts = dict(ema_regime=regime, ema50=ema50 if isfinite(ema50) else None,
                     ema200=ema200 if isfinite(ema200) else None, price_direction=direction, price_phase=phase,
                     swing_highs=swing_highs, swing_lows=swing_lows,
                     candle_shape=patterns.PATTERN_LABEL_KR.get(shapes[i]), bullish_body_pct=body,
                     surge_sources=sources, window_returns_pct=window_returns, impulse_floor=impulse_floor,
                     surge_context=last_surge is not None and i-last_surge <= patterns.BIG_CANDLE_SUPPRESS_BARS,
                     first_peak=highs[attempt.first] if attempt else None,
                     pullback_close=closes[attempt.dip] if attempt and attempt.dip is not None else None,
                     retry_peak=highs[attempt.retry] if attempt and attempt.retry is not None else None,
                     overlap_ratio=overlap, high_advance_pct=high_advance,
                     watch_breakout=latest.get('watch_breakout'), watch_id=latest.get('id'), active_watches=active)
        rows.append(dict(market=_market_label(regime, direction, phase, weaker), events=events,
                         details=facts, short_watch=bool(watches)))
    return rows
