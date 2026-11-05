import * as THREE from '../motion/work/three.module.js';

// These are explanatory product diagrams, not recordings of agent execution.
// Every frame is rendered by Three.js in a fixed 1920 × 1080 coordinate space.
const W = 1920, H = 1080;
const WHITE = '#f5f7fa', MUTED = '#83909d', CYAN = '#53ffd8', YELLOW = '#ffe16a';
const DURATIONS = { problem: 16, connections: 8, cta: 13 };
await document.fonts.load('700 60px MotionSans');
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
renderer.setSize(W, H);
renderer.setPixelRatio(1);
renderer.setClearColor('#030609', 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);
const camera = new THREE.OrthographicCamera(-W / 2, W / 2, H / 2, -H / 2, 0.1, 1000);
camera.position.z = 500;
const scenes = {}, tracks = [], texts = [], rings = [], lines = [];
const p = (x, y, z = 0) => new THREE.Vector3(x - W / 2, H / 2 - y, z);
const ease = x => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };

function group(scene, start = 0, end = 100) {
  const g = new THREE.Group();
  scene.add(g);
  g.userData = { start, end };
  tracks.push(g);
  return g;
}
function material(color, opacity = 1) {
  const m = new THREE.MeshBasicMaterial({ color, transparent: true, opacity, depthWrite: false, depthTest: false });
  m.userData.base = opacity;
  return m;
}
function text(parent, str, x, y, size = 40, color = WHITE, weight = 600, glow = false, container = null) {
  const c = document.createElement('canvas'), probe = c.getContext('2d');
  probe.font = `${weight} ${size}px MotionSans`;
  const width = Math.ceil(probe.measureText(str).width + 80), height = Math.ceil(size * 1.8 + 40);
  c.width = width * 2; c.height = height * 2;
  const ctx = c.getContext('2d');
  ctx.scale(2, 2);
  ctx.font = `${weight} ${size}px MotionSans`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = color;
  if (glow) {
    ctx.shadowColor = color; ctx.shadowBlur = 13; ctx.globalAlpha = 0.65;
    ctx.fillText(str, width / 2, height / 2); ctx.shadowBlur = 0; ctx.globalAlpha = 1;
  }
  ctx.fillText(str, width / 2, height / 2);
  const m = ctx.measureText(str), padding = glow ? 14 : 1;
  texts.push({ parent, str, x, y, size, container, glow,
    left: x - m.actualBoundingBoxLeft - padding, right: x + m.actualBoundingBoxRight + padding,
    top: y - m.actualBoundingBoxAscent - padding, bottom: y + m.actualBoundingBoxDescent + padding });
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false });
  mat.userData.base = 1;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), mat);
  mesh.position.copy(p(x, y, 14)); parent.add(mesh);
  return mesh;
}
function stroke(parent, x1, y1, x2, y2, color = MUTED, width = 2, opacity = 1, glow = false, decorative = false) {
  if (!decorative) lines.push({ parent, x1, y1, x2, y2, halfWidth: width * (glow ? 7 : 1) / 2 });
  const length = Math.hypot(x2 - x1, y2 - y1), angle = Math.atan2(-(y2 - y1), x2 - x1);
  for (const [scale, alpha] of (glow ? [[7, 0.025], [4, 0.05], [2, 0.12], [1, 1]] : [[1, 1]])) {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(length, width * scale), material(color, opacity * alpha));
    mesh.position.copy(p((x1 + x2) / 2, (y1 + y2) / 2, 2)); mesh.rotation.z = angle; parent.add(mesh);
  }
}
function ring(parent, id, x, y, radius, color = CYAN, width = 2, glow = true, decorative = false) {
  if (!decorative) rings.push({ parent, id, x, y, radius: radius + width / 2 + (glow ? 10 : 0) });
  for (const [spread, alpha] of (glow ? [[10, 0.025], [5, 0.05], [2, 0.12], [0, 1]] : [[0, 1]])) {
    const mesh = new THREE.Mesh(new THREE.RingGeometry(radius - width / 2 - spread, radius + width / 2 + spread, 96), material(color, alpha));
    mesh.position.copy(p(x, y, 4)); parent.add(mesh);
  }
}
function dot(parent, x, y, radius, color = CYAN) {
  const mesh = new THREE.Mesh(new THREE.CircleGeometry(radius, 32), material(color));
  mesh.position.copy(p(x, y, 6)); parent.add(mesh); return mesh;
}
function arrow(parent, x1, y1, x2, y2, color = CYAN, glow = true) {
  stroke(parent, x1, y1, x2, y2, color, 2, 0.8, glow);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  stroke(parent, x2, y2, x2 - 12 * Math.cos(angle - 0.5), y2 - 12 * Math.sin(angle - 0.5), color, 2, 0.9);
  stroke(parent, x2, y2, x2 - 12 * Math.cos(angle + 0.5), y2 - 12 * Math.sin(angle + 0.5), color, 2, 0.9);
}
function particle(parent, x1, y1, x2, y2, delay, color = CYAN) {
  const mesh = dot(parent, x1, y1, 3.5, color);
  mesh.userData.motion = { x1, y1, x2, y2, delay };
}
function human(parent, x, y, color = WHITE) {
  ring(parent, '', x, y - 15, 12, color, 2, false, true);
  [[-25, 29, -25, 16], [25, 29, 25, 16], [-25, 16, -9, 4], [25, 16, 9, 4], [-25, 29, 25, 29]].forEach(([a, b, c, d]) => stroke(parent, x + a, y + b, x + c, y + d, color, 2, 1, false, true));
}
function bot(parent, x, y, color = WHITE) {
  [[-29, -21, 29, -21], [29, -21, 29, 24], [29, 24, -29, 24], [-29, 24, -29, -21], [0, -21, 0, -35]].forEach(([a, b, c, d]) => stroke(parent, x + a, y + b, x + c, y + d, color, 2, 1, false, true));
  dot(parent, x, y - 39, 3, color); dot(parent, x - 11, y, 3.5, color); dot(parent, x + 11, y, 3.5, color);
}
function documentIcon(parent, x, y, color = WHITE) {
  [[-20, -25, 20, -25], [20, -25, 20, 25], [20, 25, -20, 25], [-20, 25, -20, -25], [-11, -9, 11, -9], [-11, 2, 11, 2], [-11, 13, 4, 13]].forEach(([a, b, c, d]) => stroke(parent, x + a, y + b, x + c, y + d, color, 2, 1, false, true));
}
function background(name, label) {
  const scene = new THREE.Scene(); scenes[name] = scene;
  const coords = [];
  for (let x = 80; x < W; x += 80) coords.push(...p(x, 0).toArray(), ...p(x, H).toArray());
  for (let y = 40; y < 900; y += 80) coords.push(...p(0, y).toArray(), ...p(W, y).toArray());
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(coords, 3));
  scene.add(new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: '#253348', transparent: true, opacity: 0.16 })));
  text(scene, label, 1630, 76, 22, MUTED, 500);
  return scene;
}

