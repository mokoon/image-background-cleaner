"""A/B 레이어 편집기: 원본·A·B를 완전히 겹친 레이어로 두고, 브러시/마법봉으로 원하는 부분만 골라 쓴다.
편집은 전부 브라우저 canvas에서 이뤄지고, Python은 이미지들을 data URL로 넘겨주기만 한다."""
import base64
import io
import json

import gradio as gr

HTML = """
<div class="le">
  <div class="bar">
    <b>편집 레이어</b>
    <label><input type="radio" name="le-layer" value="A" checked> A</label>
    <label><input type="radio" name="le-layer" value="B"> B</label>
    <label><input type="radio" name="le-layer" value="AB"> A+B</label>
    <label><input type="radio" name="le-layer" value="O"> 원본</label>
    <label><input type="radio" name="le-layer" value="ALL"> 일괄</label>
    <span class="sep"></span>
    <b>도구</b>
    <label><input type="radio" name="le-tool" value="brush" checked> 브러시</label>
    <label><input type="radio" name="le-tool" value="wand"> 마법봉</label>
  </div>
  <div class="bar brush-opts">
    <label><input type="radio" name="le-mode" value="erase" checked> 지우개</label>
    <label><input type="radio" name="le-mode" value="restore"> 복원</label>
    <span class="sep"></span>
    <label>브러시 <input type="range" class="size" min="2" max="200" value="30"> <span class="size-v">30</span>px</label>
  </div>
  <div class="bar wand-opts" hidden>
    <label>허용치 <input type="range" class="tol" min="0" max="255" value="32"> <span class="tol-v">32</span></label>
    <label><input type="checkbox" class="contig" checked> 연속</label>
    <label>샘플 <select class="sample"><option value="orig">원본 이미지</option><option value="view">보이는 화면</option></select></label>
    <span class="sep"></span>
    <button data-act="sel-erase">선택 영역 지우기 (Delete)</button>
    <button data-act="sel-restore">선택 영역 복원</button>
    <button data-act="deselect">선택 해제 (Esc)</button>
  </div>
  <div class="bar">
    <b>불투명도</b>
    <label>A <input type="range" class="op" data-layer="A" min="0" max="100" value="100"> <span class="op-v" data-layer="A">100</span>%</label>
    <label>B <input type="range" class="op" data-layer="B" min="0" max="100" value="100"> <span class="op-v" data-layer="B">100</span>%</label>
    <label>원본 <input type="range" class="op" data-layer="O" min="0" max="100" value="0"> <span class="op-v" data-layer="O">0</span>%</label>
    <span class="sep"></span>
    <label>원본 블러 <input type="range" class="blur-r" min="0" max="50" value="0">
      <input type="number" class="blur-n" min="0" max="100" value="0"> px</label>
  </div>
  <div class="bar">
    <button data-act="swap">A/B 순서 바꾸기</button>
    <button data-act="otop">원본 맨 아래로</button>
    <b class="order">위→아래: 원본 · A · B</b>
    <span class="sep"></span>
    <button data-act="undo">되돌리기 (Ctrl+Z)</button>
    <button data-act="reset">선택 레이어 초기화</button>
    <button data-act="save">PNG 저장</button>
  </div>
  <div class="bar">
    <b>보기</b>
    <button data-act="zoom-out">−</button>
    <span class="zoom-v">100%</span>
    <button data-act="zoom-in">+</button>
    <button data-act="zoom-fit">화면에 맞춤</button>
    <button data-act="zoom-100">100%</button>
    <span class="sep"></span>
    <span class="status"></span>
  </div>
  <p class="hint strong o-hint" hidden>원본 레이어는 반대로 동작: 지우개 = 원본을 100%로 드러내기, 복원 = 원본을 0%로 숨기기 (불투명도 슬라이더와 무관). 칠하지 않은 곳만 슬라이더를 따릅니다.</p>
  <p class="hint strong ab-hint" hidden>A+B: 지우개/복원/선택 영역 지우기·복원/초기화가 A와 B에 동시에 적용됩니다 (원본 레이어는 그대로).</p>
  <p class="hint strong all-hint" hidden>일괄: 지우개/Delete = A·B·원본 모두 0%로 / 복원 = A·B는 원래 결과로, 원본은 슬라이더를 따르는 상태로 되돌림.</p>
  <p class="hint">원본 블러: 누끼(A·B 편집 결과)가 있는 곳은 원본을 선명하게 두고 나머지 원본만 흐리게 합니다(원본 불투명도를 올려야 보임).</p>
  <p class="hint">단축키: Ctrl+Z 되돌리기 · Delete 선택 영역 지우기 · Esc/Ctrl+D 선택 해제 · Ctrl+휠 확대/축소 · Space+드래그 또는 휠 버튼 드래그 이동 · 마법봉 Shift+클릭 추가 / Alt+클릭 빼기. 화면에 보이는 그대로 PNG로 저장됩니다(선택 표시는 제외).</p>
  <p class="empty">분리 실행 후 레이어를 편집할 수 있습니다.</p>
  <canvas class="orig-copy" hidden></canvas>
  <div class="stage" hidden>
    <div class="inner">
      <canvas class="view"></canvas>
      <canvas class="overlay"></canvas>
      <div class="ring"></div>
    </div>
  </div>
</div>
"""

