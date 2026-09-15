"""테두리 강조: 투명 배경과 그림의 경계를 알파 임계값으로 구분해, 그림 바깥쪽에 지정한 색·두께의 테두리 픽셀을 추가한다.
레이어 편집기 canvas를 바로 읽어야 하므로 처리는 전부 브라우저에서 한다."""
import gradio as gr

HTML = """
<div class="ol">
  <div class="bar">
    <button data-act="from-editor">레이어 편집기 현재 이미지 가져오기</button>
    <button data-act="from-file">외부 이미지 가져오기</button>
    <input type="file" class="file" accept="image/*" hidden>
    <span class="src-info"></span>
  </div>
  <div class="bar">
    <label>테두리 색 <input type="color" class="color" value="#000000"></label>
    <span class="sep"></span>
    <label>두께 <input type="range" class="thick-r" min="1" max="50" value="1">
      <input type="number" class="thick-n" min="1" max="500" value="1"> px</label>
    <span class="sep"></span>
    <label>투명도 임계값 <input type="range" class="thr-r" min="1" max="255" value="128">
      <input type="number" class="thr-n" min="1" max="255" value="128"></label>
    <span class="sep"></span>
    <button data-act="save">PNG 저장</button>
  </div>
  <div class="bar orig-row" hidden>
    <b>원본 레이어</b>
    <label>불투명도 <input type="range" class="orig-r" min="0" max="100" value="0">
      <input type="number" class="orig-n" min="0" max="100" value="0"> %</label>
    <span class="sep"></span>
    <label>블러 <input type="range" class="blur-r" min="0" max="50" value="0">
      <input type="number" class="blur-n" min="0" max="100" value="0"> px</label>
    <span class="sub">편집된 이미지 아래에 원본을 깔아 확인합니다. 블러는 누끼 모양 밖의 원본만 흐리게 합니다 (테두리 인식에는 영향 없음)</span>
  </div>
  <p class="hint">알파(불투명도, 0~255)가 임계값 이상인 픽셀은 그림, 미만은 투명 배경으로 보고, 그림 바깥쪽 투명 영역에 두께만큼 테두리 픽셀을 추가합니다. 임계값을 낮추면 옅은 가장자리까지 그림으로 인식해 테두리가 바깥으로 밀려납니다. 이미지 가장자리에 닿은 부분의 테두리는 잘릴 수 있습니다. 화면에 보이는 그대로(원본 레이어 포함) PNG로 저장됩니다.</p>
  <p class="msg" hidden></p>
  <p class="empty">위 버튼으로 이미지를 가져오면 테두리가 적용된 미리보기가 표시됩니다.</p>
  <div class="stage" hidden><canvas class="view"></canvas></div>
  <span class="status"></span>
</div>
"""

CSS = """
.ol { display: flex; flex-direction: column; gap: 8px; }
.ol [hidden] { display: none !important; }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.sep { width: 1px; height: 18px; background: var(--border-color-primary, #ccc); }
.bar button { padding: 4px 12px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border-color-primary, #bbb);
  background: var(--button-secondary-background-fill, #f3f3f3); color: var(--body-text-color, #222); }
.bar button[data-act="save"] { background: #ea580c; border-color: #ea580c; color: #fff; font-weight: 600; }
.bar button[data-act="save"]:hover { background: #c2410c; border-color: #c2410c; }
.bar input[type="number"] { width: 4.5em; padding: 2px 4px; border-radius: 4px;
  border: 1px solid var(--border-color-primary, #bbb);
  background: var(--input-background-fill, #fff); color: var(--body-text-color, #222); }
.bar input[type="color"] { width: 36px; height: 24px; padding: 0; border: none; background: none; cursor: pointer; vertical-align: middle; }
.src-info, .status, .sub { font-size: 12px; opacity: .8; }
.hint { margin: 0; font-size: 12px; opacity: .7; }
.msg { margin: 0; font-size: 13px; font-weight: 600; color: #ea580c; }
.empty { margin: 0; padding: 24px 0; opacity: .7; }
.stage { align-self: flex-start; max-width: 100%; line-height: 0; overflow: auto;
  border: 1px solid var(--border-color-primary, #ccc); border-radius: 6px; }
.view { max-width: 100%; max-height: 70vh;
  background-color: #fff;
  background-image: linear-gradient(45deg,#ccc 25%,transparent 25%),linear-gradient(-45deg,#ccc 25%,transparent 25%),
    linear-gradient(45deg,transparent 75%,#ccc 75%),linear-gradient(-45deg,transparent 75%,#ccc 75%);
  background-size: 20px 20px; background-position: 0 0,0 10px,10px -10px,-10px 0; }
"""

