from __future__ import annotations
import hashlib,json,subprocess,re
from pathlib import Path
from PIL import Image,ImageDraw
from production import HERE,ROOT,WORK,CHAPTERS,probe,font,run
video=HERE/'culture-fit-demo-1080p.mp4';meta=probe(video)
ko_cues=re.findall(r'(?m)^\d+\n([^\n]+ --> [^\n]+)\n',(HERE/'culture-fit-demo.ko.srt').read_text())
en_cues=re.findall(r'(?m)^\d+\n([^\n]+ --> [^\n]+)\n',(HERE/'culture-fit-demo.en.srt').read_text())
assert len(en_cues)==22 and en_cues==ko_cues
network=json.loads((HERE/'captures/browser-network.json').read_text())
assert not any(r['method']=='POST' and r['url'].endswith('/brief') for r in network)
assert all(r['url'].startswith('http://127.0.0.1:8798/') for r in network)
assert not json.loads((HERE/'captures/browser-errors.json').read_text())
authority=json.loads((HERE/'captures/authority-after-priority.json').read_text())
assert authority['brief']['authority_checks'][0]['status']=='authorized'
assert authority['brief']['authority_checks'][0]['decision_owner']=='검토봇B'
assert len(authority['brief']['intervention_points'])==0
simulation=json.loads((HERE/'captures/simulation-completed.json').read_text())
assert simulation['status']=='completed' and simulation['mode']=='demo'
assert simulation['metrics']['measured_calls']==0

