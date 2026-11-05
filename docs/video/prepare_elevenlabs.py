#!/usr/bin/env python3
"""Recreate the final narration from preserved ElevenLabs audio and reviewed cuts.

No network, generation, service login, or new voice requests are performed.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from production import HERE,WORK,CHAPTERS,probe,run

ALIGNMENT=HERE/'narration-alignment.json'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--alignment',type=Path,default=ALIGNMENT)
    args=parser.parse_args()
    alignment=json.loads(args.alignment.read_text())
    SOURCE=(args.audio or HERE/alignment.get('source_audio','work/elevenlabs/culture-fit-harry-kim-v4-generation1.mp3')).resolve()
    receipt=(args.receipt or HERE/alignment.get('source_receipt','work/elevenlabs/source.json')).resolve()
    source_record=json.loads(receipt.read_text())
    source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert source_hash==source_record['sha256'], 'Original audio changed'
    expected=json.loads((HERE/'narration-request.json').read_text())['cues']
    assert [c['id'] for c in alignment['cues']]==[c['id'] for c in expected]
    outdir=WORK/'narration-cues'/SOURCE.stem;outdir.mkdir(parents=True,exist_ok=True)
    timing=[]
    for cut,request in zip(alignment['cues'],expected):
        a,b=cut['source_start_seconds'],cut['source_end_seconds']
        assert 0<=a<b<=source_record['original_duration_seconds']
        slot=request['end_seconds']-request['start_seconds']
        # Respect a verified edit boundary; never truncate a word to fit a slot.
        if b-a>slot-.08:
            raise RuntimeError(f"{cut['id']} needs {b-a:.3f}s; slot is {slot}s. Adjust caption timing before rendering.")
        out=outdir/f"{cut['id']}.wav"
        run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',a,'-i',SOURCE,
            '-t',b-a,'-ar','48000','-ac','1','-c:a','pcm_s16le',out)
        padded=outdir/f"padded-{cut['id']}.wav"
        run('ffmpeg','-hide_banner','-loglevel','error','-y','-i',out,
            '-af','apad','-t',slot,'-ar','48000','-ac','1','-c:a','pcm_s16le',padded)
        timing.append({'id':cut['id'],'start':request['start_seconds'],'end':request['end_seconds'],
            'source_start_seconds':a,'source_end_seconds':b,'original_duration':b-a,
            'slot':slot,'speed':1.0,'trailing_padding_seconds':slot-(b-a),
            'text':request['subtitle'],'path':str(padded)})
    listing=outdir/'audio-concat.txt'
    listing.write_text(''.join(f"file '{c['path']}'\n" for c in timing))
    master=WORK/'narration.wav'
    run('ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,
        '-c:a','pcm_s16le',master)
    total=sum(c['duration'] for c in CHAPTERS)
    assert abs(float(probe(master)['format']['duration'])-total)<.001
    record={**source_record,'imported':True,'duration':total,'source_audio':str(SOURCE.relative_to(HERE)),
        'automatic_service_calls':False,'source_audio_sha256':source_hash,'source_receipt':str(receipt.relative_to(HERE)),
        'alignment':'Local MLX Whisper word timestamps + normalized script alignment + measured silence boundaries. See narration-alignment.json.',
        'editing':'22 sentence cues, original playback speed 1.0 throughout; silence padding added to match caption slots. No voice cloning or new generation during import.',
        'source_reference':'User-authorized ElevenLabs web Text to Speech generation; original receipt and MP3 retained at source_audio/source_receipt.',
        'credit_title':'Culture-Fit 컬처핏 | Open-source Human-in-the-Loop (HITL) | elevenlabs.io',
        'publication_guidance':'https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform',
        'files':timing}
    (WORK/'voice-timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2))
    (HERE/'narration-source.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
    print(f'Prepared {len(timing)} cues, {total}s, original playback speed 1.0 throughout.')

if __name__=='__main__':main()
