"""격리 validation.py 서버 하나에서 실제 차트 클릭과 일봉 API 응답을 대조한다."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


TITLE = '상승·급등 대응 · 실험'
CHECKS = Path(__file__).with_name('direction_cases.json')
STAGES = {'new': '신규', 'maintained': '유지', 'released': '해제', 'invalidated': '무효'}


def click_day(page, target, days):
    # 캔버스의 실제 호버 날짜를 읽어 목표 봉을 찾는다. 차트 내부 API나 앱 상태를 변경하지 않는다.
    canvas = page.locator('canvas').first
    box = canvas.bounding_box()
    assert box
    left, right = round(box['x'] + 1), round(box['x'] + box['width'] - 1)
    bar_spacing = box['width'] / (len(days) + 25)
    y = round(box['y'] + box['height'] * 0.6)
    legend = page.get_by_test_id('chart-legend-ohlc').locator('span').first
    selected = page.locator('aside h2 + div strong').first.inner_text()

    def hover(x):
        page.mouse.move(x, y)
        page.evaluate('() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))')
        return legend.inner_text()

    # 오른쪽 빈 공간에서는 범례가 직전 선택일로 돌아간다. 실제로 관찰된 두 봉의
    # 화면 간격으로 x를 추정한 뒤 목표 봉의 범례와 클릭 결과를 각각 검증한다.
    anchors = []
    for part in (0.2, 0.6, 0.4, 0.8):
        x = round(left + part * len(days) * bar_spacing)
        label = hover(x)
        if label in days and label != selected and not any(label == anchor[0] for anchor in anchors):
            anchors.append((label, x))
        if len(anchors) == 2:
            break
    if len(anchors) == 2:
        (d1, x1), (d2, x2) = anchors
        bar_spacing = (x2 - x1) / (days.index(d2) - days.index(d1))
        x = round(x1 + (days.index(target) - days.index(d1)) * bar_spacing)
    else:
        x = round(left + (days.index(target) + 0.5) * bar_spacing)
    x = min(right, max(left, x))
    center = x
    for i in range(28):
        hovered = hover(x)
        if hovered == target:
            # 차트 라이브러리가 연속 단일 클릭을 더블클릭으로 묶지 않게 한다.
            page.wait_for_timeout(550)
            page.mouse.click(x, y)
            expect(page.locator('aside h2 + div strong').first).to_have_text(target, timeout=3000)
            return
        if i < 12:
            # 각 앵커에서 봉 안의 어느 지점을 읽었는지에 따른 오차를 먼저 보정한다.
            x = min(right, max(left, round(center + (i // 2 + 1) * bar_spacing * 0.25 * (-1 if i % 2 else 1))))
            continue
        if hovered < target:
            left = x + 1
        else:
            right = x - 1
        assert left <= right, (target, hovered, left, right)
        x = (left + right) // 2
    raise AssertionError(f'차트에서 {target} 선택 실패')


def check(url, case, output, checks):
    assert urlsplit(url).scheme == 'http' and urlsplit(url).hostname == '127.0.0.1'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    blocked = []
    errors = []
    responses = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(locale='ko-KR', viewport={'width': 3200 if case == 'fixed' else 1440,
                                                                'height': 960}, service_workers='block')

        def guard(route):
            if route.request.url.startswith(url + '/') and route.request.method == 'GET':
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()

        context.route('**/*', guard)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda r: responses.update({r.url: r}) if '/api/rise-response?' in r.url else None)
        with page.expect_response(lambda r: '/api/dashboard?' in r.url) as dashboard:
            page.goto(url)
        days = [bar['date'] for bar in dashboard.value.json()['candles']]
        toggle = page.get_by_role('checkbox', name=TITLE)
        expect(toggle).not_to_be_checked()
        assert not responses
        toggle.click()
        panel = page.get_by_test_id('rise-response-panel')
        expect(panel).to_have_attribute('data-date', days[-1], timeout=30000)
        for check_day in checks:
            day = check_day['date']
            click_day(page, day, days)
            expect(panel).to_have_attribute('data-date', day, timeout=30000)
            panel_values = panel.locator('dl dd').all_inner_texts()
            http = responses[f'{url}/api/rise-response?date={day}']
            body = http.json()
            assert http.status == 200 and body['date'] == day and body['enabled']
            assert panel_values == [body[k] for k in ('market', 'long_exit', 'short_signal')]
            for key, expected in check_day.get('contains', {}).items():
                assert expected in body[key], (day, key, expected, body[key])
            kinds = {e['kind'] for e in body['events']}
            assert set(check_day.get('events', [])) <= kinds, (day, kinds)
            source = '고정 마감 일봉 데이터' if case == 'fixed' else '합성 데이터 · 검증용'
            expect(panel.get_by_text(source)).to_be_visible()
            record = dict(case=case, date=day, market=body['market'], long_exit=body['long_exit'],
                          short_signal=body['short_signal'], source=body['data_source'], http=http.status)
            details = body['details']
            summary = panel.get_by_text('판정 근거와 당일 사건', exact=True)
            summary.click()
            expect(summary.locator('..')).to_have_attribute('open', '')
            lifecycle = details['lifecycle']
            for item, li in zip(lifecycle, panel.get_by_role('listitem').all(), strict=True):
                expect(li).to_contain_text(STAGES[item['status']])
                expect(li).to_contain_text(item['started_on'])
                expect(li).to_contain_text(f"{item['age_days']}일")
                if item.get('ended_on'):
                    expect(li).to_contain_text(item['ended_on'])
            market = details['market']
            for point in [*market['swing_highs'], *market['swing_lows']]:
                expect(panel).to_contain_text(f"발생 {point['date']} → 확인 {point['confirmed_on']}")
            for level in details['drawings']['levels']:
                if level.get('source') in ('EMA50', 'EMA200') and level['kind'] == 'resistance':
                    for label, key in [('접촉 당시', 'price'), ('당일', 'current_price')]:
                        number = page.evaluate(
                            "value => new Intl.NumberFormat('ko-KR', {maximumFractionDigits: 4}).format(value)",
                            level[key])
                        expect(panel).to_contain_text(f"{label} {level['source']} {number}")
            summary.click()
            record.update(ema_regime=market['ema_regime'], price_direction=market['price_direction'],
                          event_kinds=sorted(kinds), lifecycle=lifecycle)
            if check_day.get('capture'):
                record['capture'] = f'{case}-{day}.png'
                panel.scroll_into_view_if_needed()
                page.screenshot(path=output / record['capture'])
            records.append(record)
        assert not errors and not blocked, (errors, blocked)
        context.close()
        browser.close()
    (output / f'{case}.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n',
                                        encoding='utf-8')
    print(f'{case}: {len(records)}개 날짜의 차트 클릭·API·패널 대조 통과')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='--frontend로 실행한 격리 서버의 127.0.0.1 주소')
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    cases = json.loads(CHECKS.read_text(encoding='utf-8'))
    check(arguments.url.rstrip('/'), arguments.case, arguments.output, cases[arguments.case])
