#!/usr/bin/env python3
"""Clear only the MP4 track-enabled flag for optional subtitle tracks.

FFmpeg's MOV muxer enables the first subtitle track even when disposition=0:
https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c (enable_tracks).
No sample bytes, offsets, durations, or other track flags are changed.
"""
from __future__ import annotations
import hashlib,json,subprocess,sys
from pathlib import Path

def atoms(data,start,end):
    while start<end:
        if end-start<8:raise ValueError('Incomplete MP4 atom header')
        size=int.from_bytes(data[start:start+4],'big');kind=bytes(data[start+4:start+8]);header=8
        if size==1:
            size=int.from_bytes(data[start+8:start+16],'big');header=16
        elif size==0:size=end-start
        if size<header or start+size>end:raise ValueError('Invalid MP4 atom length')
        yield kind,start+header,start+size
        start+=size

def disable_defaults(path):
    path=Path(path)
    meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))
    track_ids={int(s['id'],0) for s in meta['streams'] if s['codec_type']=='subtitle'}
    if not track_ids:raise ValueError('No subtitle track to configure')
    original=path.read_bytes();data=bytearray(original);seen=set();changes=[]
    top=list(atoms(data,0,len(data)))
    media_before=[hashlib.sha256(data[a:b]).hexdigest() for k,a,b in top if k==b'mdat']
    for kind,a,b in top:
        if kind!=b'moov':continue
        for child,c,d in atoms(data,a,b):
            if child!=b'trak':continue
            for leaf,e,f in atoms(data,c,d):
                if leaf!=b'tkhd':continue
                version=data[e]
                if version not in (0,1):raise ValueError('Unsupported track header version')
                id_offset=e+(12 if version==0 else 20)
                track_id=int.from_bytes(data[id_offset:id_offset+4],'big')
                if track_id not in track_ids:continue
                seen.add(track_id);flags=int.from_bytes(data[e+1:e+4],'big')
                updated=flags & ~1
                data[e+1:e+4]=updated.to_bytes(3,'big')
                changes.append({'track_id':track_id,'old_flags':flags,'new_flags':updated})
    assert seen==track_ids
    assert media_before==[hashlib.sha256(data[a:b]).hexdigest() for k,a,b in top if k==b'mdat']
    differences=sum(a!=b for a,b in zip(original,data))
    assert len(data)==len(original) and differences<=len(track_ids)
    temporary=path.with_suffix(path.suffix+'.flags-tmp');temporary.write_bytes(data);temporary.replace(path)
    return {'optional_subtitle_tracks':changes,'changed_byte_count':differences,'media_samples_unchanged':True}

if __name__=='__main__':print(json.dumps(disable_defaults(sys.argv[1]),indent=2))
