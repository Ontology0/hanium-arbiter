#!/usr/bin/env python3
"""Audit measured glyph ink + neon bounds throughout the motion, without rendering."""
import json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'layout-bounds.json').read_text())
durations={'intro':16,'why-now':12,'overview':8,'authority':10,'outro':15}
def ease(x):
    x=max(0,min(1,x));return x*x*(3-2*x)
def visible(o,t):
    return ease((t-o['start'])/.7)*(1-ease((t-o['end'])/.5))>.15
def offset(o,t):
    if o['start']==0 and o['end']==100:return 0
    return 12*(1-ease((t-o['start'])/.7)*(1-ease((t-o['end'])/.5)))
def box(o,t):
    dy=offset(o,t);return (o['left'],o['top']+dy,o['right'],o['bottom']+dy)
def point_box(x,y,b):return math.hypot(max(b[0]-x,0,x-b[2]),max(b[1]-y,0,y-b[3]))
def point_segment(x,y,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];p=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(x-a[0]-p*dx,y-a[1]-p*dy)
def segment_box(a,b,r):
    # Liang-Barsky clipping detects an intersection before distance checks.
    lo,hi=0.,1.;dx=b[0]-a[0];dy=b[1]-a[1]
    hit=True
    for p,q in [(-dx,a[0]-r[0]),(dx,r[2]-a[0]),(-dy,a[1]-r[1]),(dy,r[3]-a[1])]:
        if p==0:
            if q<0:hit=False;break
        elif p<0:lo=max(lo,q/p)
        else:hi=min(hi,q/p)
    if hit and lo<=hi:return 0
    return min(point_box(*a,r),point_box(*b,r),*(point_segment(x,y,a,b) for x,y in [(r[0],r[1]),(r[2],r[1]),(r[2],r[3]),(r[0],r[3])]))

report={'method':'Measured Pretendard glyph bounds; text neon padding 14px; ring glow 10px; line glow full width; 0.1-second phase sampling above 15% opacity','scenes':{}}
failures=[]
for scene,duration in durations.items():
    texts=[o for o in data['texts'] if o['scene']==scene]
    rings=[o for o in data['rings'] if o['scene']==scene]
    strokes=[o for o in data['strokes'] if o['scene']==scene]
    min_ring=(999,None);min_line=(999,None);min_text=(999,None);max_bottom=0;overlaps=[]
    for tick in range(duration*10):
        t=tick/10;active=[o for o in texts if visible(o,t)]
        for i,a in enumerate(active):
            ab=box(a,t);max_bottom=max(max_bottom,ab[3])
            for b in active[i+1:]:
                bb=box(b,t)
                gap=math.hypot(max(ab[0]-bb[2],bb[0]-ab[2],0),max(ab[1]-bb[3],bb[1]-ab[3],0))
                if gap<min_text[0]:min_text=(gap,{'time':t,'a':a['str'],'b':b['str']})
                if min(ab[2],bb[2])>max(ab[0],bb[0]) and min(ab[3],bb[3])>max(ab[1],bb[1]):overlaps.append({'time':t,'a':a['str'],'b':b['str']})
            for r in rings:
                if not visible(r,t):continue
                if a['str']=='배포 승인' and r['radius']>80:continue # intended text inside the task node
                gap=point_box(r['x'],r['y']+offset(r,t),ab)-r['radius']
                if gap<min_ring[0]:min_ring=(gap,{'time':t,'text':a['str'],'ring':[r['x'],r['y']]})
            for l in strokes:
                if not visible(l,t):continue
                dy=offset(l,t);gap=segment_box((l['x1'],l['y1']+dy),(l['x2'],l['y2']+dy),ab)-l['halfWidth']
                if gap<min_line[0]:min_line=(gap,{'time':t,'text':a['str']})
    report['scenes'][scene]={'textOverlapCount':len(overlaps),'minimumTextToTextGapPx':round(min_text[0],2),'minimumTextToTextLocation':min_text[1],'minimumRingToTextGapPx':round(min_ring[0],2),'minimumRingToTextLocation':min_ring[1],'minimumLineToTextGapPx':round(min_line[0],2),'minimumLineToTextLocation':min_line[1],'maximumTextBottomPx':round(max_bottom,2),'subtitleSafeAreaTopPx':900}
    if overlaps or min_text[0]<20 or min_ring[0]<20 or min_line[0]<20 or max_bottom>900:failures.append({'scene':scene,'overlaps':overlaps[:4]})
report['failures']=failures
(ROOT/'spacing-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
if failures:raise SystemExit(1)
