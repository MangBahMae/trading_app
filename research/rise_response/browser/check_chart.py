"""격리 validation.py 서버 하나에서 실제 차트 클릭과 일봉 API 응답을 대조한다."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


# 각 항목은 검증 일자, 확인할 API 필드와 기대 문구. 고정 일봉은 실제 수동 이력 없이 재생한다.
CASES = {
    'surge_doji': [('2022-01-05', 'short_signal', '해당 없음')],
    'high_retry': [('2022-01-04', 'market', '상승 둔화 · 고점 횡보'),
                   ('2022-01-07', 'short_signal', '숏 관찰 · 고점 재시도 실패'),
                   ('2022-01-09', 'short_signal', '숏 관찰 해제 · 상방 돌파')],
    'trendline': [('2022-01-04', 'long_exit', '기존 롱 종료 검토 · 상승 추세선 이탈')],
    'support_fail': [('2022-01-03', 'short_signal', '숏 후보 · 지지 재시험 실패')],
    'fixed': [('2022-02-17', 'short_signal', '숏 관찰 · 고점 재시도 실패')],
}
CAPTURES = {('fixed', '2022-02-17'), ('high_retry', '2022-01-07'),
            ('trendline', '2022-01-04'), ('support_fail', '2022-01-03')}
TITLE = '상승·급등 대응 · 실험'


def click_day(page, target, days):
    # 캔버스의 실제 호버 날짜를 읽어 목표 봉을 찾는다. 차트 내부 API나 앱 상태를 변경하지 않는다.
    canvas = page.locator('canvas').first
    box = canvas.bounding_box()
    assert box
    left, right = round(box['x'] + 1), round(box['x'] + box['width'] - 1)
    bar_spacing = box['width'] / (len(days) + 25)
    x = round(left + (days.index(target) + 0.5) * bar_spacing)
    y = round(box['y'] + box['height'] * 0.6)
    legend = page.get_by_test_id('chart-legend-ohlc').locator('span').first
    for _ in range(16):
        page.mouse.move(x, y)
        page.evaluate('() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))')
        hovered = legend.inner_text()
        if hovered == target:
            # 차트 라이브러리가 연속 단일 클릭을 더블클릭으로 묶지 않게 한다.
            page.wait_for_timeout(550)
            page.mouse.click(x, y)
            expect(page.locator('aside h2 + div strong').first).to_have_text(target, timeout=3000)
            return
        if hovered < target:
            left = x + 1
        else:
            right = x - 1
        assert left <= right, (target, hovered, left, right)
        x = (left + right) // 2
    raise AssertionError(f'차트에서 {target} 선택 실패')


def check(url, case, output):
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
        for day, check_field, expected in CASES[case]:
            click_day(page, day, days)
            expect(panel).to_have_attribute('data-date', day, timeout=30000)
            panel_values = panel.locator('dl dd').all_inner_texts()
            http = responses[f'{url}/api/rise-response?date={day}']
            body = http.json()
            assert http.status == 200 and body['date'] == day and body['enabled']
            assert panel_values == [body[k] for k in ('market', 'long_exit', 'short_signal')]
            assert body[check_field] == expected
            source = '고정 마감 일봉 데이터' if case == 'fixed' else '합성 데이터 · 검증용'
            expect(panel.get_by_text(source)).to_be_visible()
            record = dict(case=case, date=day, market=body['market'], long_exit=body['long_exit'],
                          short_signal=body['short_signal'], source=body['data_source'], http=http.status)
            if case in ('surge_doji', 'trendline'):
                assert body['short_signal'] == '해당 없음'
            if (case, day) in CAPTURES:
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
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    check(arguments.url.rstrip('/'), arguments.case, arguments.output)
