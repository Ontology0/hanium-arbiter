"""Playwright recording of the unchanged local application; all interactions use visible controls."""
from __future__ import annotations
import argparse,hashlib,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from production import HERE,ROOT,WORK,CAPTURES,BASE,AUTHORITY_SESSION,CHAPTERS,fetch,probe

parser=argparse.ArgumentParser();parser.add_argument('--scenes',nargs='*',default=['intake','overview','decision','knowledge','simulation']);args=parser.parse_args()
receipts=json.loads((WORK/'recording-receipts.json').read_text()) if (WORK/'recording-receipts.json').exists() else {}
ids=json.loads((WORK/'session-ids.json').read_text()) if (WORK/'session-ids.json').exists() else {}
errors=[];requests=json.loads((CAPTURES/'browser-network.json').read_text()) if (CAPTURES/'browser-network.json').exists() else []

def wait(page,seconds):page.wait_for_timeout(int(seconds*1000))
def scroll(page,selector,offset=45):
    page.locator(selector).first.evaluate('(el, offset) => window.scrollTo({top: el.getBoundingClientRect().top + window.scrollY - offset, behavior:"smooth"})',offset)
    wait(page,.55)
def click(page,selector):
    loc=page.locator(selector).first
    loc.scroll_into_view_if_needed();box=loc.bounding_box()
    if box:page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2,steps=12)
    wait(page,.25);loc.click()
def shot(page,name):page.screenshot(path=str(CAPTURES/f'{name}.png'))
def at(page,start,sec):
    delay=sec-(time.monotonic()-start)
    if delay>0:wait(page,delay)