CSS = """
.le { display: flex; flex-direction: column; gap: 8px; }
.le [hidden] { display: none !important; }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.sep { width: 1px; height: 18px; background: var(--border-color-primary, #ccc); }
.bar button, .bar select { padding: 4px 12px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border-color-primary, #bbb);
  background: var(--button-secondary-background-fill, #f3f3f3); color: var(--body-text-color, #222); }
.bar button[data-act="save"] { background: #ea580c; border-color: #ea580c; color: #fff; font-weight: 600; }
.bar button[data-act="save"]:hover { background: #c2410c; border-color: #c2410c; }
.bar input[type="number"] { width: 4.5em; padding: 2px 4px; border-radius: 4px;
  border: 1px solid var(--border-color-primary, #bbb);
  background: var(--input-background-fill, #fff); color: var(--body-text-color, #222); }
.zoom-v { min-width: 3.5em; text-align: center; font-variant-numeric: tabular-nums; }
.status { font-size: 12px; opacity: .8; }
.hint { margin: 0; font-size: 12px; opacity: .7; }
.hint.strong { opacity: 1; font-weight: 600; }
.empty { margin: 0; padding: 24px 0; opacity: .7; }
.stage { position: relative; width: 100%; height: 70vh; overflow: auto; line-height: 0;
  border: 1px solid var(--border-color-primary, #ccc); border-radius: 6px; }
.inner { position: relative; margin: 0 auto; }
.view, .overlay { position: absolute; left: 0; top: 0; width: 100%; height: 100%; }
.view { touch-action: none; cursor: none;
  background-color: #fff;
  background-image: linear-gradient(45deg,#ccc 25%,transparent 25%),linear-gradient(-45deg,#ccc 25%,transparent 25%),
    linear-gradient(45deg,transparent 75%,#ccc 75%),linear-gradient(-45deg,transparent 75%,#ccc 75%);
  background-size: 20px 20px; background-position: 0 0,0 10px,10px -10px,-10px 0; }
.overlay, .ring { pointer-events: none; }
.pixel { image-rendering: pixelated; }
.ring { position: absolute; display: none; border-radius: 50%;
  border: 1px solid #000; box-shadow: 0 0 0 1px #fff; transform: translate(-50%, -50%); }
"""

