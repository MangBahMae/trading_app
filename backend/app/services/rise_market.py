"""마감된 BTCUSDT 일봉의 상승 국면과 고점 재시도. 날짜는 모두 UTC 봉 시작일이다."""
from dataclasses import dataclass

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
    """급등 이후의 3봉. 급등 봉 자체는 겹침이나 고점 전진 계산에 넣지 않는다."""
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


def market_days(df):
    """시간순 마감봉을 한 번 순회한다. 현재 봉의 각 상태와 그날 확정된 새 사건을 반환한다."""
    if df.empty:
        return []
    shapes = patterns.compute_candle_shape(df)['shape'].tolist()
    days = df.open_time.dt.strftime('%Y-%m-%d').tolist()
    opens, highs, lows, closes = (df[col].astype(float).tolist() for col in ('open', 'high', 'low', 'close'))
    start = floor = attempt = attempt_watch_id = sideways_ceiling = None
    watches = {}
    peak_history = []
    rows = []
    for i, day in enumerate(days):
        events = []
        sources = []
        floors = []
        body = (closes[i] - opens[i]) / opens[i] * 100
        if body >= patterns.BIG_CANDLE_MIN_PCT:
            sources.append('장대양봉')
            floors.append(opens[i])
        window_returns = {}
        for n in expansion.WINDOWS:
            if i + 1 >= n:
                window_open = opens[i - n + 1]
                # 기존 필터는 다음 약세 봉에서 읽는다. 시장 상태는 마지막 상승 봉 마감에 이미 알 수 있다.
                pct, _, matched = expansion.expansion_window(window_open, closes[i], n)
                window_returns[str(n)] = pct
                if matched:
                    sources.append(f'{n}봉 누적 급등')
                    floors.append(window_open)

        for watch_id, watch in list(watches.items()):
            if closes[i] > watch['watch_breakout']:
                released = _event('high_watch_released', '숏 관찰 해제 · 상방 돌파', day,
                                  related_id=watch_id, watch_breakout=watch['watch_breakout'],
                                  confirmation_close=closes[i])
                released['id'] += ':' + watch['date']
                events.append(released)
                del watches[watch_id]
                if watch_id == attempt_watch_id:
                    attempt_watch_id = None
                    attempt = PeakAttempt(i)

        if floors and start is None:
            start, floor, attempt = i, min(floors), PeakAttempt(i)
            events.append(_event('rise_start', '강한 상승 시작', day, surge_sources=list(sources), impulse_floor=floor))
        elif floors:
            floor = max(floor, min(floors))

        market = NORMAL
        overlap = high_advance = None
        if start is not None:
            if attempt_watch_id is None:
                failure = attempt.advance(i, days, highs, lows, closes)
                if failure:
                    events.append(failure)
                    attempt_watch_id = failure['id']
                    watches[attempt_watch_id] = failure
            if closes[i] < floor:
                start = floor = attempt = attempt_watch_id = sideways_ceiling = None
            else:
                sideways, overlap, high_advance = _sideways(i, start, peak_history, highs, lows, closes)
                if sideways_ceiling is not None and closes[i] > sideways_ceiling * (1 + MAX_HIGH_ADVANCE):
                    sideways_ceiling = None
                if sideways and sideways_ceiling is None:
                    sideways_ceiling = max(highs[i - SIDEWAYS_BARS + 1:i + 1])
                    events.append(_event('high_sideways', SIDEWAYS, day,
                                         overlap_ratio=overlap, high_advance_pct=high_advance))
                market = RISING if attempt.dip is None else DIPPING
                if sideways:
                    market = SIDEWAYS
        previous_peak = peak_history[-1] if start is not None and i > start else highs[i]
        peak_history.append(max(previous_peak, highs[i]))
        latest_watch = next(reversed(watches.values()), None)
        details = dict(candle_shape=patterns.PATTERN_LABEL_KR.get(shapes[i]), bullish_body_pct=body,
                       surge_sources=sources, window_returns_pct=window_returns, impulse_floor=floor,
                       first_peak=highs[attempt.first] if attempt else None,
                       pullback_close=closes[attempt.dip] if attempt and attempt.dip is not None else None,
                       retry_peak=highs[attempt.retry] if attempt and attempt.retry is not None else None,
                       overlap_ratio=overlap, high_advance_pct=high_advance,
                       watch_breakout=latest_watch['watch_breakout'] if latest_watch else None,
                       watch_id=latest_watch['id'] if latest_watch else None,
                       active_watches=[dict(id=w['id'], date=w['date'], watch_breakout=w['watch_breakout'])
                                       for w in watches.values()])
        rows.append(dict(market=market, events=events, details=details, short_watch=bool(watches)))
    return rows
