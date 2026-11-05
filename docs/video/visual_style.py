"""Editorial UI frames and subtitles. Three.js motion graphics are supplied by motion/."""
from __future__ import annotations
import json,re,shutil
from PIL import Image,ImageDraw,ImageFilter
from production import HERE,WORK,CHAPTERS,font,wrap
W,H=1920,1080
WHITE='#ffffff';MUTED='#b5becb';YELLOW='#FFE16A';CYAN='#53FFD8'

def canvas():
 im=Image.new('RGBA',(W,H),'#000000');d=ImageDraw.Draw(im)
 for x in range(0,W,80):d.line((x,0,x,924),fill='#080b0e',width=1)
 for y in range(0,924,80):d.line((0,y,W,y),fill='#080b0e',width=1)
 return im

def glow_text(im,xy,text,size,color=WHITE,bold=True,glow=False,anchor=None):
 layer=Image.new('RGBA',im.size);d=ImageDraw.Draw(layer);d.text(xy,text,font=font(size,bold),fill=color,anchor=anchor)
 if glow:
  haze=layer.filter(ImageFilter.GaussianBlur(10));haze.putalpha(haze.getchannel('A').point(lambda a:int(a*.55)));im.alpha_composite(haze)
  soft=layer.filter(ImageFilter.GaussianBlur(3));soft.putalpha(soft.getchannel('A').point(lambda a:int(a*.35)));im.alpha_composite(soft)
 im.alpha_composite(layer)

def subtitle(im,text):
 d=ImageDraw.Draw(im);d.rectangle((0,912,W,H),fill='#000000')
 f=font(52,True);lines=wrap(text,1770,f,d);assert len(lines)<=2,(text,lines)
 y=917 if len(lines)==2 else 965
 keys=['사람의 결정','공동 승인','권한','근거','두 사람의 승인','두 사람의 동의','검토봇 B']
 for line in lines:
  x=(W-d.textlength(line,font=f))/2
  parts=re.split('('+'|'.join(keys)+')',line)
  for part in parts:
   if not part:continue
   color=YELLOW if part in ['권한','공동 승인','두 사람의 승인','두 사람의 동의','검토봇 B'] else CYAN if part in ['근거','사람의 결정','검토봇 B'] else WHITE
   glow_text(im,(x,y),part,52,color,glow=color!=WHITE)
   x+=d.textlength(part,font=f)
  y+=58

def overlay(chapter,text):
 im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im)
 if chapter['id'] not in ['intro','timeliness','outro']:
  d.rectangle((0,0,W,96),fill='#000000');glow_text(im,(60,24),'CULTURE-FIT',25,WHITE)
  glow_text(im,(350,22),chapter['title'],28,CYAN,glow=True)
  glow_text(im,(1860,19),'합성 예제 · 로컬 시연',22,MUTED,anchor='ra')
  if chapter['id']=='authority':glow_text(im,(1860,49),'저장된 모델 분석 · 운영자 입력',19,MUTED,anchor='ra')
  if chapter['id']=='simulation':glow_text(im,(1860,49),'통제 시뮬레이션 · 조율 계획',19,MUTED,anchor='ra')
 subtitle(im,text)
 return im

def end_credits(im):
 # Preserve the original Three.js outro; a quiet source line sits above captions.
 glow_text(im,(960,860),'출처: Anthropic (2024) · Google (2025) · Li & Xie (2025)  |  음성: ElevenLabs',24,MUTED,bold=False,anchor='ma')
 return im

