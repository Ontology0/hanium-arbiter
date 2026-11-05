"""Compose real UI, original Three.js motion, Pretendard captions and Korean narration."""
from __future__ import annotations
import json
from pathlib import Path
from production import HERE,WORK,CHAPTERS,run
receipts=json.loads((WORK/'recording-receipts.json').read_text())
segments=[]
ENC=['-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-video_track_timescale','15360']

def motion(name):
 out=WORK/f'v2-motion-{name}.mp4'
 run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',HERE/'motion'/f'{name}.mp4','-vf','fps=30,setsar=1,format=yuv420p',*ENC,out)
 return out

def ui(scene,a,b,label,full=False,source_start=None,source_duration=None):
 out=WORK/f'v2-ui-{label}.mp4'
 if out.exists():return out
 receipt=receipts[scene];start=receipt['trim_start']+a if source_start is None else source_start
 timing=f'trim=duration={source_duration},setpts=(PTS-STARTPTS)*{(b-a)/source_duration},' if source_duration else ''
 if full:fg='scale=1480:694:flags=lanczos';x,y=220,128
 else:fg='crop=1260:650:300:0,scale=1560:805:flags=lanczos';x,y=180,100
 filt=f'[0:v]{timing}tpad=stop_mode=clone:stop_duration=2,{fg},fps=30,setsar=1[ui];[1:v][ui]overlay={x}:{y}:shortest=1,format=yuv420p[v]'
 print('UI segment',label,flush=True)
 run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',start,'-i',HERE/receipt['raw'],'-loop','1','-framerate','30','-i',WORK/'canvas.png','-t',b-a,'-filter_complex',filt,'-map','[v]',*ENC,out)
 return out

def join(parts,name):
 if len(parts)==1:return parts[0]
 listing=WORK/f'v2-{name}-list.txt';listing.write_text(''.join(f"file '{p}'\n" for p in parts))
 out=WORK/f'v2-{name}.mp4';run('ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,'-c','copy',out)
 return out

for c in CHAPTERS:
 name=c['id']
 if name in ['intro','timeliness','outro']:parts=[motion(name)]
 elif name=='overview':parts=[motion('overview'),ui(name,0,4,'overview-questions'),ui(name,12,17,'overview-source')]
 elif name=='authority':parts=[motion('authority'),ui(name,0,4,'authority-brief'),ui(name,9,15,'authority-conflict'),ui(name,0,11,'authority-approval-v3',source_start=18,source_duration=7.2),ui(name,31,37,'authority-result')]
 elif name=='simulation':parts=[ui(name,0,10,'simulation-start',True),ui(name,10,35,'simulation-decision-resume')]
 else:parts=[ui(name,0,c['duration'],name,name=='intake')]
 segments.append(join(parts,name))
concat=WORK/'v2-video-concat.txt';concat.write_text(''.join(f"file '{p}'\n" for p in segments))
base=WORK/'v2-base.mp4';run('ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy',base)
meta=';FFMETADATA1\ntitle=Culture-Fit 컬처핏 | Open-source Human-in-the-Loop (HITL) | elevenlabs.io\ncomment=Real local UI capture with original Three.js motion; synthetic examples; no external execution.\n'
start=0
for c in CHAPTERS:
 meta+=f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start*1000}\nEND={(start+c['duration'])*1000}\ntitle={c['title']}\n";start+=c['duration']
(WORK/'chapters.txt').write_text(meta)
out=WORK/'final-render.mp4';print('Final composite',start,'seconds',flush=True)
run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',base,'-framerate','1','-i',WORK/'overlay/%04d.png','-i',WORK/'narration.wav','-i',HERE/'culture-fit-demo.ko.srt','-i',WORK/'chapters.txt','-filter_complex','[0:v][1:v]overlay=0:0:shortest=0:eof_action=repeat:repeatlast=1:format=auto,format=yuv420p[v];[2:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]','-map','[v]','-map','[a]','-map','3:0','-map_metadata','4','-map_chapters','4','-t',start,'-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-c:a','aac','-b:a','160k','-ar','48000','-c:s','mov_text','-disposition:s:0','0','-metadata:s:s:0','language=kor','-metadata:s:a:0','language=kor','-movflags','+faststart',out)
from disable_subtitle_default import disable_defaults
(WORK/'subtitle-default-patch.json').write_text(json.dumps(disable_defaults(out),indent=2))
out.replace(HERE/'culture-fit-demo-1080p.mp4')
print(HERE/'culture-fit-demo-1080p.mp4',flush=True)
