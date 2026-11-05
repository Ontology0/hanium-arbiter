import * as THREE from './work/three.module.js';

// Native Three.js meshes, lines and CanvasTexture text planes; fixed 1080p coordinate space.
const W=1920,H=1080, WHITE='#f4f6fa', MUTED='#8b98aa', CYAN='#53ffd8', YELLOW='#ffe16a';
await document.fonts.load('700 60px MotionSans');
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,preserveDrawingBuffer:true});
renderer.setSize(W,H); renderer.setPixelRatio(1); renderer.setClearColor('#05070b',1);
renderer.outputColorSpace=THREE.SRGBColorSpace; document.body.appendChild(renderer.domElement);
const camera=new THREE.OrthographicCamera(-W/2,W/2,H/2,-H/2,0.1,1000); camera.position.z=500;
const scenes={}, tracks=[], textBounds=[], ringBounds=[], strokeBounds=[];
const point=(x,y,z=0)=>new THREE.Vector3(x-W/2,H/2-y,z);
const ease=x=>{x=Math.max(0,Math.min(1,x));return x*x*(3-2*x)};
function group(parent,start=0,end=100){const g=new THREE.Group(); parent.add(g);g.userData={start,end};tracks.push(g);return g}
function mat(color,opacity=1){const m=new THREE.MeshBasicMaterial({color,transparent:true,opacity,depthWrite:false,depthTest:false});m.userData.base=opacity;return m}
function text(parent,str,x,y,size=40,color=WHITE,weight=600,glow=false){
 const c=document.createElement('canvas'),measure=c.getContext('2d');measure.font=`${weight} ${size}px MotionSans`;
 const width=Math.ceil(measure.measureText(str).width+80),height=Math.ceil(size*1.8+40); c.width=width*2;c.height=height*2;
 const ctx=c.getContext('2d');ctx.scale(2,2);ctx.font=`${weight} ${size}px MotionSans`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillStyle=color;
 if(glow){ctx.shadowColor=color;ctx.shadowBlur=14;ctx.globalAlpha=.7;ctx.fillText(str,width/2,height/2);ctx.shadowBlur=0;ctx.globalAlpha=1;}
 ctx.fillText(str,width/2,height/2); const metrics=ctx.measureText(str); const padding=glow?14:1; textBounds.push({parent,str,x,y,size,glow,left:x-metrics.actualBoundingBoxLeft-padding,right:x+metrics.actualBoundingBoxRight+padding,top:y-metrics.actualBoundingBoxAscent-padding,bottom:y+metrics.actualBoundingBoxDescent+padding}); const tex=new THREE.CanvasTexture(c);tex.colorSpace=THREE.SRGBColorSpace;
 const material=new THREE.MeshBasicMaterial({map:tex,transparent:true,depthWrite:false,depthTest:false});material.userData.base=1;
 const mesh=new THREE.Mesh(new THREE.PlaneGeometry(width,height),material);mesh.position.copy(point(x,y,12));parent.add(mesh);return mesh;
}
function stroke(parent,x1,y1,x2,y2,color=MUTED,width=2,opacity=1,glow=false){
 strokeBounds.push({parent,x1,y1,x2,y2,halfWidth:width*(glow?7:1)/2}); const length=Math.hypot(x2-x1,y2-y1),angle=Math.atan2(-(y2-y1),x2-x1);let mesh;
 for(const [mul,a] of (glow?[[7,.025],[4,.05],[2,.12],[1,1]]:[[1,1]])){
 mesh=new THREE.Mesh(new THREE.PlaneGeometry(length,width*mul),mat(color,opacity*a));mesh.position.copy(point((x1+x2)/2,(y1+y2)/2,2));mesh.rotation.z=angle;parent.add(mesh);}
 return mesh;
}
function ring(parent,x,y,r,color=CYAN,width=2,glow=true){
 ringBounds.push({parent,x,y,radius:r+width/2+(glow?10:0)});
 for(const [extra,a] of(glow?[[10,.025],[5,.05],[2,.12],[0,1]]:[[0,1]])){
 const mesh=new THREE.Mesh(new THREE.RingGeometry(r-width/2-extra,r+width/2+extra,96),mat(color,a));mesh.position.copy(point(x,y,4));parent.add(mesh);}
}
function dot(parent,x,y,r,color=CYAN){const m=new THREE.Mesh(new THREE.CircleGeometry(r,24),mat(color));m.position.copy(point(x,y,6));parent.add(m);return m}
function arrow(parent,x1,y1,x2,y2,color=CYAN){stroke(parent,x1,y1,x2,y2,color,2,.7,true);const a=Math.atan2(y2-y1,x2-x1);stroke(parent,x2,y2,x2-12*Math.cos(a-.5),y2-12*Math.sin(a-.5),color,2,.8);stroke(parent,x2,y2,x2-12*Math.cos(a+.5),y2-12*Math.sin(a+.5),color,2,.8);}
function particle(parent,x1,y1,x2,y2,delay=0,color=CYAN){const m=dot(parent,x1,y1,4,color);m.userData.motion={x1,y1,x2,y2,delay};return m}
function human(parent,x,y,color=WHITE){ring(parent,x,y-18,16,color,2,false);stroke(parent,x-30,y+35,x-30,y+19,color,2);stroke(parent,x+30,y+35,x+30,y+19,color,2);stroke(parent,x-30,y+19,x-12,y+7,color,2);stroke(parent,x+30,y+19,x+12,y+7,color,2);stroke(parent,x-30,y+35,x+30,y+35,color,2);}
function bot(parent,x,y,color=WHITE){stroke(parent,x-29,y-21,x+29,y-21,color,2);stroke(parent,x+29,y-21,x+29,y+24,color,2);stroke(parent,x+29,y+24,x-29,y+24,color,2);stroke(parent,x-29,y+24,x-29,y-21,color,2);stroke(parent,x,y-21,x,y-35,color,2);dot(parent,x,y-39,4,color);dot(parent,x-11,y,4,color);dot(parent,x+11,y,4,color);}
function background(name,label){const s=new THREE.Scene();scenes[name]=s;
 const coords=[];for(let x=80;x<W;x+=80)coords.push(...point(x,0).toArray(),...point(x,H).toArray());for(let y=40;y<H;y+=80)coords.push(...point(0,y).toArray(),...point(W,y).toArray());
 const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(coords,3));const grid=new THREE.LineSegments(geo,new THREE.LineBasicMaterial({color:'#253348',transparent:true,opacity:.21}));s.add(grid);
 stroke(s,130,116,1790,116,'#394355',1,.65);text(s,'CULTURE-FIT',260,78,22,WHITE,650);text(s,label,1580,78,21,MUTED,500);return s;
}

