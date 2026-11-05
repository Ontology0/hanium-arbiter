"""Build the product editions from actual English UI, new voice and Three.js.

Preserves every older video artifact. Run with --language ko, then en.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw
from production import font, wrap
from visual_style import canvas, glow_text
from disable_subtitle_default import disable_defaults

HERE = Path(__file__).resolve().parent
WORK = HERE / 'work' / 'product'
MOTION = HERE / 'product-motion'


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(seconds):
    milliseconds = round(seconds * 1000)
    return f'{milliseconds // 3600000:02d}:{milliseconds // 60000 % 60:02d}:{milliseconds // 1000 % 60:02d},{milliseconds % 1000:03d}'


def narration(language):
    directory = WORK / f'audio-{language}'
    alignment = json.loads((directory / 'alignment-reviewed.json').read_text())
    stem = 'product-ko-harry-kim-v4-generation1' if language == 'ko' else 'product-en-daniel-v4-generation1'
    source = HERE / 'work' / 'elevenlabs' / f'{stem}.mp3'
    receipt = json.loads(source.with_suffix('.json').read_text())
    assert digest(source) == receipt['audio_sha256']
    assert digest(HERE / f'product-script-{language}.txt') == receipt['script_sha256']
    cues = alignment['cues']
    filters = ['[0:a]asplit=22' + ''.join(f'[a{i}]' for i in range(22))]
    silence_intervals = json.loads((directory / 'silences.json').read_text())
    for i, cue in enumerate(cues):
        a, b = cue['source_start_seconds'], cue['source_end_seconds']
        duration = cue['end_seconds'] - cue['start_seconds']
        assert b - a <= duration - .05
        if i < 21:
            assert any(interval['start'] <= b <= interval['end'] for interval in silence_intervals), (language, cue['id'], b)
        filters.append(f'[a{i}]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,apad,atrim=duration={duration}[b{i}]')
    filters.append(''.join(f'[b{i}]' for i in range(22)) + 'concat=n=22:v=0:a=1[out]')
    out = directory / 'narration.wav'
    run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', source,
        '-filter_complex', ';'.join(filters), '-map', '[out]', '-ar', 48000, '-ac', 1, '-c:a', 'pcm_s16le', out)
    assert abs(float(probe(out)['format']['duration']) - 180) < .001
    record = {**receipt, 'imported': True, 'source_audio': str(source.relative_to(HERE)),
              'output': str(out.relative_to(HERE)), 'output_sha256': digest(out),
              'duration_seconds': 180, 'speed': 1.0, 'cue_count': 22,
              'all_21_internal_cuts_in_measured_silence': True,
              'full_original_audio_tail_preserved': True,
              'editing': 'Contiguous source segments split at measured sentence pauses, original speed; silence padding to scene slots.',
              'alignment': str((directory / 'alignment-reviewed.json').relative_to(HERE)),
              'asr_caveat': 'ASR is a text/timing check; proper-name recognition can differ from the authorized original script.',
              'cues': cues}
    (HERE / f'product-narration-source-{language}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    return out, cues


def overlays(language, cues):
    folder = WORK / f'overlay-{language}'
    folder.mkdir(exist_ok=True)
    override_file = HERE / f'product-caption-overrides-{language}.json'
    override_data = json.loads(override_file.read_text()) if override_file.exists() else {}
    caption_overrides = override_data.get('cues', {})
    line_overrides = override_data.get('line_overrides', {})
    size = 52 if language == 'ko' else 44
    white, cyan, yellow = '#FFFFFF', '#53FFD8', '#FFE16A'
    scenes = {c['id']: c['scene'] for c in json.loads((HERE / 'product-storyboard.json').read_text())['cues']}
    titles = {'value': 'HUMAN-IN-THE-LOOP', 'start': 'TRY OR INSTALL', 'install': 'HOW TO USE',
              'first-screen': 'FIRST RUN', 'conflict': 'WHO CAN DECIDE?', 'evidence': 'READ THE EVIDENCE',
              'approval': 'RECORD OWNER APPROVALS', 'next-owner': 'THE NEXT DECISION OWNER',
              'connections': 'CONNECT YOUR AGENTS'}
    layouts, srt, pngs = [], [], []
    for i, cue in enumerate(cues):
        text = caption_overrides.get(cue['id'], cue['subtitle'])
        image = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        a, b = cue['start_seconds'], cue['end_seconds']
        scene = scenes[cue['id']]
        if 16 <= a < 159:
            draw.rectangle((0, 0, 1920, 96), fill='#000000')
            glow_text(image, (52, 24), 'CULTURE-FIT', 25, white)
            glow_text(image, (330, 22), titles.get(scene, scene.upper()), 27, cyan, glow=True)
            label = ('SOURCE INSTALLATION' if a < 59 else 'LOCAL FIRST RUN' if a < 67 else
                     'PUBLIC DEMO · RECORDED ANALYSIS' if a < 109 else
                     'OPERATOR-ENTERED APPROVALS' if a < 133 else
                     'PUBLIC DEMO · SCOPED AUTHORITY' if a < 151 else 'LOCAL CONNECTION SETUP')
            if a < 25:
                label = 'OPEN SOURCE · HUMAN-IN-THE-LOOP'
            glow_text(image, (1865, 25), label, 20, '#b5becb', anchor='ra')
        draw.rectangle((0, 900, 1920, 1080), fill='#000000')
        fnt = font(size, True)
        lines = line_overrides.get(cue['id'], wrap(text, 1770, fnt, draw))
        assert len(lines) <= 2, (language, cue['id'], lines)
        assert all(draw.textlength(line, font=fnt) <= 1770 for line in lines)
        y = 914 if len(lines) == 2 else 966
        boxes = []
        keys = ['권한', '근거', '사람의 판단', '두 소유자의 동의', 'authority', 'evidence', 'human judgment', 'Human-in-the-Loop', 'MIT-licensed']
        for line in lines:
            x = (1920 - draw.textlength(line, font=fnt)) / 2
            boxes.append(draw.textbbox((x, y), line, font=fnt))
            for part in re.split('(' + '|'.join(re.escape(k) for k in keys) + ')', line):
                color = yellow if part in ('권한', 'authority', 'MIT-licensed') else cyan if part in keys else white
                glow_text(image, (x, y), part, size, color, glow=color != white)
                x += draw.textlength(part, font=fnt)
            y += 58 if language == 'ko' else 56
        margin = min(1080 - box[3] for box in boxes)
        assert margin >= 44, (cue['id'], margin)
        path = folder / f'{i:02d}.png'
        image.save(path)
        pngs.append((path, b - a))
        layouts.append({'id': cue['id'], 'start': a, 'end': b, 'lines': lines,
                        'glyph_bounds': boxes, 'bottom_margin': margin})
        srt.append(f'{i + 1}\n{stamp(a)} --> {stamp(b)}\n' + '\n'.join(lines) + '\n')
    # Keep credits unobtrusive and in the existing motion-safe strip.
    final, duration = pngs.pop()
    original = Image.open(final).convert('RGBA')
    credit = 'Voice: ElevenLabs  ·  Open-source code: MIT  ·  Sources in description'
    glow_text(original, (960, 860), credit, 24, '#a7afbb', bold=False, anchor='ma')
    credited = folder / 'end-credit.png'
    original.save(credited)
    pngs.extend([(final, duration - 3), (credited, 3)])
    listing = folder / 'frames.txt'
    listing.write_text(''.join(f"file '{path}'\nduration {duration:.6f}\n" for path, duration in pngs) + f"file '{pngs[-1][0]}'\n")
    subtitle = HERE / f'culture-fit-product.{language}.srt'
    subtitle.write_text('\n'.join(srt))
    layout = {'font': 'Pretendard ExtraBold', 'size': size, 'max_lines': 2,
              'minimum_bottom_margin': min(x['bottom_margin'] for x in layouts), 'cues': layouts}
    (HERE / f'product-caption-layout-{language}.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n')
    return listing, subtitle, layout


def base_video():
    base = WORK / 'product-base.mp4'
    if base.exists():
        return base
    receipt = json.loads((WORK / 'capture-receipt.json').read_text())
    assert not receipt['page_errors'] and receipt['source_zip_match']
    backdrop = WORK / 'canvas.png'
    canvas().convert('RGB').save(backdrop)
    pieces = [MOTION / 'problem.mp4']
    # Enlarged app content; entire first screen and setup pages remain visible.
    for start, end, focused in [(16, 59, False), (59, 75, False), (75, 151, True), (151, 154, True), (154, 159, False)]:
        out = WORK / f'ui-{start}-{end}.mp4'
        if not out.exists():
            scaling = 'crop=1300:720:300:0,scale=1440:798:flags=lanczos' if focused else 'scale=1480:740:flags=lanczos'
            x, y = (240, 98) if focused else (220, 130)
            filt = f'[0:v]tpad=stop_mode=clone:stop_duration=2,{scaling},fps=30,setsar=1[ui];[1:v][ui]overlay={x}:{y}:shortest=1,format=yuv420p[v]'
            run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', receipt['trim_start'] + start - 16,
                '-i', HERE / receipt['raw'], '-loop', 1, '-framerate', 30, '-i', backdrop, '-t', end - start,
                '-filter_complex', filt, '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'veryfast',
                '-crf', 18, '-threads', 4, '-video_track_timescale', 15360, out)
        pieces.append(out)
    pieces.extend([MOTION / 'connections.mp4', MOTION / 'cta.mp4'])
    listing = WORK / 'base-concat.txt'
    listing.write_text(''.join(f"file '{p}'\n" for p in pieces))
    run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', 0, '-i', listing, '-c', 'copy', base)
    info = probe(base)
    assert abs(float(info['format']['duration']) - 180) < .05
    return base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--language', choices=['ko', 'en'], required=True)
    args = parser.parse_args()
    language = args.language
    print('Preparing narration and captions:', language, flush=True)
    audio, cues = narration(language)
    overlay, subtitle, layout = overlays(language, cues)
    print('Preparing shared video base', flush=True)
    base = base_video()
    output = HERE / f'culture-fit-product-{language}-1080p.mp4'
    temporary = WORK / f'final-{language}.mp4'
    code = 'kor' if language == 'ko' else 'eng'
    print('Rendering final:', language, flush=True)
    run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', base,
        '-f', 'concat', '-safe', 0, '-i', overlay, '-i', audio, '-i', subtitle,
        '-filter_complex', '[1:v]fps=30,format=rgba[o];[0:v][o]overlay=0:0:shortest=0:eof_action=repeat:repeatlast=1:format=auto,format=yuv420p[v];[2:a]loudnorm=I=-16:TP=-1.5:LRA=11[a]',
        '-map', '[v]', '-map', '[a]', '-map', '3:0', '-t', 180,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', 18, '-threads', 4, '-r', 30,
        '-c:a', 'aac', '-b:a', '160k', '-ar', 48000, '-c:s', 'mov_text', '-disposition:s:0', 0,
        '-metadata:s:s:0', f'language={code}', '-metadata:s:a:0', f'language={code}',
        '-metadata', f'title=Culture-Fit | Open-source Human-in-the-Loop (HITL) | {"Korean" if language == "ko" else "English"} | elevenlabs.io',
        '-metadata', 'comment=Actual English interface; source installation and isolated visitor demo. New product narration. Synthetic example, operator-recorded approvals.',
        '-movflags', '+faststart', temporary)
    patch = disable_defaults(temporary)
    info = probe(temporary)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    sound = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    subs = next(s for s in info['streams'] if s['codec_type'] == 'subtitle')
    assert video['width'] == 1920 and video['height'] == 1080
    assert video['avg_frame_rate'] == '30/1' and int(video['nb_frames']) == 5400
    assert all(abs(float(s['duration']) - 180) < .035 for s in (video, sound, subs))
    assert subs['disposition']['default'] == 0
    run('ffmpeg', '-hide_banner', '-v', 'error', '-xerror', '-i', temporary, '-f', 'null', '-')
    temporary.replace(output)
    frame_paths = []
    for second in (5, 20, 45, 62, 80, 96, 120, 136, 155, 172, 179.9):
        frame = WORK / f'final-{language}-{second}.jpg'
        run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', second, '-i', output, '-frames:v', 1, '-q:v', 2, frame)
        frame_paths.append(frame)
    sheet = Image.new('RGB', (1280, 4 * 258), '#121212')
    draw = ImageDraw.Draw(sheet)
    for i, frame in enumerate(frame_paths):
        im = Image.open(frame); im.thumbnail((420, 236))
        x, y = (i % 3) * 426, (i // 3) * 258
        sheet.paste(im, (x, y)); draw.text((x + 5, y + 237), frame.stem, fill='white')
    sheet.save(HERE / f'product-contact-sheet-{language}.jpg')
    validation = {'file': output.name, 'sha256': digest(output), 'bytes': output.stat().st_size,
                  'language': language, 'interface': 'English', 'narration_language': language,
                  'duration_seconds': 180, 'video_frames': 5400, 'resolution': [1920, 1080], 'fps': 30,
                  'full_decode': 'passed', 'streams_all_cover_180_seconds': True,
                  'subtitle_default': 0, 'subtitle_patch': patch, 'caption_layout': layout,
                  'narration_source': f'product-narration-source-{language}.json',
                  'capture_receipt': 'work/product/capture-receipt.json',
                  'source_first_run': 'work/product/first-run-receipt.json',
                  'motion_seconds': 37, 'actual_ui_seconds': 143,
                  'motion_hashes': {p.name: digest(p) for p in (MOTION / 'problem.mp4', MOTION / 'connections.mp4', MOTION / 'cta.mp4')},
                  'style': 'Black canvas; Pretendard; white captions and cyan/yellow emphasis; actual Three.js motion',
                  'limitations': ['Synthetic prepared example with recorded analysis', 'Operator-entered approval records, not remote identity authentication', 'No new model call or external action in this capture', 'Windows setup instructions shown; Windows hardware execution not performed'],
                  'ffprobe': info}
    revision = WORK / 'caption-revision-before.json'
    if language == 'ko' and revision.exists():
        before = json.loads(revision.read_text())
        audio_packet_hash = subprocess.check_output(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(output), '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).decode().strip()
        assert audio_packet_hash == before['audio_packet_hash'], 'Caption edit changed encoded audio'
        assert digest(audio) == before['narration_wav_sha256'], 'Caption edit changed narration source'
        assert digest(HERE / 'culture-fit-product-en-1080p.mp4') == before['en_video_sha256'], 'English edition changed'
        validation['caption_revision'] = {'override_file': 'product-caption-overrides-ko.json',
                                          'audio_packet_hash': audio_packet_hash,
                                          'encoded_audio_identical_to_previous': True,
                                          'narration_wav_identical_to_previous': True,
                                          'english_edition_unchanged': True,
                                          'timing_unchanged': True}
    (HERE / f'product-validation-{language}.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: validation[k] for k in ('file', 'sha256', 'bytes', 'duration_seconds', 'video_frames', 'full_decode')}, indent=2), flush=True)


if __name__ == '__main__':
    main()