JS = """
// A, B: 편집 가능한 레이어 canvas / O(원본): 원본 이미지 + 드러냄 마스크(R) + 숨김 마스크(H)
const HISTORY_MAX = 30;
const S = { A: null, B: null, R: null, H: null, t1: null, t2: null, t3: null, t4: null, orig: {}, origData: null,
  op: { A: 1, B: 1, O: 0 }, blur: 0, blurCache: null, top: 'A', oTop: true, sel: 'A', tool: 'brush', mode: 'erase', size: 30,
  tol: 32, contig: true, sample: 'orig', selArr: null, selCount: 0, selMask: null,
  hist: [], zoom: 1, last: null, pan: null, space: false, hover: false, opDrag: false, w: 0, h: 0 };
const NAMES = { A: 'A', B: 'B', O: '원본' };
const $ = (s) => element.querySelector(s);
const other = (k) => (k === 'A' ? 'B' : 'A');
const active = () => !!S.A && !$('.stage').hidden;

function loadImg(src) {
  return new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = src; });
}

function blank() {
  const c = document.createElement('canvas');
  c.width = S.w; c.height = S.h;
  return c;
}

async function init() {
  let v = props.value;
  if (typeof v === 'string') { try { v = JSON.parse(v); } catch (err) { v = null; } }
  const has = !!(v && v.a && v.b && v.o);
  $('.empty').hidden = has;
  $('.stage').hidden = !has;
  if (!has) { S.A = null; return; }
  const imgs = await Promise.all([loadImg(v.a), loadImg(v.b), loadImg(v.o)]);
  S.w = imgs[0].naturalWidth; S.h = imgs[0].naturalHeight;
  ['A', 'B'].forEach((k, i) => {
    const c = blank();
    c.getContext('2d').drawImage(imgs[i], 0, 0);
    S[k] = c; S.orig[k] = imgs[i];
  });
  S.orig.O = imgs[2];
  S.R = blank(); S.H = blank(); S.t1 = blank(); S.t2 = blank(); S.t3 = blank(); S.t4 = blank(); S.selMask = blank();
  // 원본 사본(DOM의 숨김 canvas): 마법봉 샘플용 + 테두리 강조에서 원본 레이어로 가져감
  const oCopy = $('.orig-copy');
  oCopy.width = S.w; oCopy.height = S.h;
  const oc = oCopy.getContext('2d', { willReadFrequently: true });
  oc.drawImage(imgs[2], 0, 0);
  S.origData = oc.getImageData(0, 0, S.w, S.h).data;
  for (const c of [$('.view'), $('.overlay')]) { c.width = S.w; c.height = S.h; }
  // 새 이미지가 들어오면 기본 상태로 시작: A가 위, 원본은 맨 위, 불투명도 A/B 100% · 원본 0%, 블러 0, 기록/선택 비움
  S.top = 'A'; S.oTop = true; S.op = { A: 1, B: 1, O: 0 }; S.blur = 0; S.blurCache = null;
  S.hist = []; S.selArr = null; S.selCount = 0;
  syncUI(); fit(); render(); status();
}

// 아래 → 위 순서
function stack() {
  const ab = [other(S.top), S.top];
  return S.oTop ? [...ab, 'O'] : ['O', ...ab];
}

function syncUI() {
  const check = (name, val) => {
    const el = element.querySelector('input[name="' + name + '"][value="' + val + '"]');
    if (el) el.checked = true;
  };
  check('le-layer', S.sel); check('le-tool', S.tool); check('le-mode', S.mode);
  $('.size').value = S.size; $('.size-v').textContent = S.size;
  $('.tol').value = S.tol; $('.tol-v').textContent = S.tol;
  $('.contig').checked = S.contig; $('.sample').value = S.sample;
  ['A', 'B', 'O'].forEach((k) => {
    const pct = Math.round(S.op[k] * 100);
    $('.op[data-layer="' + k + '"]').value = pct;
    $('.op-v[data-layer="' + k + '"]').textContent = pct;
  });
  $('.blur-r').value = Math.min(S.blur, 50); $('.blur-n').value = S.blur;
  $('.order').textContent = '위→아래: ' + stack().reverse().map((k) => NAMES[k]).join(' · ');
  $('[data-act="otop"]').textContent = S.oTop ? '원본 맨 아래로' : '원본 맨 위로';
  $('.brush-opts').hidden = S.tool !== 'brush';
  $('.wand-opts').hidden = S.tool !== 'wand';
  $('.o-hint').hidden = S.sel !== 'O';
  $('.ab-hint').hidden = S.sel !== 'AB';
  $('.all-hint').hidden = S.sel !== 'ALL';
  updateCursor();
}

function updateCursor() {
  $('.view').style.cursor = S.pan ? 'grabbing' : S.space ? 'grab' : S.tool === 'wand' ? 'crosshair' : 'none';
}

function status() {
  if (!S.A) return;
  $('.status').textContent = '되돌리기 ' + S.hist.length + '/' + HISTORY_MAX + ' · '
    + (S.selCount ? '선택 ' + S.selCount.toLocaleString() + 'px' : '선택 없음');
}

// ---------- 렌더링 ----------

// 가우시안 블러. 가장자리 1px 줄을 바깥으로 늘려 붙인 뒤 흐려서 이미지 테두리가 투명하게 번지지 않게 함
// (테두리 강조 outline_tool.py에도 같은 함수가 있음 — 두 컴포넌트가 독립 스크립트라 공유하지 않음)
function blurImage(img, w, h, radius) {
  const pad = Math.ceil(radius * 3);
  const big = document.createElement('canvas');
  big.width = w + pad * 2; big.height = h + pad * 2;
  const b = big.getContext('2d');
  b.drawImage(img, pad, pad);
  b.drawImage(img, 0, 0, w, 1, pad, 0, w, pad);
  b.drawImage(img, 0, h - 1, w, 1, pad, pad + h, w, pad);
  b.drawImage(img, 0, 0, 1, h, 0, pad, pad, h);
  b.drawImage(img, w - 1, 0, 1, h, pad + w, pad, pad, h);
  b.drawImage(img, 0, 0, 1, 1, 0, 0, pad, pad);
  b.drawImage(img, w - 1, 0, 1, 1, pad + w, 0, pad, pad);
  b.drawImage(img, 0, h - 1, 1, 1, 0, pad + h, pad, pad);
  b.drawImage(img, w - 1, h - 1, 1, 1, pad + w, pad + h, pad, pad);
  const out = document.createElement('canvas');
  out.width = w; out.height = h;
  const o = out.getContext('2d');
  o.filter = 'blur(' + radius + 'px)';
  o.drawImage(big, -pad, -pad);
  o.filter = 'none';
  return out;
}

// 원본 레이어에 쓸 이미지: 블러 0이면 원본 그대로, 아니면 누끼(A·B 편집 결과 모양)는 선명한 원본 + 나머지는 블러된 원본
function originalSource() {
  if (!S.blur) return S.orig.O;
  if (!S.blurCache || S.blurCache.r !== S.blur) S.blurCache = { r: S.blur, c: blurImage(S.orig.O, S.w, S.h, S.blur) };
  const m = S.t4.getContext('2d');
  m.globalCompositeOperation = 'source-over'; m.clearRect(0, 0, S.w, S.h);
  m.drawImage(S.A, 0, 0); m.drawImage(S.B, 0, 0);
  m.globalCompositeOperation = 'source-in'; m.drawImage(S.orig.O, 0, 0);
  m.globalCompositeOperation = 'source-over';
  const s = S.t3.getContext('2d');
  s.clearRect(0, 0, S.w, S.h);
  s.drawImage(S.blurCache.c, 0, 0);
  s.drawImage(S.t4, 0, 0);
  return S.t3;
}

// 원본 레이어 = (슬라이더 불투명도의 원본 − 숨김 마스크) 위에 (드러냄 마스크 모양의 100% 원본)
function originalLayer() {
  const src = originalSource();
  const t = S.t1.getContext('2d'), u = S.t2.getContext('2d');
  t.globalCompositeOperation = 'source-over'; t.clearRect(0, 0, S.w, S.h);
  t.globalAlpha = S.op.O; t.drawImage(src, 0, 0); t.globalAlpha = 1;
  t.globalCompositeOperation = 'destination-out'; t.drawImage(S.H, 0, 0);
  u.globalCompositeOperation = 'source-over'; u.clearRect(0, 0, S.w, S.h); u.drawImage(S.R, 0, 0);
  u.globalCompositeOperation = 'source-in'; u.drawImage(src, 0, 0);
  t.globalCompositeOperation = 'source-over'; t.drawImage(S.t2, 0, 0);
  return S.t1;
}

function render() {
  if (!S.A) return;
  const ctx = $('.view').getContext('2d');
  ctx.clearRect(0, 0, S.w, S.h);
  for (const k of stack()) {
    if (k === 'O') { ctx.drawImage(originalLayer(), 0, 0); continue; }
    ctx.globalAlpha = S.op[k];
    ctx.drawImage(S[k], 0, 0);
    ctx.globalAlpha = 1;
  }
}

// ---------- 편집 연산 (shape = 브러시 경로 {line, dot} 또는 선택 영역 {mask}) ----------

function paintShape(c, shape, style) {
  if (shape.mask) { c.drawImage(shape.mask, 0, 0); return; }
  c.lineCap = 'round'; c.lineWidth = S.size;
  c.strokeStyle = style; c.fillStyle = style;
  // 선(둥근 끝)과 점을 둘 다 그리면 복원(source-over)에서 반투명 픽셀이 두 번 겹쳐 원래보다 진해짐 → 하나만 그림
  if (shape.zero) c.fill(shape.dot); else c.stroke(shape.line);
}

function withOp(canvas, op, fn) {
  const c = canvas.getContext('2d');
  c.save(); c.globalCompositeOperation = op; fn(c); c.restore();
}

const draw = (canvas, shape) => withOp(canvas, 'source-over', (c) => paintShape(c, shape, '#000'));
const cut = (canvas, shape) => withOp(canvas, 'destination-out', (c) => paintShape(c, shape, '#000'));

// shape 영역에 원래 이미지를 다시 칠함
function drawOriginalIn(canvas, shape, img) {
  if (!shape.mask) {
    withOp(canvas, 'source-over', (c) => paintShape(c, shape, c.createPattern(img, 'no-repeat')));
    return;
  }
  const u = S.t2.getContext('2d');
  u.save();
  u.globalCompositeOperation = 'source-over'; u.clearRect(0, 0, S.w, S.h); u.drawImage(shape.mask, 0, 0);
  u.globalCompositeOperation = 'source-in'; u.drawImage(img, 0, 0);
  u.restore();
  withOp(canvas, 'source-over', (c) => c.drawImage(S.t2, 0, 0));
}

// 레이어 하나에 적용. kind: erase | restore | clear(원본 전용: 슬라이더를 따르는 상태로)
function applyTo(k, kind, shape) {
  if (k === 'O') {
    // 원본은 반대로: erase = 드러냄(100%), restore = 숨김(0%). 두 마스크는 서로 덮어씀
    if (kind === 'erase') { draw(S.R, shape); cut(S.H, shape); }
    else if (kind === 'restore') { draw(S.H, shape); cut(S.R, shape); }
    else { cut(S.R, shape); cut(S.H, shape); }
    return;
  }
  cut(S[k], shape);
  if (kind === 'restore') drawOriginalIn(S[k], shape, S.orig[k]);
}

function applyAction(kind, shape) {
  if (S.sel === 'ALL') {
    // 일괄 지우개 = A·B·원본 모두 0% / 일괄 복원 = A·B 원래대로 + 원본은 슬라이더를 따르게
    if (kind === 'erase') { applyTo('A', 'erase', shape); applyTo('B', 'erase', shape); applyTo('O', 'restore', shape); }
    else { applyTo('A', 'restore', shape); applyTo('B', 'restore', shape); applyTo('O', 'clear', shape); }
  } else if (S.sel === 'AB') {
    // A+B = A와 B에 같은 동작 (원본은 건드리지 않음)
    applyTo('A', kind, shape); applyTo('B', kind, shape);
  } else {
    applyTo(S.sel, kind, shape);
  }
  render();
}

function brushShape(p0, p1) {
  const line = new Path2D(); line.moveTo(p0.x, p0.y); line.lineTo(p1.x, p1.y);
  const dot = new Path2D(); dot.arc(p1.x, p1.y, S.size / 2, 0, Math.PI * 2);
  return { line, dot, zero: p0.x === p1.x && p0.y === p1.y };  // zero: 이동 없는 클릭 → 점만
}

// ---------- 되돌리기 ----------

function affected() {
  if (S.sel === 'ALL') return ['A', 'B', 'R', 'H'];
  if (S.sel === 'AB') return ['A', 'B'];
  return S.sel === 'O' ? ['R', 'H'] : [S.sel];
}

// 변경 직전 상태 저장: 바뀔 canvas만 복사 + 불투명도/블러/순서
function pushHistory(keys) {
  const entry = { layers: {}, op: { ...S.op }, blur: S.blur, top: S.top, oTop: S.oTop };
  for (const k of keys) {
    const c = blank();
    c.getContext('2d').drawImage(S[k], 0, 0);
    entry.layers[k] = c;
  }
  S.hist.push(entry);
  if (S.hist.length > HISTORY_MAX) S.hist.shift();
  status();
}

function undo() {
  const entry = S.hist.pop();
  if (!entry) return;
  for (const k in entry.layers) withOp(S[k], 'copy', (c) => c.drawImage(entry.layers[k], 0, 0));
  S.op = entry.op; S.blur = entry.blur; S.top = entry.top; S.oTop = entry.oTop;
  syncUI(); render(); status();
}

// ---------- 마법봉 선택 ----------

function wand(ix, iy, how) {
  if (ix < 0 || iy < 0 || ix >= S.w || iy >= S.h) return;
  const w = S.w, n = S.w * S.h, tol = S.tol;
  const src = S.sample === 'view'
    ? $('.view').getContext('2d').getImageData(0, 0, S.w, S.h).data
    : S.origData;
  const i0 = (iy * w + ix) * 4;
  const r0 = src[i0], g0 = src[i0 + 1], b0 = src[i0 + 2], a0 = src[i0 + 3];
  // 포토샵과 같은 방식: 채널별 차이가 모두 허용치 이하이면 같은 색
  const match = (p) => {
    const i = p * 4;
    return Math.abs(src[i] - r0) <= tol && Math.abs(src[i + 1] - g0) <= tol
      && Math.abs(src[i + 2] - b0) <= tol && Math.abs(src[i + 3] - a0) <= tol;
  };
  const hit = new Uint8Array(n);
  if (S.contig) {
    const stack = [iy * w + ix];
    hit[stack[0]] = 1;
    while (stack.length) {
      const p = stack.pop(), x = p % w;
      if (x > 0 && !hit[p - 1] && match(p - 1)) { hit[p - 1] = 1; stack.push(p - 1); }
      if (x < w - 1 && !hit[p + 1] && match(p + 1)) { hit[p + 1] = 1; stack.push(p + 1); }
      if (p >= w && !hit[p - w] && match(p - w)) { hit[p - w] = 1; stack.push(p - w); }
      if (p + w < n && !hit[p + w] && match(p + w)) { hit[p + w] = 1; stack.push(p + w); }
    }
  } else {
    for (let p = 0; p < n; p++) hit[p] = match(p) ? 1 : 0;
  }
  const cur = S.selArr;
  if (how === 'add' && cur) {
    for (let p = 0; p < n; p++) hit[p] |= cur[p];
  } else if (how === 'sub') {
    if (!cur) return;
    for (let p = 0; p < n; p++) hit[p] = cur[p] && !hit[p] ? 1 : 0;
  }
  setSelection(hit);
}

// 선택 배열 → 연산용 마스크(selMask) + 표시용 오버레이(파란 채움 + 흑백 점선 테두리)
function setSelection(arr) {
  const w = S.w, h = S.h, n = w * h;
  const mctx = S.selMask.getContext('2d'), octx = $('.overlay').getContext('2d');
  const m = mctx.createImageData(w, h), o = octx.createImageData(w, h);
  let count = 0;
  for (let p = 0; p < n; p++) {
    if (!arr[p]) continue;
    count++;
    const i = p * 4, x = p % w, y = (p - x) / w;
    m.data[i + 3] = 255;
    const edge = x === 0 || y === 0 || x === w - 1 || y === h - 1 || !arr[p - 1] || !arr[p + 1] || !arr[p - w] || !arr[p + w];
    if (edge) {
      const c = ((x + y) >> 2) & 1 ? 255 : 0;
      o.data[i] = c; o.data[i + 1] = c; o.data[i + 2] = c; o.data[i + 3] = 255;
    } else {
      o.data[i] = 30; o.data[i + 1] = 144; o.data[i + 2] = 255; o.data[i + 3] = 70;
    }
  }
  if (!count) { deselect(); return; }
  mctx.putImageData(m, 0, 0); octx.putImageData(o, 0, 0);
  S.selArr = arr; S.selCount = count;
  status();
}

function deselect() {
  S.selArr = null; S.selCount = 0;
  S.selMask.getContext('2d').clearRect(0, 0, S.w, S.h);
  $('.overlay').getContext('2d').clearRect(0, 0, S.w, S.h);
  status();
}

function applySelection(kind) {
  if (!S.selArr) return;
  pushHistory(affected());
  applyAction(kind, { mask: S.selMask });
}

// ---------- 확대/축소 ----------

// anchor(clientX/Y)가 가리키는 이미지 지점을 화면에서 같은 위치에 유지
function setZoom(z, anchor) {
  z = Math.min(16, Math.max(0.05, z));
  const st = $('.stage'), inner = $('.inner');
  const sr = st.getBoundingClientRect();
  const a = anchor || { clientX: sr.left + st.clientWidth / 2, clientY: sr.top + st.clientHeight / 2 };
  const ir = inner.getBoundingClientRect();
  const ix = S.zoom ? (a.clientX - ir.left) / S.zoom : 0, iy = S.zoom ? (a.clientY - ir.top) / S.zoom : 0;
  S.zoom = z;
  inner.style.width = S.w * z + 'px';
  inner.style.height = S.h * z + 'px';
  $('.view').classList.toggle('pixel', z >= 2);
  $('.overlay').classList.toggle('pixel', z >= 2);
  st.scrollLeft = inner.offsetLeft + ix * z - (a.clientX - sr.left);
  st.scrollTop = inner.offsetTop + iy * z - (a.clientY - sr.top);
  $('.zoom-v').textContent = Math.round(z * 100) + '%';
}

function fit() {
  const st = $('.stage');
  const aw = st.clientWidth - 2, ah = st.clientHeight - 2;
  setZoom(aw > 0 && ah > 0 ? Math.min(aw / S.w, ah / S.h) : 1);
  st.scrollLeft = 0; st.scrollTop = 0;
}

// ---------- 입력 ----------

function pos(e) {
  const r = $('.view').getBoundingClientRect();
  return { x: (e.clientX - r.left) * S.w / r.width, y: (e.clientY - r.top) * S.h / r.height };
}

function moveRing(e) {
  const ring = $('.ring');
  if (S.tool !== 'brush' || S.space || S.pan) { ring.style.display = 'none'; return; }
  const ir = $('.inner').getBoundingClientRect();
  const d = S.size * S.zoom;
  ring.style.display = 'block';
  ring.style.width = d + 'px'; ring.style.height = d + 'px';
  ring.style.left = (e.clientX - ir.left) + 'px'; ring.style.top = (e.clientY - ir.top) + 'px';
}

const onView = (e) => e.target.classList && e.target.classList.contains('view') && S.A;

element.addEventListener('mousedown', (e) => { if (onView(e) && e.button === 1) e.preventDefault(); });  // 휠 버튼 자동 스크롤 방지

element.addEventListener('pointerdown', (e) => {
  if (!onView(e)) return;
  e.preventDefault();
  e.target.setPointerCapture(e.pointerId);
  if (S.space || e.button === 1) {
    const st = $('.stage');
    S.pan = { x: e.clientX, y: e.clientY, l: st.scrollLeft, t: st.scrollTop };
    updateCursor(); moveRing(e);
    return;
  }
  if (e.button !== 0) return;
  const p = pos(e);
  if (S.tool === 'wand') {
    wand(Math.floor(p.x), Math.floor(p.y), e.shiftKey ? 'add' : e.altKey ? 'sub' : 'new');
    return;
  }
  pushHistory(affected());  // 한 번의 드래그 = 되돌리기 1단계
  S.last = p;
  applyAction(S.mode, brushShape(p, p));
});
element.addEventListener('pointermove', (e) => {
  if (!onView(e)) return;
  S.hover = true;
  if (S.pan) {
    const st = $('.stage');
    st.scrollLeft = S.pan.l - (e.clientX - S.pan.x);
    st.scrollTop = S.pan.t - (e.clientY - S.pan.y);
    return;
  }
  moveRing(e);
  if (!S.last) return;
  const p = pos(e);
  applyAction(S.mode, brushShape(S.last, p));
  S.last = p;
});
const endPointer = () => { S.last = null; if (S.pan) { S.pan = null; updateCursor(); } };
element.addEventListener('pointerup', endPointer);
element.addEventListener('pointercancel', endPointer);
element.addEventListener('pointerout', (e) => { if (onView(e)) { S.hover = false; $('.ring').style.display = 'none'; } });

element.addEventListener('wheel', (e) => {
  if (!active() || !e.ctrlKey || !$('.stage').contains(e.target)) return;
  e.preventDefault();
  setZoom(S.zoom * (e.deltaY < 0 ? 1.25 : 0.8), e);
}, { passive: false });

element.addEventListener('change', (e) => {
  const t = e.target;
  if (t.name === 'le-layer') { S.sel = t.value; syncUI(); }
  if (t.name === 'le-tool') { S.tool = t.value; syncUI(); }
  if (t.name === 'le-mode') S.mode = t.value;
  if (t.classList.contains('contig')) S.contig = t.checked;
  if (t.classList.contains('sample')) S.sample = t.value;
  if (t.classList.contains('op') || t.classList.contains('blur-r') || t.classList.contains('blur-n')) S.opDrag = false;
  if (t.classList.contains('blur-n')) t.value = S.blur;  // 범위 밖/빈 값은 실제 적용값으로 되돌림
});
element.addEventListener('input', (e) => {
  const t = e.target;
  if (t.classList.contains('size')) { S.size = +t.value; $('.size-v').textContent = S.size; }
  if (t.classList.contains('tol')) { S.tol = +t.value; $('.tol-v').textContent = S.tol; }
  if (t.classList.contains('op') && S.A) {
    if (!S.opDrag) { pushHistory([]); S.opDrag = true; }  // 슬라이더 한 번 조작 = 되돌리기 1단계
    S.op[t.dataset.layer] = +t.value / 100;
    $('.op-v[data-layer="' + t.dataset.layer + '"]').textContent = t.value;
    render();
  }
  if ((t.classList.contains('blur-r') || t.classList.contains('blur-n')) && S.A) {
    if (t.value === '' || !Number.isFinite(+t.value)) return;
    const v = Math.min(100, Math.max(0, Math.round(+t.value)));
    if (!S.opDrag) { pushHistory([]); S.opDrag = true; }
    S.blur = v;
    if (t.classList.contains('blur-r')) $('.blur-n').value = v; else $('.blur-r').value = Math.min(v, 50);
    render();  // 실시간 반영
  }
});
element.addEventListener('click', (e) => {
  const act = e.target.dataset && e.target.dataset.act;
  if (!act || !S.A) return;
  if (act === 'swap') { pushHistory([]); S.top = other(S.top); syncUI(); render(); }
  if (act === 'otop') { pushHistory([]); S.oTop = !S.oTop; syncUI(); render(); }
  if (act === 'undo') undo();
  if (act === 'sel-erase') applySelection('erase');
  if (act === 'sel-restore') applySelection('restore');
  if (act === 'deselect') deselect();
  if (act === 'zoom-in') setZoom(S.zoom * 1.25);
  if (act === 'zoom-out') setZoom(S.zoom * 0.8);
  if (act === 'zoom-fit') fit();
  if (act === 'zoom-100') setZoom(1);
  if (act === 'reset') {
    pushHistory(affected());
    const layers = S.sel === 'ALL' ? ['A', 'B', 'O'] : S.sel === 'AB' ? ['A', 'B'] : [S.sel];
    for (const k of layers) {
      if (k === 'O') {
        S.R.getContext('2d').clearRect(0, 0, S.w, S.h);
        S.H.getContext('2d').clearRect(0, 0, S.w, S.h);
      } else {
        withOp(S[k], 'copy', (c) => c.drawImage(S.orig[k], 0, 0));
      }
    }
    render();
  }
  if (act === 'save') {
    const a = document.createElement('a');
    a.href = $('.view').toDataURL('image/png'); a.download = 'AB_edited.png'; a.click();
  }
});

// 단축키: 편집기에 이미지가 있을 때만, 글 입력 중이 아닐 때만
const typing = (t) => t && (t.isContentEditable || (t.tagName === 'TEXTAREA' && !t.readOnly)
  || (t.tagName === 'INPUT' && !['range', 'radio', 'checkbox', 'button'].includes(t.type)));
document.addEventListener('keydown', (e) => {
  if (!active() || typing(e.target)) return;
  const key = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && key === 'z') { e.preventDefault(); undo(); }
  else if ((e.ctrlKey || e.metaKey) && key === 'd') { e.preventDefault(); deselect(); }
  else if (e.key === 'Delete' || e.key === 'Backspace') { if (S.selArr) { e.preventDefault(); applySelection('erase'); } }
  else if (e.key === 'Escape') deselect();
  else if (e.key === ' ' && S.hover) { e.preventDefault(); if (!S.space) { S.space = true; updateCursor(); $('.ring').style.display = 'none'; } }
});
document.addEventListener('keyup', (e) => { if (e.key === ' ' && S.space) { S.space = false; updateCursor(); } });

watch('value', init);
init();
"""


def _data_url(im) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def editor_value(a, b, original) -> str:
    return json.dumps({"a": _data_url(a), "b": _data_url(b), "o": _data_url(original)})


def layer_editor() -> gr.HTML:
    return gr.HTML(value="", html_template=HTML, css_template=CSS, js_on_load=JS,
                   container=True, padding=True, elem_id="layer-editor")
