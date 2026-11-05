#!/usr/bin/env python3
"""Rebuild the Culture-Fit local demonstration. No model calls or external publication."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = HERE / 'work'
CAPTURES = HERE / 'captures'
BASE = 'http://127.0.0.1:8798'
AUTHORITY_SESSION = '177cddcae14345fba16b42eb6772121e'
CHAPTERS = [{'id': 'intro',
  'title': '대화의 검증에서, 결정의 권한으로',
  'duration': 16,
  'cues': [(0, 8, '컬처핏은 생성형 AI를 믿고 쓰려면 무엇을 확인해야 할까, 라는 질문에서 출발했어요.'),
           (8, 16, '문화와 역사 자료, 깃허브의 지식 충돌을 살피다 보니, 이제는 누가 결정할 수 있는지에 주목하게 됐죠.')]},
 {'id': 'timeliness',
  'title': '왜 지금, 결정 권한일까요?',
  'duration': 12,
  'cues': [(0, 6, '에이전트가 도구를 쓰고, 서로 일을 맡기는 연결 표준이 생겼어요.'), (6, 12, '이제는 누가 어떤 결정을 내려도 되는지까지 살펴봐야 하죠.')]},
 {'id': 'intake',
  'title': '01  합성 대화 가져오기',
  'duration': 19,
  'cues': [(0, 9, '대화가 길어지면, 중요한 질문도 놓치기 쉬워요. 먼저 두 에이전트의 대화를 가져와 볼까요?'),
           (9, 19, '확인해 볼게요, 라는 약속은 있어요. 그런데 누가 답하고, 누가 다음 일을 맡을지는 더 확인해야 해요.')]},
 {'id': 'overview',
  'title': '02  현황과 원문 확인',
  'duration': 17,
  'cues': [(0, 8, '현황에서는 지금 필요한 질문을 한눈에 모아 봐요. 어떤 결정이 남아 있는지부터 살펴보죠.'),
           (8, 17, '궁금한 내용은 원문으로 돌아가 확인해요. 누가 어떤 말을 했는지, 근거를 함께 볼 수 있어요.')]},
 {'id': 'decision',
  'title': '03  사람의 판단과 다음 행동 기록',
  'duration': 23,
  'cues': [(0, 9, '아직 전달 여부가 확인되지 않은 요청을 열어 볼게요. 이 질문을 맡을 담당자를 정해 줘요.'),
           (9, 17, '개발 에이가 배포 책임자에게 승인 여부를 확인하고, 이곳에 답변을 남기도록 적어요.'),
           (17, 23, '담당자와 할 일을 남기니, 다음 행동이 선명해졌어요.')]},
 {'id': 'knowledge',
  'title': '04  대화·약속·결정의 관계',
  'duration': 12,
  'cues': [(0, 12, '지식맵에서는 대화와 확인 약속, 사람의 판단이 어떻게 이어지는지 볼 수 있어요. 흩어진 기록을 관계로 살펴보는 거죠.')]},
 {'id': 'authority',
  'title': '05  권한 충돌에서 공동 승인 기록으로',
  'duration': 37,
  'cues': [(0, 10, '같은 정보를 안다고, 승인 권한까지 같아지는 건 아니에요. 두 에이전트가 같은 배포를 승인하려 하면, 누구의 위임을 따라야 할까요?'),
           (10, 19, '두 에이전트의 소유자가 달라요. 누가 먼저 결정할지, 관련된 두 사람의 동의를 모아야 하죠.'),
           (19, 29, '이번 배포의 승인 순서를 정하고 두 사람의 동의를 기록해요. 검토봇 B가 먼저 맡도록 해 볼게요.'),
           (29, 37, '두 사람의 승인이 모이자 검토봇 B가 담당자로 정해졌어요. 권한을 묻던 질문도 정리돼요.')]},
 {'id': 'simulation',
  'title': '06  통제 시뮬레이션 · 중단 → 사람 결정 → 재개',
  'duration': 35,
  'cues': [(0, 10, '모임을 조율하는 상황도 볼까요? 에이전트들이 대화를 이어가다가, 사람의 답이 필요한 순간에 기다려요.'),
           (10, 21, '참석할 수 있는지 선택하고 이유를 남겨요. 사람의 판단이 기록되면 대화를 이어서 실행할 수 있어요.'),
           (21, 29, '답을 받은 에이전트가 다음 대화를 이어가고, 조율 계획의 조건을 하나씩 확인해요.'),
           (29, 35, '마지막으로 조율 계획의 완료 상태를 확인해요.')]},
 {'id': 'outro',
  'title': '근거를 확인하고, 권한에 맞게 결정하기',
  'duration': 15,
  'cues': [(0, 8, '컬처핏은 근거를 찾고, 권한을 확인하고, 필요한 사람의 판단을 연결해요.'),
           (8, 15, '여러 에이전트가 함께 일할 때, 누가 다음 결정을 맡는지 더 쉽게 살펴보세요.')]}]

def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args],check=True,**kwargs)

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

def fetch(path):
    with urllib.request.urlopen(BASE+path) as r: return json.load(r)

def snapshot():
    WORK.mkdir(parents=True,exist_ok=True); CAPTURES.mkdir(exist_ok=True)
    try:
        with urllib.request.urlopen(BASE+'/api/health',timeout=.5):
            raise RuntimeError('8798 서버를 종료한 뒤 snapshot을 실행하세요.')
    except OSError:
        pass
    db=WORK/'video-demo.sqlite3'
    for p in [db,Path(str(db)+'-wal'),Path(str(db)+'-shm')]: p.unlink(missing_ok=True)
    original=ROOT/'.runtime/authority-demo.sqlite3'
    if original.exists():
        source=sqlite3.connect(f"file:{original}?mode=ro",uri=True)
        target=sqlite3.connect(db);source.backup(target);source.close();target.close()
    else:
        # Portable replay of the preserved synthetic session; never fabricate a fresh model result.
        state=json.loads((CAPTURES/'authority-briefing-source.json').read_text())
        registry=json.loads((CAPTURES/'authority-registry-source.json').read_text())
        target=sqlite3.connect(db)
        target.execute('CREATE TABLE sessions (id TEXT PRIMARY KEY, updated_at TEXT NOT NULL, state TEXT NOT NULL)')
        target.execute('CREATE TABLE configuration (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        target.execute('INSERT INTO sessions VALUES (?,?,?)',(state['id'],state['updated_at'],json.dumps(state,ensure_ascii=False)))
        target.execute('INSERT INTO configuration VALUES (?,?)',('authority',json.dumps(registry,ensure_ascii=False)))
        target.commit();target.close()
    # A read-only snapshot of the existing, synthetic model briefing. Reset only the video copy's priority.
    target=sqlite3.connect(db)
    raw=target.execute("SELECT value FROM configuration WHERE key='authority'").fetchone()
    if raw:
        registry=json.loads(raw[0]);registry['precedence']=[]
        target.execute("UPDATE configuration SET value=? WHERE key='authority'",(json.dumps(registry,ensure_ascii=False),))
    target.execute('DELETE FROM sessions WHERE id != ?',(AUTHORITY_SESSION,))
    target.commit();target.close()
    shutil.copy2(db,WORK/'initial-video-demo.sqlite3')

def font(size,bold=False):
    from PIL import ImageFont
    path=HERE/'fonts'/('Pretendard-ExtraBold.otf' if bold else 'Pretendard-Regular.otf')
    return ImageFont.truetype(str(path),size)

def wrap(text,width,fnt,draw):
    import re
    if draw.textlength(text,font=fnt)<=width:return [text]
    sentences=re.split(r'(?<=[.!?])\s+',text)
    if len(sentences)==2 and all(draw.textlength(t,font=fnt)<=width for t in sentences):return sentences
    words=text.split();choices=[]
    for i in range(1,len(words)):
        left=' '.join(words[:i]);right=' '.join(words[i:]);a=draw.textlength(left,font=fnt);b=draw.textlength(right,font=fnt)
        if max(a,b)<=width:choices.append((abs(a-b),[left,right]))
    if choices:return min(choices,key=lambda x:x[0])[1]
    lines=[];line=''
    for token in words:
        candidate=f'{line} {token}'.strip()
        if draw.textlength(candidate,font=fnt)>width and line:lines.append(line);line=token
        else:line=candidate
    if line:lines.append(line)
    return lines

def artwork():
    from visual_style import build
    build()

def speech():
    WORK.mkdir(exist_ok=True)
    cues=[];start=0
    for c in CHAPTERS:
        for i,(a,b,text) in enumerate(c['cues']):
            path=WORK/f"voice-{c['id']}-{i}.aiff"
            if not path.exists():run('say','-v','Yuna','-r','155','-o',path,text.replace('검토봇 B','검토봇 비'))
            dur=float(probe(path)['format']['duration']);slot=b-a
            # Fit narration inside each matching caption window; preserve intelligibility.
            speed=max(1,dur/(slot-.35))
            out=WORK/f"voice-{c['id']}-{i}.wav"
            run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',path,'-af',f'atempo={speed:.6f},apad','-t',slot,'-ar','48000','-ac','1',out)
            cues.append({'path':str(out),'start':start+a,'original_duration':dur,'slot':slot,'speed':speed})
        start+=c['duration']
    listing=WORK/'audio-concat.txt';listing.write_text(''.join(f"file '{c['path']}'\n" for c in cues))
    run('ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,'-c:a','pcm_s16le',WORK/'narration.wav')
    (WORK/'voice-timing.json').write_text(json.dumps(cues,ensure_ascii=False,indent=2))
    (HERE/'narration-source.json').write_text(json.dumps({'provider':'macOS say / Yuna Korean','imported':False,'base_rate':155,'duration':sum(c['duration'] for c in CHAPTERS),'automatic_service_calls':False,'note':'Local synthetic voice; no ElevenLabs service used.'},ensure_ascii=False,indent=2))
    print('Narration seconds:',probe(WORK/'narration.wav')['format']['duration'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('task',choices=['snapshot','artwork','speech','capture','render','verify']);args=parser.parse_args()
    if args.task=='snapshot':snapshot()
    elif args.task=='artwork':artwork()
    elif args.task=='speech':speech()
    elif args.task=='capture':run(sys.executable,HERE/'record_ui.py','--scenes','intake','overview','decision','knowledge','authority','simulation')
    elif args.task=='render':run(sys.executable,HERE/'render_video.py')
    elif args.task=='verify':run(sys.executable,HERE/'verify_video.py')