// Intro: the three research stages are explicitly labels, not performance claims.
{
 const s=background('intro','기획에서 현재 구현까지');
 let g=group(s,.15);text(g,'컬처핏',960,224,90,WHITE,750);text(g,'Culture-Fit',960,335,40,CYAN,500,true);
 g=group(s,.9);text(g,'생성형 AI의 검증·관리',960,420,40,WHITE,550);
 const xs=[365,960,1555],titles=['초기 기획','7월 개발보고','현재 구현'],a=['문화·역사 고증','GitHub RAG · 지식 충돌','에이전트 권한'],b=['KG-RAG','수용 · 거부 · 유보','사람의 결정'];
 for(let i=0;i<3;i++){g=group(s,3+i*2.7);ring(g,xs[i],548,18,i===2?CYAN:YELLOW,2);dot(g,xs[i],548,5,i===2?CYAN:YELLOW);text(g,titles[i],xs[i],632,29,i===2?CYAN:YELLOW,650,true);text(g,a[i],xs[i],710,36,WHITE,650);text(g,b[i],xs[i],773,30,MUTED,500);if(i){arrow(g,xs[i-1]+60,548,xs[i]-60,548,'#70879d');particle(g,xs[i-1]+65,548,xs[i]-65,548,3+i*2.7);}}
 g=group(s,12.2);text(g,'재사용 가능한 연결 계층',960,842,42,CYAN,650,true);
}
// Why now: distinct tool/data and inter-agent standards connect the ecosystem.
{
 const s=background('why-now','왜 지금, 결정권인가');let g=group(s,.15);text(g,'도구에서 에이전트까지',960,224,66,WHITE,700);
 g=group(s,.55);ring(g,340,475,72,CYAN,2);stroke(g,315,450,305,450,WHITE,2);stroke(g,305,450,305,500,WHITE,2);stroke(g,305,500,315,500,WHITE,2);stroke(g,365,450,375,450,WHITE,2);stroke(g,375,450,375,500,WHITE,2);stroke(g,375,500,365,500,WHITE,2);stroke(g,332,494,348,456,WHITE,2);text(g,'도구·데이터',340,620,37,WHITE,650);
 g=group(s,.9);ring(g,960,475,72,CYAN,2);bot(g,960,475,WHITE);text(g,'에이전트',960,620,37,WHITE,650);
 g=group(s,1.3);text(g,'MCP · 2024',650,365,31,CYAN,650,true);arrow(g,460,475,840,475,CYAN);stroke(g,460,475,471,469,CYAN,2);stroke(g,460,475,471,481,CYAN,2);particle(g,470,475,830,475,1.3);text(g,'도구·데이터 연결',650,540,26,MUTED,500);
 g=group(s,2.5);ring(g,1580,475,72,YELLOW,2);bot(g,1580,475,WHITE);text(g,'다른 에이전트',1580,620,37,WHITE,650);
 g=group(s,3);text(g,'A2A · 2025',1270,365,31,YELLOW,650,true);arrow(g,1080,475,1460,475,YELLOW);stroke(g,1080,475,1091,469,YELLOW,2);stroke(g,1080,475,1091,481,YELLOW,2);particle(g,1090,475,1450,475,3,YELLOW);text(g,'작업·상태 교환',1270,540,26,MUTED,500);
 g=group(s,6.3);text(g,'누가 결정할 수 있죠?',960,764,64,YELLOW,700,true);
 g=group(s,.2);text(g,'Anthropic 2024 · Google 2025 · Li & Xie 2025',960,855,20,MUTED,500);
}
// Overview: state transitions distinguish a promise from transmission and a decision.
{
 const s=background('overview','대화와 결정의 상태');let g=group(s,.15);text(g,'약속에서 결정까지',960,230,62,WHITE,700);
 const xs=[330,750,1170,1590],labels=['확인 약속','질문 전달','사람의 결정','실행 근거'],sub=['대화에 남은 의도','전달 상태와 담당자','판단과 승인 기록','다음 행동의 책임'];
 for(let i=0;i<4;i++){g=group(s,.6+i*1.25);text(g,`0${i+1}`,xs[i],366,24,MUTED,500);ring(g,xs[i],490,73,i===2?YELLOW:CYAN,2);if(i===2)human(g,xs[i],485,YELLOW);else if(i===0){ring(g,xs[i],485,26,WHITE,2,false);stroke(g,xs[i],485,xs[i],466,WHITE,2);stroke(g,xs[i],485,xs[i]+16,494,WHITE,2);}else {for(let j=0;j<3;j++)stroke(g,xs[i]-24,472+j*15,xs[i]+24-(j===2?12:0),472+j*15,WHITE,2)}
 text(g,labels[i],xs[i],640,43,WHITE,650);text(g,sub[i],xs[i],720,27,MUTED,500);if(i){arrow(g,xs[i-1]+120,490,xs[i]-120,490,'#718796');particle(g,xs[i-1]+125,490,xs[i]-125,490,.6+i*1.25)}}
}
// Authority: a local operator records the approvals. This is not remote identity verification.
{
 const s=background('authority','권한과 공동 승인');let g=group(s,.1);text(g,'누가 승인할 수 있을까요?',960,209,62,WHITE,700);text(g,'로컬 운영자 입력',960,287,26,MUTED,500);
 const ys=[420,660];
 for(let i=0;i<2;i++){g=group(s,.5+i*.5);ring(g,350,ys[i],62,'#526477',1,false);human(g,350,ys[i]-4,WHITE);text(g,`사람 ${i?'B':'A'}`,350,ys[i]+126,31,WHITE,600);arrow(g,455,ys[i],735,ys[i],'#6b7f91');particle(g,465,ys[i],725,ys[i],i*.5);text(g,'위임',586,ys[i]-48,24,MUTED,500);ring(g,840,ys[i],62,'#526477',1,false);bot(g,840,ys[i],i?CYAN:WHITE);text(g,i?'검토봇 B':'배포봇 A',840,ys[i]+126,31,i?CYAN:WHITE,650);arrow(g,965,ys[i],1370,535,i?CYAN:'#728396');particle(g,975,ys[i],1360,535,i*.5,i?CYAN:WHITE);}
 g=group(s,1.2);ring(g,1510,535,88,YELLOW,2);text(g,'배포 승인',1510,534,30,WHITE,650);
 g=group(s,2.2,4.7);text(g,'권한 충돌',1130,770,49,YELLOW,700,true);
 g=group(s,5.3);text(g,'공동 승인 기록',1130,745,32,WHITE,600);text(g,'2 / 2',1510,745,32,CYAN,650,true);
 g=group(s,6.5);stroke(g,965,660,1370,535,CYAN,4,1,true);ring(g,840,660,62,CYAN,2);particle(g,975,657,1360,538,6.5);
 g=group(s,7.5);text(g,'검토봇 B 담당',1130,827,48,CYAN,700,true);
}
{
 const s=background('outro','전 세계 개발자를 위한 오픈소스 연결 계층');let g=group(s,.15);text(g,'Culture-Fit',960,226,76,WHITE,700);
 text(g,'Human-in-the-Loop (HITL)',960,326,36,WHITE,600);
 const xs=[330,750,1170,1590],labels=['원문 근거','위임 권한','사람의 결정','다음 행동'];
 for(let i=0;i<4;i++){g=group(s,1+i*.9);ring(g,xs[i],420,22,i===2?YELLOW:CYAN,2);dot(g,xs[i],420,5,i===2?YELLOW:CYAN);text(g,labels[i],xs[i],520,36,WHITE,600);if(i){arrow(g,xs[i-1]+68,420,xs[i]-68,420,'#718796');particle(g,xs[i-1]+73,420,xs[i]-73,420,1+i*.9)}}
 g=group(s,5.1);text(g,'필요한 순간,',960,670,70,WHITE,700);
 g=group(s,6.6);text(g,'필요한 사람에게',960,780,74,CYAN,750,true);
}