// Shared context and owner-to-agent authority are deliberately separate edges.
{
  const s = background('problem', 'Decision authority');
  let g = group(s, 0.1);
  text(g, 'Same information. Different authority.', 960, 204, 62, WHITE, 700);
  g = group(s, 0.6);
  ring(g, 'shared-context', 960, 350, 48, CYAN, 2);
  documentIcon(g, 960, 350);
  text(g, 'Shared context', 960, 470, 30, WHITE, 550);
  for (const [x, label, delay] of [[570, 'Agent A', 1], [1350, 'Agent B', 1.4]]) {
    g = group(s, delay);
    ring(g, label, x, 615, 62, CYAN, 2);
    bot(g, x, 615);
    text(g, label, x, 737, 34, WHITE, 650);
  }
  g = group(s, 2.1);
  arrow(g, 906, 385, 632, 551, '#9fb7c4', false);
  arrow(g, 1014, 385, 1288, 551, '#9fb7c4', false);
  particle(g, 898, 390, 640, 546, 2.1, CYAN);
  particle(g, 1022, 390, 1280, 546, 2.1, CYAN);
  for (const [x, label, delay, from, to] of [[210, 'Owner A', 4.2, 290, 475], [1710, 'Owner B', 5.1, 1630, 1445]]) {
    g = group(s, delay);
    ring(g, label, x, 615, 50, YELLOW, 2);
    human(g, x, 615);
    text(g, label, x, 737, 34, WHITE, 650);
    arrow(g, from, 615, to, 615, YELLOW);
    text(g, 'Delegate', (from + to) / 2, 550, 24, YELLOW, 600);
    particle(g, from, 615, to - Math.sign(to - from) * 12, 615, delay, YELLOW);
  }
  g = group(s, 6.7);
  ring(g, 'decision', 960, 615, 60, YELLOW, 2);
  text(g, '?', 960, 615, 66, YELLOW, 650, false, 'decision');
  arrow(g, 664, 615, 864, 615, YELLOW);
  arrow(g, 1256, 615, 1056, 615, YELLOW);
  g = group(s, 8.2);
  text(g, 'Who can decide?', 960, 785, 60, YELLOW, 700, true);
  text(s, 'Illustrated example · Culture-Fit', 960, 870, 24, MUTED, 450);
}

