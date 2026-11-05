"""Record actual English product UI for the new Korean and English editions.

Fresh public visitor, isolated downloaded-source first run, no model requests.
The shared raw recording covers global video time 16..159 (143 seconds).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
WORK = HERE / 'work' / 'product'
CAPTURES = HERE / 'captures' / 'product'
PUBLIC = 'https://culture-fit-demo-production.up.railway.app'
LOCAL = 'http://127.0.0.1:8896'


def main():
    local = json.loads((WORK / 'first-run-receipt.json').read_text())
    assert local['ready'] and local['local_url'] == LOCAL
    CAPTURES.mkdir(parents=True, exist_ok=True)
    rawdir = WORK / 'raw'
    rawdir.mkdir(parents=True, exist_ok=True)
    events, errors, requests, responses = [], [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 800},
                                      device_scale_factor=1, locale='en-US', timezone_id='UTC',
                                      record_video_dir=str(rawdir),
                                      record_video_size={'width': 1600, 'height': 800},
                                      accept_downloads=True)

        def guard(route):
            req = route.request
            if urlparse(req.url).netloc not in (urlparse(PUBLIC).netloc, urlparse(LOCAL).netloc):
                route.abort()
                return
            if req.method == 'POST':
                allowed = req.url == PUBLIC + '/api/authority/precedence'
                if not allowed:
                    errors.append('Blocked unexpected mutation: ' + req.url)
                    route.abort()
                    return
            route.continue_()

        context.route('**/*', guard)
        page = context.new_page()
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.on('request', lambda req: requests.append({'method': req.method, 'url': req.url}))
        page.on('response', lambda res: responses.append({'status': res.status, 'url': res.url}))
        page.goto(PUBLIC, wait_until='networkidle')
        page.wait_for_timeout(700)
        began = time.monotonic()

        def at(global_second):
            delta = global_second - 16 - (time.monotonic() - began)
            if delta > 0:
                page.wait_for_timeout(int(delta * 1000))
            events.append({'target_seconds': global_second,
                           'actual_seconds': round(time.monotonic() - began + 16, 3),
                           'url': page.url})

        def scroll(selector, offset=30):
            page.locator(selector).first.evaluate(
                '(el, offset) => window.scrollTo({top: el.getBoundingClientRect().top + window.scrollY - offset, behavior:"smooth"})', offset)
            page.wait_for_timeout(450)

        def click(selector):
            element = page.locator(selector).first
            element.scroll_into_view_if_needed()
            box = element.bounding_box()
            if box:
                page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, steps=12)
            element.click()

        def shot(name):
            page.screenshot(path=str(CAPTURES / f'{name}.png'))

        shot('01-product-landing')
        at(25)
        page.get_by_role('link', name='Install locally').click()
        page.wait_for_load_state('networkidle')
        shot('02-source-and-skill')
        at(33)
        with page.expect_download() as download_event:
            click('#source-download')
        download = download_event.value
        download_path = WORK / 'downloaded-on-camera-source.zip'
        download.save_as(str(download_path))
        shot('03-source-download')
        at(38)
        scroll('#setup-heading', 60)
        at(42)
        click('#macos-tab')
        shot('04-macos-guide')
        at(46)
        click('#windows-tab')
        shot('05-windows-guide')
        at(51)
        scroll('.download-packages', 45)
        with page.expect_download() as download_event:
            click('#skill-download')
        download_event.value.save_as(str(WORK / 'downloaded-on-camera-skill.zip'))
        at(54)
        scroll('#skill-setup', 30)
        shot('06-skill-setup')
        at(59)
        page.goto(LOCAL + '/workspace', wait_until='networkidle')
        shot('07-local-empty-first-run')
        (CAPTURES / 'local-first-run-text.txt').write_text(page.locator('body').inner_text())
        at(67)
        page.goto(PUBLIC + '/workspace', wait_until='networkidle')
        page.locator('#authority-checks').wait_for(state='visible')
        shot('08-public-demo-first-screen')
        at(69)
        click('#open-intake')
        shot('09-import-conversation')
        at(72)
        page.keyboard.press('Escape')
        at(75)
        click('#overview-tab')
        scroll('#authority-check-panel', 20)
        shot('10-authority-conflict')
        assert 'Cross-owner authority conflict' in page.locator('#authority-checks').inner_text()
        at(84)
        click('#knowledge-tab')
        scroll('.authority-panel', 25)
        shot('11-scope-and-owner-grants')
        at(88)
        click('#overview-tab')
        scroll('#authority-check-panel', 20)
        at(92)
        scroll('#brief-panel', 25)
        shot('12-recorded-analysis')
        at(101)
        page.get_by_role('button', name='View source message m1', exact=True).first.click()
        scroll('#conversation-view', 25)
        shot('13-source-message')
        at(109)
        click('#overview-tab')
        scroll('.precedence-form', 25)
        page.get_by_role('button', name='Review Agent Priority Up', exact=True).click()
        shot('14-proposed-priority')
        at(117)
        page.locator('.precedence-form input[value="Owner A"]').check()
        click('.precedence-submit')
        page.wait_for_timeout(850)
        assert 'Missing approvals: Owner B' in page.locator('#authority-checks').inner_text()
        scroll('.precedence-form', 25)
        shot('15-partial-approval')
        (CAPTURES / 'partial-approval.txt').write_text(page.locator('#authority-checks').inner_text())
        at(125)
        page.locator('.precedence-form input[value="Owner B"]').check()
        shot('16-both-owner-approvals')
        at(129)
        click('.precedence-submit')
        page.wait_for_timeout(850)
        at(133)
        scroll('#authority-check-panel', 25)
        result = page.locator('#authority-checks').inner_text()
        assert 'Delegation verified' in result and 'Decision owner\nReview Agent' in result
        shot('17-review-agent-authorized')
        (CAPTURES / 'complete-approval.txt').write_text(result)
        at(142)
        click('#knowledge-tab')
        scroll('.authority-panel', 25)
        shot('18-delegation-scope')
        at(151)
        click('#integration-tab')
        scroll('#integration-view', 25)
        shot('19-install-own-connections')
        at(154)
        page.get_by_role('link', name='Download and install locally').click()
        page.wait_for_load_state('networkidle')
        click('#macos-tab')
        scroll('#mcp-heading', 25)
        shot('20-mcp-configuration')
        at(159)
        active_duration = time.monotonic() - began
        video = page.video
        context.close()
        raw = Path(video.path())
        browser.close()
    import subprocess
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(raw)]))
    duration = float(probe['format']['duration'])
    receipt = {'raw': str(raw.relative_to(HERE)), 'sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
               'viewport': [1600, 800], 'global_start': 16, 'global_end': 159,
               'active_duration': active_duration, 'raw_duration': duration,
               'trim_start': max(0, duration - active_duration), 'events': events,
               'source_zip_match': hashlib.sha256(download_path.read_bytes()).hexdigest() == local['source']['source']['sha256'],
               'capture_method': 'Chrome/Playwright actual deployed English UI and isolated downloaded-source first run',
               'public_context': 'fresh isolated visitor; no existing visitor state imported',
               'local_source_receipt': 'work/product/first-run-receipt.json',
               'page_errors': errors, 'requests': requests, 'responses': responses}
    (WORK / 'capture-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    assert not errors, errors
    assert receipt['source_zip_match'], 'Deployed ZIP changed between first-run setup and recording'
    assert all(r['status'] < 400 for r in responses), 'Failed request during recording'
    assert all(event['actual_seconds'] - event['target_seconds'] < 1.0 for event in events), 'Capture exceeded a cue boundary'
    print(json.dumps({key: value for key, value in receipt.items() if key not in ('requests', 'responses')}, indent=2))


if __name__ == '__main__':
    main()