def build():
 WORK.mkdir(exist_ok=True);(WORK/'overlay').mkdir(exist_ok=True)
 canvas().convert('RGB').save(WORK/'canvas.png')
 start=0;srt=[];num=0
 for c in CHAPTERS:
  for a,b,tx in c['cues']:
   num+=1
   def stamp(t):return f'{int(t)//3600:02}:{int(t)%3600//60:02}:{int(t)%60:02},000'
   dummy=Image.new('RGB',(10,10));d=ImageDraw.Draw(dummy);lines=wrap(tx,1770,font(52,True),d)
   srt.append(f'{num}\n{stamp(start+a)} --> {stamp(start+b)}\n'+ '\n'.join(lines)+'\n')
   first=WORK/'overlay'/f'{start+a:04}.png';overlay(c,tx).save(first)
   for sec in range(a+1,b):shutil.copyfile(first,WORK/'overlay'/f'{start+sec:04}.png')
  start+=c['duration']
 # Quiet three-second source line, above the preserved narration caption.
 for sec in range(start-3,start):
  p=WORK/'overlay'/f'{sec:04}.png';end_credits(Image.open(p).convert('RGBA')).save(p)
 (HERE/'culture-fit-demo.ko.srt').write_text('\n'.join(srt),encoding='utf-8')
 (HERE/'storyboard.json').write_text(json.dumps(CHAPTERS,ensure_ascii=False,indent=2))
 c=next(c for c in CHAPTERS if c['id']=='authority')
 preview=canvas();ui=Image.open(HERE/'captures/10-joint-approval-entry.png').crop((300,0,1560,650)).resize((1560,805),Image.Resampling.LANCZOS)
 preview.paste(ui,(180,100));preview.alpha_composite(overlay(c,c['cues'][2][2]));preview.convert('RGB').save(HERE/'dark-ui-preview.png')
 out=['# 컬처핏 영상 스토리보드\n','최종 길이 3분 6초. 실제 UI 녹화와 Three.js 설명 도식을 연결한다.\n','| 구간 | 화면·행동 | 내레이션 및 자막 |','|---|---|---|'];start=0
 for c in CHAPTERS:
  a=f'{start//60:02}:{start%60:02}';start+=c['duration'];b=f'{start//60:02}:{start%60:02}'
  out.append(f"| {a}–{b} | {c['title']} | {'<br>'.join(t for _,_,t in c['cues'])} |")
 out+=['','Three.js 설명 도식: 00:00–00:16, 00:16–00:28, 00:47–00:55, 01:39–01:49, 02:51–03:06. 나머지는 실제 로컬 앱의 화면을 확대·재배치한 녹화다.','메타 설명·검증 한계는 README와 validation.json에서 확인한다.']
 (HERE/'storyboard.md').write_text('\n'.join(out))
 items=[];offset=0;min_margin=H;d=ImageDraw.Draw(Image.new('RGB',(10,10)))
 for c in CHAPTERS:
  for i,(a,b,tx) in enumerate(c['cues']):
   items.append({'id':f"voice-{c['id']}-{i}",'filename':f"voice-{c['id']}-{i}.mp3",'start_seconds':offset+a,'end_seconds':offset+b,'max_duration_seconds':b-a-.25,'subtitle':tx,'speech':tx.replace('검토봇 B','검토봇 비')})
   lines=wrap(tx,1770,font(52,True),d);y=917 if len(lines)==2 else 965
   for line in lines:min_margin=min(min_margin,H-y-font(52,True).getbbox(line)[3]);y+=58
  offset+=c['duration']
 (HERE/'narration-request.json').write_text(json.dumps({'language':'ko','style':'자연스러운 설명형 한국어, 따뜻하고 또렷하게, 과장 없이','total_duration_seconds':offset,'cues':items},ensure_ascii=False,indent=2))
 assert min_margin>=40
 credit_text='출처: Anthropic (2024) · Google (2025) · Li & Xie (2025)  |  음성: ElevenLabs'
 credit_bounds=font(24).getbbox(credit_text,anchor='ma');credit_top=860+credit_bounds[1];credit_bottom=860+credit_bounds[3]
 assert credit_bottom<900
 (HERE/'caption-layout.json').write_text(json.dumps({'end_credit_line':{'font':'Pretendard Regular','size_px':24,'top_px':credit_top,'bottom_px':credit_bottom,'caption_region_starts_px':912},'font':'Pretendard ExtraBold','size_px':52,'max_lines':2,'minimum_text_bottom_margin_px':min_margin,'width_px':W,'height_px':H,'note':'Measured glyph bounds; soft glow may extend beyond the glyph box.'},ensure_ascii=False,indent=2))
 print(HERE/'dark-ui-preview.png',flush=True)

if __name__=='__main__':build()