window.renderAt=(sceneName,time)=>{
 const scene=scenes[sceneName];if(!scene)throw new Error('Unknown scene: '+sceneName);
 for(const g of tracks){if(g.parent!==scene)continue;const {start,end}=g.userData;const opacity=ease((time-start)/.7)*(1-ease((time-end)/.5));g.visible=opacity>0;g.position.y=-12*(1-opacity);
 g.traverse(o=>{if(o.material&&o.material.userData.base!==undefined)o.material.opacity=o.material.userData.base*opacity;if(o.userData.motion){const m=o.userData.motion,p=((Math.max(0,time-m.delay)*.32)%1);o.position.copy(point(m.x1+(m.x2-m.x1)*p,m.y1+(m.y2-m.y1)*p,6));}})}
 renderer.render(scene,camera);return true;
};
const describe=({parent,...b})=>{let s=parent;while(s.parent)s=s.parent;return {scene:Object.keys(scenes).find(k=>scenes[k]===s),start:parent.userData.start??0,end:parent.userData.end??100,...b}};
window.motionLayout=()=>({texts:textBounds.map(describe),rings:ringBounds.map(describe),strokes:strokeBounds.map(describe)});
window.motionMeta={width:W,height:H,fps:30,durations:{intro:16,"why-now":12,overview:8,authority:10,outro:15},threeRevision:THREE.REVISION};
window.renderAt(new URLSearchParams(location.search).get('scene')||'intro',Number(new URLSearchParams(location.search).get('t')||14));window.motionReady=true;
