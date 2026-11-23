"""격리 서버에서 실제 차트를 클릭해 선택일 HTTP 응답과 신규·유지·종료 색상을 대조한다."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

# 빈 기대값은 당시 도형 기록이 없는 고정 일봉이다. 그 외 날짜는 합성 사례다.
CASES = {
    'fixed': {'2024-03-16': []},
    'zone_hold': {'2022-01-02': ['breakout_up'], '2022-01-03': ['long_candidate'],
                  '2022-01-04': ['long_candidate:maintained'], '2022-01-05': ['invalidated:ended']},
    'zone_failure': {'2022-01-03': ['breakout_caution'], '2022-01-04': ['breakout_failed', 'long_exit'],
                     '2022-01-05': ['short_candidate'], '2022-01-06': ['short_candidate:maintained']},
    'wick': {'2022-01-02': ['wick_sweep']},
    'support_recover': {'2022-01-03': ['breakdown_failed'], '2022-01-04': ['long_candidate']},
    'slope_down': {'2022-01-03': ['breakout_up'], '2022-01-04': ['long_candidate']},
    'slope_up': {'2022-01-03': ['long_exit'], '2022-01-04': ['breakdown_failed'],
                 '2022-01-05': ['long_candidate']},
    'slope_short': {'2022-01-03': ['long_exit'], '2022-01-04': ['short_candidate'],
                    '2022-01-05': ['short_candidate:maintained']},
    'version_lifecycle': {'2022-01-03': ['version_replaced:ended'], '2022-01-06': ['version_ended:ended']},
    'expiry': {'2022-01-11': ['expired:ended']},
    'gentle': {'2022-03-04': ['long_candidate']}, 'bear_rebound': {'2022-03-22': ['long_candidate']},
}
COLORS = {'long_candidate': 'rgb(112, 217, 181)', 'short_candidate': 'rgb(255, 146, 155)',
          'breakout_caution': 'rgb(148, 198, 255)', 'breakout_failed': 'rgb(148, 198, 255)',
          'breakdown_failed': 'rgb(148, 198, 255)', 'long_exit': 'rgb(246, 197, 111)'}
MUTED = 'rgb(138, 143, 156)'
CAPTURES = {('slope_down', '2022-01-04'), ('zone_failure', '2022-01-05'), ('bear_rebound', '2022-03-22')}


def check_day(panel, rise, body, case, day, expected):
    from playwright.sync_api import expect

    events = {e['id']: e for e in [*body['active'], *body['events']]}
    visible = panel.locator('li[data-event-id]').all()
    assert len(visible) == len(events)
    found = []
    for row in visible:
        event = events[row.get_attribute('data-event-id')]
        kind, status = event['type'], event['status']
        expect(row.locator('strong')).to_have_text(event['label'])
        expect(row).to_have_attribute('data-status', status)
        color = row.locator('strong').evaluate('(el) => getComputedStyle(el).color')
        wanted = COLORS.get(kind) if status == 'new' else MUTED
        if wanted:
            assert color == wanted, (case, day, kind, color, wanted)
        found.append({'id': event['id'], 'type': kind, 'label': event['label'], 'status': status,
                      'confirmed': event['confirmed_date'], 'color': color})
    assertions = {r['type'] if r['status'] == 'new' else r['type'] + ':' + r['status'] for r in found}
    assert set(expected) <= assertions, (case, day, expected, assertions)
    assert len(found) == len({r['id'] for r in found})
    if any(r['type'] in ('long_candidate', 'short_candidate') and r['status'] == 'new' for r in found):
        assert found[0]['type'] in ('long_candidate', 'short_candidate'), (case, day, found)
    expect(panel).to_contain_text(body['market_label'])
    if body['market_context']:
        expect(panel).to_contain_text(body['market_context'])
    if case == 'fixed':
        assert not events and body['history_status'] == 'unconfirmed'
        expect(panel).to_contain_text('당시 도형 이력 미확인')
    if any(r['type'] in ('short_candidate', 'breakout_failed') for r in found):
        expect(rise.get_by_text('숏 진입 주의', exact=True)).not_to_be_visible()
    shared = [e for e in events.values() if e['type'] == 'short_candidate' and e['origin'] == 'rise_response']
    if shared:
        expect(rise.locator('dl')).not_to_contain_text(shared[0]['label'])
        expect(rise.locator('dl')).to_contain_text('위 돌파·재시험에 표시')
    if events:
        summary = panel.get_by_text('도형·가격과 사건 순서', exact=True)
        summary.click()
        for card in panel.locator('[data-detail-id]').all():
            event = events[card.get_attribute('data-detail-id')]
            expect(card.get_by_text(f"확인 {event['confirmed_date']} (UTC 일봉)", exact=True)).to_be_visible()
            for li, step in zip(card.locator('ol > li').all(), event['steps'], strict=True):
                expect(li).to_contain_text(f"{step['date']} · {step['label']}")
        summary.click()
    return found


def check(url, case, output):
    from playwright.sync_api import expect, sync_playwright
    from research.rise_response.browser.check_chart import click_day

    assert urlsplit(url).scheme == 'http' and urlsplit(url).hostname == '127.0.0.1'
    output.mkdir(exist_ok=True, parents=True)
    records, errors, blocked = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
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
        api = {}
        page.on('response', lambda r: api.update({r.url: r}) if '/api/breakout-retest?' in r.url else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        with page.expect_response(lambda r: '/api/dashboard?' in r.url) as dashboard:
            page.goto(url)
        days = [c['date'] for c in dashboard.value.json()['candles']]
        toggle = page.get_by_role('checkbox', name='돌파·재시험 · 실험')
        expect(toggle).not_to_be_checked()
        assert not api
        toggle.click()
        panel, rise = page.get_by_test_id('breakout-retest-panel'), page.get_by_test_id('rise-response-panel')
        expect(panel).to_have_attribute('data-date', days[-1], timeout=30000)
        page.get_by_role('checkbox', name='상승·급등 대응 · 실험').click()
        expect(rise).to_have_attribute('data-date', days[-1], timeout=30000)
        for day, expected in CASES[case].items():
            click_day(page, day, days)
            for region in (panel, rise):
                expect(region).to_have_attribute('data-date', day, timeout=30000)
            response = api[f'{url}/api/breakout-retest?date={day}']
            body = response.json()
            assert response.ok and body['enabled'] and body['date'] == day
            expect(panel.get_by_text('고정 마감 일봉 데이터' if case == 'fixed' else '합성 데이터 · 검증용')).to_be_visible()
            found = check_day(panel, rise, body, case, day, expected)
            shot = None
            if (case, day) in CAPTURES:
                if case == 'slope_down':
                    panel.get_by_text('도형·가격과 사건 순서', exact=True).click()
                    sequence = panel.locator('ol').first
                    expect(sequence).to_contain_text('2022-01-03')
                    expect(sequence).to_contain_text('선 가격 102')
                    expect(sequence).to_contain_text('2022-01-04')
                    expect(sequence).to_contain_text('선 가격 100')
                shot = f'{case}-{day}.png'
                panel.locator('h3').scroll_into_view_if_needed()
                page.screenshot(path=output / shot)
            records.append(dict(date=day, http=response.status, source=body['data_source'], events=found,
                                market=body['market_label'], context=body['market_context'], capture=shot))
        assert not blocked and not errors, (blocked, errors)
        browser.close()
    (output / f'{case}.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(f'{case}: {len(records)}개 날짜 클릭·HTTP·문구·색상 대조 통과')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser-python', default='python')
    parser.add_argument('--url', help='이미 실행한 격리 검증 서버의 루프백 주소')
    args = parser.parse_args()
    if args.url:
        if len(args.case or []) != 1:
            parser.error('--url에는 검증 서버에 맞는 --case 하나가 필요합니다.')
        check(args.url.rstrip('/'), args.case[0], args.output)
        return
    from research.breakout_retest.validation import isolated
    from fastapi.staticfiles import StaticFiles
    from app.main import app
    from research.rise_response.browser.run_checks import local_server
    app.mount('/', StaticFiles(directory=ROOT / 'frontend/dist', html=True))
    for case in args.case or CASES:
        with isolated(case), local_server() as url:
            subprocess.run([args.browser_python, '-B', str(Path(__file__)), '--case', case, '--url', url,
                            '--output', str(args.output)], check=True)


if __name__ == '__main__':
    main()