{
  const s = background('connections', 'Connect your stack');
  let g = group(s, 0.1);
  text(g, 'Connect your agent workflow.', 960, 214, 64, WHITE, 700);
  g = group(s, 0.4);
  ring(g, 'agent-clients', 320, 520, 75, CYAN, 2);
  bot(g, 320, 520);
  text(g, 'Agent clients', 320, 682, 36, WHITE, 650);
  g = group(s, 0.7);
  stroke(g, 440, 520, 730, 520, CYAN, 2, 0.7, true);
  stroke(g, 730, 350, 730, 690, CYAN, 2, 0.7, true);
  for (const [label, y, delay] of [['MCP', 350, 1], ['A2A', 520, 1.5], ['Skill', 690, 2]]) {
    g = group(s, delay);
    arrow(g, 730, y, 805, y, CYAN);
    ring(g, `protocol-${label}`, 900, y, 62, CYAN, 2);
    text(g, label, 900, y, 34, WHITE, 650, false, `protocol-${label}`);
    stroke(g, 995, y, 1070, y, CYAN, 2, 0.75, true);
  }
  g = group(s, 2.4);
  stroke(g, 1070, 350, 1070, 690, CYAN, 2, 0.7, true);
  arrow(g, 1070, 520, 1395, 520, CYAN);
  particle(g, 1080, 520, 1380, 520, 2.4, CYAN);
  g = group(s, 2.8);
  ring(g, 'culture-fit', 1540, 520, 100, CYAN, 2);
  text(g, 'CF', 1540, 520, 70, WHITE, 700, false, 'culture-fit');
  text(g, 'Culture-Fit', 1540, 682, 43, WHITE, 700);
  text(g, 'Human-in-the-Loop', 1540, 750, 27, CYAN, 550);
  text(s, 'Connection architecture · Culture-Fit', 960, 870, 24, MUTED, 450);
}

{
  const s = background('cta', 'Build with Culture-Fit');
  let g = group(s, 0.15);
  text(g, 'Culture-Fit', 960, 245, 104, WHITE, 750);
  text(g, 'Human-in-the-Loop (HITL)', 960, 375, 48, CYAN, 650, true);
  g = group(s, 1.5);
  text(g, 'For developers everywhere.', 960, 520, 52, WHITE, 700);
  g = group(s, 2.4);
  text(g, 'MIT open source', 960, 615, 36, YELLOW, 650, true);
  g = group(s, 6.2);
  text(g, 'The right person. At the right moment.', 960, 700, 42, WHITE, 650);
  g = group(s, 3.4);
  text(g, 'github.com/Ontology0/hanium-arbiter', 960, 778, 34, WHITE, 550);
  text(g, 'culture-fit-demo-production.up.railway.app/download', 960, 835, 25, MUTED, 450);
}

window.renderAt = (sceneName, time) => {
  const scene = scenes[sceneName];
  if (!scene) throw new Error(`Unknown scene: ${sceneName}`);
  for (const g of tracks) {
    if (g.parent !== scene) continue;
    const { start, end } = g.userData;
    const opacity = ease((time - start) / 0.7) * (1 - ease((time - end) / 0.5));
    g.visible = opacity > 0;
    g.position.y = -10 * (1 - opacity);
    g.traverse(o => {
      if (o.material?.userData.base !== undefined) o.material.opacity = o.material.userData.base * opacity;
      if (o.userData.motion) {
        const m = o.userData.motion, progress = (Math.max(0, time - m.delay) * 0.32) % 1;
        o.position.copy(p(m.x1 + (m.x2 - m.x1) * progress, m.y1 + (m.y2 - m.y1) * progress, 6));
      }
    });
  }
  renderer.render(scene, camera);
  return true;
};
const describe = ({ parent, ...data }) => {
  let s = parent; while (s.parent) s = s.parent;
  return { scene: Object.keys(scenes).find(key => scenes[key] === s), start: parent.userData.start ?? 0, end: parent.userData.end ?? 100, moving: tracks.includes(parent), ...data };
};
window.motionLayout = () => ({ texts: texts.map(describe), rings: rings.map(describe), lines: lines.map(describe) });
window.motionMeta = { width: W, height: H, fps: 30, durations: DURATIONS, threeRevision: THREE.REVISION, font: 'Pretendard 1.3.9', subtitleSafeAreaTop: 900 };
window.renderAt(new URLSearchParams(location.search).get('scene') || 'problem', Number(new URLSearchParams(location.search).get('t') || 13));
window.motionReady = true;