JS = """
// src: 테두리 계산 대상(가져온 이미지 픽셀) / out: 테두리 적용 결과 / orig: 원본 레이어(편집기에서 가져온 경우만)
const T = { w: 0, h: 0, src: null, srcCanvas: null, out: null, orig: null, origOp: 0, blur: 0, blurCache: null,
  t3: null, t4: null, dist: null, distThr: -1, shape: 0, color: '#000000', thick: 1, thr: 128, pending: 0 };
const $ = (s) => element.querySelector(s);

function msg(text) {
  const m = $('.msg');
  m.textContent = text || '';
  m.hidden = !text;
}

function newCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

function copyCanvas(source, w, h) {
  const c = newCanvas(w, h);
  c.getContext('2d').drawImage(source, 0, 0);
  return c;
}

// 가져온 이미지(편집기 canvas 또는 외부 이미지)를 원본 픽셀로 보관. orig가 있으면 원본 레이어로 사용
function loadSource(source, w, h, label, orig) {
  const c = newCanvas(w, h);
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(source, 0, 0);
  T.w = w; T.h = h; T.srcCanvas = c; T.src = ctx.getImageData(0, 0, w, h); T.dist = null; T.distThr = -1;
  T.out = newCanvas(w, h); T.t3 = newCanvas(w, h); T.t4 = newCanvas(w, h);
  T.orig = orig || null;
  // 가져올 때마다 원본 레이어는 불투명도 0% · 블러 0에서 시작
  T.origOp = 0; T.blur = 0; T.blurCache = null;
  $('.orig-r').value = 0; $('.orig-n').value = 0; $('.blur-r').value = 0; $('.blur-n').value = 0;
  $('.orig-row').hidden = !T.orig;
  const view = $('.view');
  view.width = w; view.height = h;
  $('.empty').hidden = true;
  $('.stage').hidden = false;
  $('.src-info').textContent = label + ' · ' + w + '×' + h + 'px';
  msg('');
  schedule();
}

function fromEditor() {
  const ed = document.querySelector('#layer-editor');
  const view = ed && ed.querySelector('canvas.view');
  const stage = ed && ed.querySelector('.stage');
  if (!view || !stage || stage.hidden || !view.width) {
    msg('레이어 편집기에 이미지가 없습니다. 먼저 분리 실행을 해주세요.');
    return;
  }
  // 편집기가 보관한 원본 사본을 복사해 둠 (이후 편집기에서 새로 분리 실행해도 영향 없게)
  const oc = ed.querySelector('canvas.orig-copy');
  const orig = oc && oc.width === view.width && oc.height === view.height ? copyCanvas(oc, oc.width, oc.height) : null;
  loadSource(view, view.width, view.height, '레이어 편집기', orig);  // 편집기 화면에 보이는 합성 그대로(선택 표시 제외)
}

// 1차원 제곱 거리 변환 (Felzenszwalb & Huttenlocher)
function edt1d(f, n, d, v, z) {
  let k = 0;
  v[0] = 0; z[0] = -Infinity; z[1] = Infinity;
  for (let q = 1; q < n; q++) {
    let s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
    while (s <= z[k]) {
      k--;
      s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
    }
    k++; v[k] = q; z[k] = s; z[k + 1] = Infinity;
  }
  k = 0;
  for (let q = 0; q < n; q++) {
    while (z[k + 1] < q) k++;
    d[q] = (q - v[k]) * (q - v[k]) + f[v[k]];
  }
}

// 각 픽셀에서 가장 가까운 그림 픽셀까지의 제곱 유클리드 거리 (그림 픽셀 = 0)
function distanceField(mask, w, h) {
  const INF = 1e20, n = Math.max(w, h);
  const grid = new Float64Array(w * h);
  for (let p = 0; p < w * h; p++) grid[p] = mask[p] ? 0 : INF;
  const f = new Float64Array(n), d = new Float64Array(n), v = new Int32Array(n), z = new Float64Array(n + 1);
  for (let x = 0; x < w; x++) {
    for (let y = 0; y < h; y++) f[y] = grid[y * w + x];
    edt1d(f, h, d, v, z);
    for (let y = 0; y < h; y++) grid[y * w + x] = d[y];
  }
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) f[x] = grid[row + x];
    edt1d(f, w, d, v, z);
    for (let x = 0; x < w; x++) grid[row + x] = d[x];
  }
  return grid;
}

function schedule() {
  if (T.pending) return;
  T.pending = setTimeout(() => { T.pending = 0; process(); }, 0);  // 슬라이더 연속 입력은 한 번으로 묶음
}

function process() {
  if (!T.src) return;
  const t0 = performance.now();
  const w = T.w, h = T.h, n = w * h, a = T.src.data;
  // 거리 필드는 임계값에만 의존 → 임계값이 바뀔 때만 다시 계산 (색·두께 변경은 칠하기만)
  if (T.distThr !== T.thr) {
    const mask = new Uint8Array(n);
    let shape = 0;
    for (let p = 0; p < n; p++) if (a[p * 4 + 3] >= T.thr) { mask[p] = 1; shape++; }
    T.shape = shape;
    T.dist = shape && shape < n ? distanceField(mask, w, h) : null;
    T.distThr = T.thr;
  }
  const rgb = parseInt(T.color.slice(1), 16);
  const cr = (rgb >> 16) & 255, cg = (rgb >> 8) & 255, cb = rgb & 255;
  const lim = (T.thick + 0.5) * (T.thick + 0.5);  // +0.5: 1px에서도 대각선까지 끊김 없이
  const out = new ImageData(w, h), o = out.data;
  let added = 0;
  for (let p = 0; p < n; p++) {
    const i = p * 4, d = T.dist ? T.dist[p] : 0;
    if (d > 0 && d <= lim) {
      // 테두리 픽셀: 임계값 미만의 옅은 원본 픽셀은 테두리 색 위에 겹쳐 가장자리가 자연스럽게 이어지게 함
      const sa = a[i + 3] / 255;
      o[i] = a[i] * sa + cr * (1 - sa);
      o[i + 1] = a[i + 1] * sa + cg * (1 - sa);
      o[i + 2] = a[i + 2] * sa + cb * (1 - sa);
      o[i + 3] = 255;
      added++;
    } else {
      o[i] = a[i]; o[i + 1] = a[i + 1]; o[i + 2] = a[i + 2]; o[i + 3] = a[i + 3];
    }
  }
  T.out.getContext('2d').putImageData(out, 0, 0);
  compose();
  if (!T.shape) msg('임계값 이상인(그림으로 인식되는) 픽셀이 없습니다. 임계값을 낮춰보세요.');
  else if (T.shape === n) msg('투명한 부분이 없어 테두리를 추가할 곳이 없습니다. 배경이 투명한 PNG를 사용하세요.');
  else msg('');
  $('.status').textContent = '그림 픽셀 ' + T.shape.toLocaleString() + ' · 테두리 ' + added.toLocaleString()
    + 'px 추가 · ' + Math.round(performance.now() - t0) + 'ms';
}

// 가우시안 블러. 가장자리 1px 줄을 바깥으로 늘려 붙인 뒤 흐려서 이미지 테두리가 투명하게 번지지 않게 함
// (레이어 편집기 layer_editor.py에도 같은 함수가 있음 — 두 컴포넌트가 독립 스크립트라 공유하지 않음)
function blurImage(img, w, h, radius) {
  const pad = Math.ceil(radius * 3);
  const big = newCanvas(w + pad * 2, h + pad * 2);
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
  const out = newCanvas(w, h);
  const o = out.getContext('2d');
  o.filter = 'blur(' + radius + 'px)';
  o.drawImage(big, -pad, -pad);
  o.filter = 'none';
  return out;
}

// 원본 레이어에 쓸 이미지: 블러 0이면 원본 그대로, 아니면 누끼(가져온 편집 이미지 모양)는 선명한 원본 + 나머지는 블러된 원본
function originalSource() {
  if (!T.blur) return T.orig;
  if (!T.blurCache || T.blurCache.r !== T.blur) T.blurCache = { r: T.blur, c: blurImage(T.orig, T.w, T.h, T.blur) };
  const m = T.t4.getContext('2d');
  m.globalCompositeOperation = 'source-over'; m.clearRect(0, 0, T.w, T.h);
  m.drawImage(T.srcCanvas, 0, 0);
  m.globalCompositeOperation = 'source-in'; m.drawImage(T.orig, 0, 0);
  m.globalCompositeOperation = 'source-over';
  const s = T.t3.getContext('2d');
  s.clearRect(0, 0, T.w, T.h);
  s.drawImage(T.blurCache.c, 0, 0);
  s.drawImage(T.t4, 0, 0);
  return T.t3;
}

// 화면 = 원본 레이어(블러·불투명도 적용, 아래) + 테두리 적용 결과(위)
function compose() {
  if (!T.out) return;
  const ctx = $('.view').getContext('2d');
  ctx.clearRect(0, 0, T.w, T.h);
  if (T.orig && T.origOp > 0) {
    ctx.globalAlpha = T.origOp;
    ctx.drawImage(originalSource(), 0, 0);
    ctx.globalAlpha = 1;
  }
  ctx.drawImage(T.out, 0, 0);
}

const readInt = (s, lo, hi) => {
  if (s === '' || !Number.isFinite(+s)) return null;
  return Math.min(hi, Math.max(lo, Math.round(+s)));
};

element.addEventListener('input', (e) => {
  const t = e.target, c = t.classList;
  if (c.contains('color')) {
    T.color = t.value;
  } else if (c.contains('thick-r') || c.contains('thick-n')) {
    const v = readInt(t.value, 1, 500);
    if (v === null) return;
    T.thick = v;
    if (c.contains('thick-r')) $('.thick-n').value = v; else $('.thick-r').value = Math.min(v, 50);
  } else if (c.contains('thr-r') || c.contains('thr-n')) {
    const v = readInt(t.value, 1, 255);
    if (v === null) return;
    T.thr = v;
    if (c.contains('thr-r')) $('.thr-n').value = v; else $('.thr-r').value = v;
  } else if (c.contains('orig-r') || c.contains('orig-n')) {
    const v = readInt(t.value, 0, 100);
    if (v === null) return;
    T.origOp = v / 100;
    if (c.contains('orig-r')) $('.orig-n').value = v; else $('.orig-r').value = v;
    compose();  // 원본 불투명도는 합성만 다시 (테두리 재계산 불필요)
    return;
  } else if (c.contains('blur-r') || c.contains('blur-n')) {
    const v = readInt(t.value, 0, 100);
    if (v === null) return;
    T.blur = v;
    if (c.contains('blur-r')) $('.blur-n').value = v; else $('.blur-r').value = Math.min(v, 50);
    compose();  // 블러도 합성만 다시 (실시간 반영)
    return;
  } else {
    return;
  }
  schedule();
});
// 숫자 칸에서 벗어날 때 범위 밖/빈 값은 실제 적용값으로 되돌림
element.addEventListener('change', (e) => {
  const c = e.target.classList;
  if (c.contains('thick-n')) e.target.value = T.thick;
  if (c.contains('thr-n')) e.target.value = T.thr;
  if (c.contains('orig-n')) e.target.value = Math.round(T.origOp * 100);
  if (c.contains('blur-n')) e.target.value = T.blur;
  if (c.contains('file')) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file), img = new Image();
    img.onload = () => { loadSource(img, img.naturalWidth, img.naturalHeight, '외부 이미지: ' + file.name, null); URL.revokeObjectURL(url); };
    img.onerror = () => { msg('이미지를 읽을 수 없습니다: ' + file.name); URL.revokeObjectURL(url); };
    img.src = url;
    e.target.value = '';  // 같은 파일을 다시 골라도 change가 발생하도록
  }
});
element.addEventListener('click', (e) => {
  const act = e.target.dataset && e.target.dataset.act;
  if (act === 'from-editor') fromEditor();
  if (act === 'from-file') $('.file').click();
  if (act === 'save') {
    if (!T.src) { msg('먼저 이미지를 가져오세요.'); return; }
    const link = document.createElement('a');
    link.href = $('.view').toDataURL('image/png'); link.download = 'outlined.png'; link.click();
  }
});
"""


def outline_tool() -> gr.HTML:
    return gr.HTML(value="", html_template=HTML, css_template=CSS, js_on_load=JS,
                   container=True, padding=True, elem_id="outline-tool")
