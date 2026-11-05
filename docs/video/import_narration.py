#!/usr/bin/env python3
"""Import locally supplied narration; does not contact or claim use of a voice service."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from production import HERE,WORK,CHAPTERS,probe,run
p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--cue-dir',type=Path);g.add_argument('--audio',type=Path)
p.add_argument('--provider',default='Supplied audio; provider not independently verified');p.add_argument('--source-reference',default='');a=p.parse_args()
total=sum(c['duration'] for c in CHAPTERS);timing=[];files=[]
if a.cue_dir:
 for c in CHAPTERS:
  for i,(start,end,text) in enumerate(c['cues']):
   stem=f"voice-{c['id']}-{i}";matches=[x for x in a.cue_dir.glob(stem+'.*') if x.suffix.lower() in ['.wav','.mp3','.m4a','.aac','.aiff','.flac']]
   if len(matches)!=1:raise SystemExit(f'Expected exactly one audio file for {stem}; found {len(matches)}')
   src=matches[0];duration=float(probe(src)['format']['duration']);slot=end-start;speed=max(1,duration/(slot-.25))
   if speed>1.12:raise SystemExit(f'{stem} is too long ({duration:.2f}s for {slot}s). Shorten/re-record this cue to preserve natural pacing.')
   files.append((src,stem,slot,duration,speed,text))
 for src,stem,slot,duration,speed,text in files:
  out=WORK/f'imported-{stem}.wav';run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',src,'-af',f'atempo={speed:.7f},apad','-t',slot,'-ar','48000','-ac','1',out)
  timing.append({'source':str(src),'path':str(out),'slot':slot,'original_duration':duration,'speed':speed,'text':text,'sha256':hashlib.sha256(src.read_bytes()).hexdigest()})
 listing=WORK/'imported-audio-concat.txt';listing.write_text(''.join(f"file '{x['path']}'\n" for x in timing))
 run('ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,'-c:a','pcm_s16le',WORK/'narration.wav')
else:
 duration=float(probe(a.audio)['format']['duration'])
 if abs(duration-total)>.05:raise SystemExit(f'Full track must be pre-aligned to {total}s; got {duration:.3f}s. Use --cue-dir for automatic cue matching.')
 run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',a.audio,'-ar','48000','-ac','1','-c:a','pcm_s16le',WORK/'narration.wav')
 timing=[{'source':str(a.audio),'original_duration':duration,'sha256':hashlib.sha256(a.audio.read_bytes()).hexdigest(),'alignment':'Caller supplied a pre-aligned full-length track; listening review required.'}]
(WORK/'voice-timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2))
source={'provider':a.provider,'source_reference':a.source_reference,'imported':True,'duration':total,'automatic_service_calls':False,'files':timing}
(HERE/'narration-source.json').write_text(json.dumps(source,ensure_ascii=False,indent=2))
print('Imported narration. Run production.py render and production.py verify, then listen for alignment.')
