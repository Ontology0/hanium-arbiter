#!/usr/bin/env python3
"""Render English captions over the same Korean UI/diagrams and Korean narration."""
from __future__ import annotations
import hashlib,json,re,shutil
from PIL import Image,ImageDraw
from production import HERE,WORK,CHAPTERS,font,wrap,run,probe
from visual_style import overlay,glow_text,end_credits,WHITE,YELLOW,CYAN
from disable_subtitle_default import disable_defaults

def seconds(stamp):
    h,m,tail=stamp.split(':');s,ms=tail.split(',')
    assert int(ms)==0
    return int(h)*3600+int(m)*60+int(s)

def main():
    text=(HERE/'culture-fit-demo.en.srt').read_text()
    cues=[]
    for block in text.strip().split('\n\n'):
        lines=block.splitlines();a,b=lines[1].split(' --> ')
        cues.append((seconds(a),seconds(b),' '.join(lines[2:])))
    assert len(cues)==22 and cues[0][0]==0 and cues[-1][1]==186
    chapters=[];offset=0
    for c in CHAPTERS:chapters.append((offset,offset+c['duration'],c));offset+=c['duration']
    directory=WORK/'overlay-en';directory.mkdir(exist_ok=True)
    f=font(44,True);bounds=[]
    keys=['approval authority','delegated authority','human judgment','Review Bot B','authority','evidence']
    for start,end,caption in cues:
        chapter=next(c for a,b,c in chapters if a<=start<b)
        im=overlay(chapter,'');d=ImageDraw.Draw(im)
        lines=wrap(caption,1770,f,d);assert len(lines)<=2,(start,lines)
        y=925 if len(lines)==2 else 970
        for line in lines:
            x=(1920-d.textlength(line,font=f))/2
            bounds.append({'cue_start_seconds':start,'text':line,'bottom_px':y+f.getbbox(line)[3]})
            for part in re.split('('+'|'.join(keys)+')',line):
                if not part:continue
                color=CYAN if part in ['evidence','human judgment'] else YELLOW if part in keys else WHITE
                glow_text(im,(x,y),part,44,color,glow=color!=WHITE);x+=d.textlength(part,font=f)
            y+=55
        first=directory/f'{start:04}.png';im.save(first)
        for second in range(start+1,end):shutil.copyfile(first,directory/f'{second:04}.png')
    for second in range(183,186):
        path=directory/f'{second:04}.png';end_credits(Image.open(path).convert('RGBA')).save(path)
    margin=1080-max(x['bottom_px'] for x in bounds);assert margin>=44
    (HERE/'caption-layout-en.json').write_text(json.dumps({'font':'Pretendard ExtraBold','size_px':44,'max_lines':2,'minimum_text_bottom_margin_px':margin,'glyph_bounds':bounds},ensure_ascii=False,indent=2))
    korean=HERE/'culture-fit-demo-1080p.mp4';out=WORK/'final-en-render.mp4'
    base=WORK/'v2-base.mp4';assert int(probe(base)['streams'][0]['nb_frames'])==5580
    run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',base,'-framerate','1','-i',directory/'%04d.png',
        '-i',korean,'-i',HERE/'culture-fit-demo.en.srt',
        '-filter_complex','[0:v][1:v]overlay=0:0:shortest=0:eof_action=repeat:repeatlast=1:format=auto,format=yuv420p[v]',
        '-map','[v]','-map','2:a:0','-map','3:0','-map_metadata','2','-map_chapters','2','-t','186',
        '-c:v','libx264','-preset','veryfast','-crf','18','-threads','4','-c:a','copy','-c:s','mov_text',
        '-disposition:s:0','0','-metadata:s:s:0','language=eng',
        '-metadata','title=Culture-Fit | Human-in-the-Loop (HITL), English captions | elevenlabs.io',
        '-metadata','comment=English captions over Korean UI and original Three.js diagrams; original Korean Harry Kim narration.',
        '-movflags','+faststart',out)
    patch=disable_defaults(out);out.replace(HERE/'culture-fit-demo-en-1080p.mp4');out=HERE/'culture-fit-demo-en-1080p.mp4'
    meta=probe(out);v=next(x for x in meta['streams'] if x['codec_type']=='video');a=next(x for x in meta['streams'] if x['codec_type']=='audio');sub=next(x for x in meta['streams'] if x['codec_type']=='subtitle')
    assert (v['width'],v['height'],int(v['nb_frames']))==(1920,1080,5580)
    assert all(abs(float(x['duration'])-186)<.02 for x in [meta['format'],v,a])
    assert sub['disposition']['default']==0 and sub['tags']['language']=='eng'
    run('ffmpeg','-hide_banner','-loglevel','error','-i',out,'-f','null','-')
    run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',185.95,'-i',out,'-frames:v','1',HERE/'english-caption-preview.png')
    # Compare the compressed audio packets, rather than re-encoding the approved voice.
    import subprocess
    def audio_hash(path):
        return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-']).decode().strip()
    approved_hash=audio_hash(korean);assert audio_hash(out)==approved_hash
    record={'artifact':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size,
        'duration_seconds':186.0,'video_stream_duration_seconds':float(v['duration']),'audio_stream_duration_seconds':float(a['duration']),
        'width':1920,'height':1080,'frame_rate':'30/1','video_frame_count':5580,'english_cue_count':22,
        'scope':'English narration captions only. Original Korean UI, Korean editorial labels, Korean Three.js diagrams, and the approved Korean Harry Kim narration are retained.',
        'audio':'Copied AAC packets from the Korean final; no new TTS or audio re-encoding.','audio_packet_hash':approved_hash,
        'caption_layout':json.loads((HERE/'caption-layout-en.json').read_text()),'optional_subtitle_patch':patch,
        'korean_artifact_sha256':hashlib.sha256(korean.read_bytes()).hexdigest(),'base_video_sha256':hashlib.sha256(base.read_bytes()).hexdigest(),
        'validation':['Full FFmpeg decode passed','186 seconds for video/audio/container;5580 frames','Last frame185.95s extracted','English mov_text default0','AAC packet hash matches approved Korean version','English captions fit two lines with44px or more bottom margin'],
        'ffprobe':meta}
    (HERE/'validation-en.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(json.dumps({k:record[k] for k in ['artifact','sha256','bytes','duration_seconds']},indent=2))

if __name__=='__main__':main()