stream=next(x for x in meta['streams'] if x['codec_type']=='video')
audio=next(x for x in meta['streams'] if x['codec_type']=='audio')
assert meta['format']['tags']['title']=='Culture-Fit 컬처핏 | Open-source Human-in-the-Loop (HITL) | elevenlabs.io'
voice=json.loads((HERE/'narration-source.json').read_text())
assert voice['provider']=='ElevenLabs' and len(voice['files'])==22
assert all(x['speed']==1.0 and x['trailing_padding_seconds']>=0 for x in voice['files'])
assert (HERE/'references.json').exists()
alignment=json.loads((HERE/'narration-alignment.json').read_text())
assert len(alignment['cues'])==22
assert (stream['width'],stream['height'])==(1920,1080)
expected_seconds=sum(c['duration'] for c in CHAPTERS)
assert abs(float(meta['format']['duration'])-expected_seconds)<.02
assert abs(float(stream['duration'])-expected_seconds)<.02
assert abs(float(audio['duration'])-expected_seconds)<.02
assert int(stream['nb_frames'])==expected_seconds*30
assert all(x['disposition']['default']==0 for x in meta['streams'] if x['codec_type']=='subtitle')
run('ffmpeg','-hide_banner','-loglevel','error','-i',video,'-f','null','-')
contact=Image.new('RGB',(1440,1515),'#000000');d=ImageDraw.Draw(contact)
for i,t in enumerate([5,23,37,51,77,95,106,126,133,145,165,184]):
    p=WORK/f'review-{t}.png';run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',t,'-i',video,'-frames:v','1',p)
    im=Image.open(p);im.thumbnail((464,261));x=16+(i%3)*480;y=30+(i//3)*375
    contact.paste(im,(x,y));d.text((x,y+272),f'{t//60:02}:{t%60:02}',font=font(23),fill='white')
contact.save(HERE/'contact-sheet.jpg',quality=92)
run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',expected_seconds-.05,'-i',video,'-frames:v','1',WORK/'review-final-frame.png')
assert (WORK/'review-final-frame.png').stat().st_size>1000
run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',184,'-i',video,'-frames:v','1',HERE/'end-credits-preview.png')
checks={
 'artifact':video.name,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'bytes':video.stat().st_size,
 'video_frame_count':int(stream['nb_frames']),'video_stream_duration_seconds':float(stream['duration']),'audio_stream_duration_seconds':float(audio['duration']),
 'duration_seconds':float(meta['format']['duration']),'width':stream['width'],'height':stream['height'],'frame_rate':stream['avg_frame_rate'],'video_codec':stream['codec_name'],'audio_codec':audio['codec_name'],'audio_sample_rate':audio['sample_rate'],
 'title':meta['format']['tags'].get('title'),
 'end_credits':{'start_seconds':183,'end_seconds':186,'text':['출처: Anthropic (2024) · Google (2025) · Li & Xie (2025) | 음성: ElevenLabs'],'font_size_px':24,'position_y_px':860,'style':'Single muted gray line; original Three.js outro remains visible'},
 'references':'references.json',
 'standalone_english_captions':{'path':'culture-fit-demo.en.srt','cue_count':22,'timing_identical_to_korean':True,'embedded_in_video':False,'sha256':hashlib.sha256((HERE/'culture-fit-demo.en.srt').read_bytes()).hexdigest()},
 'global_positioning':'MIT-licensed open-source Human-in-the-Loop (HITL) coordination layer for developers worldwide, with MCP tools, an A2A analysis service, and a reusable Skill package. Describes intended audience and reuse, not international adoption.',
 'bilingual_upload_description':'upload-description.txt',
 'post_capture_public_links':{'demo':'https://culture-fit-demo-production.up.railway.app/','source_branch':'https://github.com/Ontology0/hanium-arbiter/tree/feat/ontology-hitl','scope':'Published after recording; this fixed local capture does not validate their current state.'},
 'captions':'Burned Korean captions + optional embedded Korean mov_text (default=0, avoids duplicate automatic captions) + standalone UTF-8 SRT',
 'narration':voice,
 'narration_sync_check':json.loads((HERE/'narration-sync-check.json').read_text()),
 'narration_alignment':{'path':'narration-alignment.json','exact_match_ratio':alignment['exact_match_ratio'],'review_status':alignment.get('editorial_review'),'method':alignment['method'],'speed':1.0},
 'audio_mastering':'48 kHz AAC; normalized to -16 LUFS target and -1.5 dB true-peak target.',
 'capture':'Playwright Chromium channel chrome, 1600x750 viewport/video, real app at 127.0.0.1:8798. Whole UI: 1480x694 at (220,128); main-area crop (300,0,1260,650) enlarged to 1560x805 at (180,100), within black 1920x1080 canvas. UI content and app theme unchanged.',
 'editing':'Real UI is cut between stages. The authority approval shot uses 7.2 recorded seconds retimed to 11 seconds for legibility; no application state was synthesized.',
 'motion':'61 seconds of original Three.js r180 WebGL motion: intro16, timeliness12, overview8, authority10, outro15; 125 seconds of real UI recording. See motion/render-validation.json and motion/README.md for available source details.',
 'caption_layout':json.loads((HERE/'caption-layout.json').read_text()),
 'editorial_font':'Pretendard ExtraBold/Regular v1.3.9, locally supplied official OTF files. Burned subtitles 52px, white with selected #FFE16A / #53FFD8 glow.',
 'isolation':'SQLite copy of .runtime/authority-demo.sqlite3; only docs/video/work/video-demo.sqlite3 mutated; original service 8797 read-only source; operating service 8787 not used',
 'data':'Synthetic text examples; prior saved actual-model briefing reused in authority scene; scripted simulation',
 'no_model_post_requests':True,'no_slack_account_connected':True,'external_actions_executed':False,'uploaded_or_published':False,
 'validation':['Full FFmpeg decode passed','Video/audio/container duration186.000s and5580 video frames checked','UI assertions: imported decision persisted; cross-owner conflict -> authorized; simulation waiting -> completed','Twelve-frame contact sheet generated for visual review','22 narration cues preserve original ElevenLabs playback speed; script alignment and silence boundaries inspected'],
 'source_sha256':json.loads((HERE/'captures/capture-source-hashes.json').read_text()),
 'source_snapshot_notice':'These are the app source hashes verified unchanged at recording start/end. The live working tree may differ after subsequent deployment development; the video reuses the fixed capture.',
 'limitations':['Local operator records do not authenticate external owners or their consent','No general infinite-loop detection or model-quality claim','Simulation completion means local plan checklist satisfied, not attendance/delivery/execution','Not a live Slack integration test or independent user evaluation; fixed local capture does not verify the later public branch/deployed demo'],
 'narration_cue_timing':json.loads((WORK/'voice-timing.json').read_text()),
 'ui_capture_source_sha256':json.loads((HERE/'captures/capture-source-hashes.json').read_text()),
 'motion_files_sha256':{str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'motion'/f'{name}.mp4' for name in ['intro','timeliness','overview','authority','outro']]},
 'ffprobe':meta,
}
(HERE/'validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));print(json.dumps({k:checks[k] for k in ['duration_seconds','width','height','bytes','sha256']},ensure_ascii=False))