def persist():
    (WORK/'recording-receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
    (WORK/'session-ids.json').write_text(json.dumps(ids,ensure_ascii=False,indent=2))

def intake(p,start):
    at(p,start,1);click(p,'#open-intake');p.locator('#intake-source').select_option('manual');p.locator('#intake-title').fill('합성 예제 · 배포 승인 확인')
    at(p,start,4);p.locator('#intake-transcript').fill('개발 A: 배포 전 최종 승인 여부는 담당자에게 확인해볼게요.\n검토 B: 검토 항목을 정리했습니다. 승인 답변을 받으면 다음 단계를 진행하겠습니다.')
    shot(p,'01-intake');at(p,start,12);click(p,'#intake-submit');p.locator('#intake-dialog').wait_for(state='hidden');wait(p,.5)
    ids['import']=p.evaluate('localStorage.getItem("arbiter-session")');scroll(p,'.workspace-navigation',20);shot(p,'02-overview')

def overview(p,start):
    scroll(p,'#overview-decision',120);shot(p,'03-current-questions');at(p,start,8);click(p,'#conversation-tab');scroll(p,'#conversation-view',90);shot(p,'04-original-transcript')

def decision(p,start):
    click(p,'#decisions-tab');p.locator('#request-list button').filter(has_text='확인 요청 전달 상태').click();scroll(p,'#decision-content',40)
    at(p,start,3);p.get_by_text('요청 담당자 지정',exact=True).click();at(p,start,7);p.locator('#decision-note').fill('개발 A가 배포 책임자에게 승인 여부를 확인하고 이 세션에 응답을 기록한다.')
    scroll(p,'#decision-note',330);shot(p,'05-human-decision-entry');at(p,start,16);click(p,'#decision-submit');wait(p,.5)
    p.locator('#request-filter').select_option('resolved');scroll(p,'#decision-content',100);shot(p,'06-decision-saved')
    state=fetch('/api/sessions/'+ids['import']);assert len(state['decisions'])==1
    (CAPTURES/'import-after-decision.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))

def knowledge(p,start):
    click(p,'#knowledge-tab');scroll(p,'#graph-view',45);shot(p,'07-knowledge-graph');at(p,start,7);scroll(p,'.graph-details',320)

def authority(p,start):
    scroll(p,'#brief-panel',20) if p.locator('#brief-panel').count() else scroll(p,'.brief-panel',20)
    shot(p,'08-recorded-model-briefing');at(p,start,9);scroll(p,'#authority-check-panel',20);shot(p,'09-owner-conflict')
    assert '소유자 간 권한 충돌' in p.locator('#authority-checks').inner_text()
    at(p,start,18);scroll(p,'.precedence-form',60)
    p.get_by_role('button',name='배포봇A 우선순위 위로',exact=True).click();wait(p,.5)
    p.get_by_role('button',name='검토봇B 우선순위 위로',exact=True).click();wait(p,.5)
    p.locator('.precedence-form input[value="시연 소유자A"]').check();p.locator('.precedence-form input[value="시연 소유자B"]').check()
    at(p,start,24);shot(p,'10-joint-approval-entry');p.locator('.precedence-submit').click();wait(p,.8)
    at(p,start,29);scroll(p,'#authority-check-panel',20);shot(p,'11-authority-updated')
    assert '위임 확인됨' in p.locator('#authority-checks').inner_text()
    result=fetch('/api/sessions/'+AUTHORITY_SESSION+'/brief');(CAPTURES/'authority-after-priority.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))

def simulation(p,start):
    p.evaluate('window.scrollTo(0,0)');p.locator('#scenario-select').select_option('social-handoff');p.locator('#policy-select').select_option('adaptive');p.locator('#mode-select').select_option('demo')
    at(p,start,2);click(p,'#create-session');wait(p,.5);ids['simulation']=p.evaluate('localStorage.getItem("arbiter-session")')
    p.evaluate('window.scrollTo(0,0)');at(p,start,4);click(p,'#run-button');p.locator('#session-status').filter(has_text='사람의 결정 대기').wait_for(timeout=15000)
    shot(p,'12-simulation-waiting');at(p,start,10);click(p,'#decisions-tab');scroll(p,'#decision-content',30);p.get_by_text('참석 가능',exact=True).click();p.locator('#decision-note').fill('합성 시연 응답: 금요일 19시 참석 가능. 결과 전달 담당은 피클 A.')
    scroll(p,'#decision-note',320);shot(p,'13-simulation-human-decision');at(p,start,18);click(p,'#decision-submit');wait(p,.5);p.evaluate('window.scrollTo({top:0,behavior:"smooth"})');wait(p,.7)
    at(p,start,21);click(p,'#run-button');p.locator('#session-status').filter(has_text='완료').wait_for(timeout=15000);click(p,'#overview-tab');scroll(p,'.workspace-navigation',20);shot(p,'14-simulation-complete')
    at(p,start,29);scroll(p,'#overview-task',100) if p.locator('#overview-task').count() else scroll(p,'.overview-task',100)
    shot(p,'15-simulation-completion');state=fetch('/api/sessions/'+ids['simulation']);assert state['status']=='completed' and state['metrics']['success'] is True
    (CAPTURES/'simulation-completed.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))

source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'frontend/index.html',ROOT/'frontend/app.js',ROOT/'frontend/styles.css',ROOT/'backend/arbiter/app.py',ROOT/'backend/arbiter/authority.py']}
(CAPTURES/'capture-source-hashes.json').write_text(json.dumps(source_hashes,indent=2))

with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    for name in args.scenes:
        chapter=next(c for c in CHAPTERS if c['id']==name)
        context=browser.new_context(viewport={'width':1600,'height':750},device_scale_factor=1,record_video_dir=str(WORK/'raw'),record_video_size={'width':1600,'height':750},locale='ko-KR',timezone_id='Asia/Seoul')
        sid=AUTHORITY_SESSION if name=='authority' else ids.get('import')
        if sid:context.add_init_script(f'localStorage.setItem("arbiter-session",{json.dumps(sid)})')
        def route_handler(route):
            req=route.request
            if not req.url.startswith(BASE):route.abort();return
            if req.method=='POST' and req.url.endswith('/brief'):raise RuntimeError('Model-call request blocked by recording guard')
            if req.method=='POST' and req.url.endswith('/api/sessions') and req.post_data_json.get('mode')!='demo':raise RuntimeError('Non-demo session blocked')
            route.continue_()
        context.route('**/*',route_handler)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append({'scene':name,'method':r.method,'url':r.url,'body':r.post_data if r.method=='POST' else None}))
        page.goto(BASE+'/workspace',wait_until='networkidle');page.locator('#create-session').wait_for(state='visible');wait(page,.6)
        if name=='overview':click(page,'#overview-tab')
        if name in ['decision','knowledge']:click(page,'#overview-tab')
        page.evaluate('window.scrollTo(0,0)');wait(page,.4)
        if page.locator('#error-banner').is_visible():raise RuntimeError(page.locator('#error-text').inner_text())
        start=time.monotonic();print('Recording',name,flush=True)
        globals()[name](page,start);at(page,start,chapter['duration']);elapsed=time.monotonic()-start
        video=page.video;context.close();raw=Path(video.path());duration=float(probe(raw)['format']['duration']);offset=max(0,duration-elapsed)
        receipts[name]={'raw':str(raw.relative_to(HERE)),'raw_duration':duration,'active_duration':elapsed,'trim_start':offset,'output_duration':chapter['duration'],'session_id':ids.get('simulation') if name=='simulation' else AUTHORITY_SESSION if name=='authority' else ids.get('import'),'viewport':[1600,750]}
        persist();print('Recorded',name,receipts[name],flush=True)
    browser.close()
(CAPTURES/'browser-network.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2))
(CAPTURES/'browser-errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2))
assert not errors,errors
assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in source_hashes.items()),'App source changed while recording; recapture after stabilization'
