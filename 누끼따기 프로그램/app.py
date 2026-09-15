"""캐릭터 배경 분리 비교 GUI (Gradio)."""
import json
import sys
import time
from pathlib import Path

import gradio as gr

from layer_editor import editor_value, layer_editor
from methods import cutout_matting, cutout_rembg
from outline_tool import outline_tool

OUT_DIR = Path(__file__).parent / "outputs"
OUT_DIR.mkdir(exist_ok=True)

LOG_MAX_LINES = 300

# B(알파 매팅) 경계 폭 프리셋: 폭이 좁을수록 경계가 단단하고(강함), 넓을수록 부드럽다(약함)
BAND_PRESETS = {"경계 강함 (5px)": 5, "경계 중간 (10px)": 10, "경계 약함 (20px)": 20}
BAND_CUSTOM = "사용자 설정"

BAND_HELP = (
    "알파 매팅이 투명도를 새로 계산하는 '윤곽선 주변 띠'의 두께입니다.\n"
    "isnet 마스크 윤곽선의 안쪽·바깥쪽으로 이 폭만큼(합쳐서 약 2배)을 '모름' 영역으로 두고, "
    "그 안에서만 주변 색을 보고 투명도를 계산합니다. 나머지는 마스크대로 100% / 0%입니다.\n\n"
    "• 강함 (5px): 마스크를 거의 그대로 믿음 — 윤곽 또렷, 빠름, 배경 섞임 적음\n"
    "• 중간 (10px): 무난한 기본값\n"
    "• 약함 (20px): 넓게 계산 — 머리카락·반투명 부분 복원에 유리하지만 느리고, "
    "배경색이 캐릭터와 비슷하면 섞일 수 있음\n\n"
    "실제 계산 범위는 진행 로그의 'trimap 미지 영역'에서 확인할 수 있습니다."
)

# 투명 영역이 보이도록 결과 이미지 뒤에 체크무늬 배경
CSS = """
.checker img {
  background-color: #fff;
  background-image: linear-gradient(45deg,#ccc 25%,transparent 25%),linear-gradient(-45deg,#ccc 25%,transparent 25%),
    linear-gradient(45deg,transparent 75%,#ccc 75%),linear-gradient(-45deg,transparent 75%,#ccc 75%);
  background-size: 20px 20px;
  background-position: 0 0,0 10px,10px -10px,-10px 0;
}
.log textarea { font-family: ui-monospace, Consolas, monospace; font-size: 12px; }
/* Gradio index.html의 body 배경은 OS 설정(prefers-color-scheme)만 따라가므로, 다크 테마일 때 body도 다크 배경으로 */
body.dark { background: var(--body-background-fill); }
.help-tip { display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 16px;
  margin-left: 6px; vertical-align: middle; border-radius: 4px; cursor: help; font-size: 11px; font-weight: 700; line-height: 1;
  border: 1px solid var(--border-color-primary); background: var(--background-fill-secondary); color: var(--body-text-color-subdued); }
.help-tip:hover, .help-tip:focus { color: var(--body-text-color); border-color: var(--color-accent); outline: none; }
.help-pop { position: fixed; z-index: 10000; max-width: min(360px, calc(100vw - 16px)); padding: 10px 12px;
  border-radius: 8px; border: 1px solid var(--border-color-primary); background: var(--background-fill-primary);
  color: var(--body-text-color); box-shadow: 0 6px 20px rgba(0, 0, 0, .18); font-size: 12px; line-height: 1.5;
  white-space: pre-line; pointer-events: none; }
"""

# 드롭다운 라벨은 텍스트만 받으므로, 페이지 로드 후 라벨 뒤에 "?" 상자를 붙인다.
# 라벨 조상(.block/.form)이 overflow:hidden이라 툴팁은 body에 두고 fixed 좌표로 띄움. Gradio가 라벨을 다시 그리면 다시 붙임.
HELP_JS = """
() => {
  const pop = document.createElement('div');
  pop.className = 'help-pop'; pop.id = 'band-help'; pop.setAttribute('role', 'tooltip'); pop.hidden = true;
  pop.textContent = __HELP__;
  document.body.appendChild(pop);
  const show = (tip) => {
    pop.hidden = false;
    const r = tip.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + 'px';
    pop.style.top = (r.bottom + 6 + h > window.innerHeight - 8 ? Math.max(8, r.top - h - 6) : r.bottom + 6) + 'px';
  };
  const hide = () => { pop.hidden = true; };
  const attach = () => {
    const label = document.querySelector('#band-choice [data-testid="block-info"]');
    if (!label || label.querySelector('.help-tip')) return;
    const tip = document.createElement('span');
    tip.className = 'help-tip'; tip.textContent = '?'; tip.tabIndex = 0;
    tip.setAttribute('aria-label', '매팅 경계 폭 설명'); tip.setAttribute('aria-describedby', 'band-help');
    tip.addEventListener('mouseenter', () => show(tip));
    tip.addEventListener('mouseleave', hide);
    tip.addEventListener('focus', () => show(tip));
    tip.addEventListener('blur', hide);
    tip.addEventListener('click', (e) => { e.preventDefault(); e.stopPropagation(); });
    label.appendChild(tip);
  };
  attach();
  new MutationObserver(attach).observe(document.body, { childList: true, subtree: true });
  window.addEventListener('scroll', hide, true);
}
""".replace("__HELP__", json.dumps(BAND_HELP, ensure_ascii=False))
# Gradio 6은 js를 <script> 본문으로 그대로 넣어 실행 → 함수 정의만으로는 호출되지 않으므로 즉시 실행 형태로 감쌈
HELP_JS = f"({HELP_JS.strip()})();"

# 기본 테마 = 다크. 주소에 __theme가 없으면 dark로 간주하고 주소에도 붙임(새로고침·설정 창에서도 다크로 인식).
# 설정 창에서 라이트를 고르면 __theme=light가 붙어 그 선택을 따름. Gradio가 system 모드로 dark 클래스를 떼면 다시 붙임.
DARK_JS = """
(() => {
  const url = new URL(window.location.href);
  if (url.searchParams.get('__theme')) return;
  url.searchParams.set('__theme', 'dark');
  history.replaceState(history.state, '', url);
  const ensure = () => { if (!document.body.classList.contains('dark')) document.body.classList.add('dark'); };
  ensure();
  new MutationObserver(ensure).observe(document.body, { attributes: true, attributeFilter: ['class'] });
})();
"""


def save(name, im):
    p = OUT_DIR / f"{name}.png"
    im.save(p, "PNG")
    return str(p)


def add_log(log, *msgs):
    lines = (log.splitlines() if log else []) + [f"[{time.strftime('%H:%M:%S')}] {m}" for m in msgs]
    return "\n".join(lines[-LOG_MAX_LINES:])


def toggle_band(choice):
    return gr.Slider(visible=choice == BAND_CUSTOM)


def run(img, model, band_choice, band_custom, log):
    # 제너레이터: 단계마다 로그와 끝난 결과를 바로 화면에 반영 (dict = 해당 컴포넌트만 갱신)
    log = add_log(log, "──── 분리 실행 ────")
    if img is None:
        yield {log_box: add_log(log, "오류: 이미지를 먼저 업로드하세요.")}
        raise gr.Error("이미지를 먼저 업로드하세요.")
    band = BAND_PRESETS.get(band_choice, int(band_custom))
    t0 = time.perf_counter()
    try:
        log = add_log(log, f"원본 {img.width}×{img.height}px | A 모델={model} | B 매팅 경계 폭={band}px ({band_choice})",
                      f"A: rembg({model}) 실행 중… (첫 실행이면 모델 다운로드로 오래 걸릴 수 있음)")
        yield {log_box: log}

        t = time.perf_counter()
        a = cutout_rembg(img, model)
        log = add_log(log, f"A 완료 ({time.perf_counter() - t:.1f}s)",
                      "B: 알파 매팅 실행 중… (isnet-anime 마스크 → trimap → 매팅, 큰 이미지일수록 느림)")
        yield {outs[0]: a, files[0]: save("A_rembg", a), log_box: log}

        t = time.perf_counter()
        notes = []
        b = cutout_matting(img, band, log=notes.append)
        log = add_log(log, *notes, f"B 완료 ({time.perf_counter() - t:.1f}s)", "레이어 편집기 데이터 준비 중…")
        yield {outs[1]: b, files[1]: save("B_matting", b), log_box: log}

        yield {editor: editor_value(a, b, img),
               log_box: add_log(log, f"완료 — 총 {time.perf_counter() - t0:.1f}s (결과 PNG는 outputs/ 에도 저장됨)")}
    except gr.Error:
        raise
    except Exception as ex:
        yield {log_box: add_log(log, f"오류: {type(ex).__name__}: {ex}")}
        raise gr.Error(f"처리 중 오류: {ex}")


def result_column(label, outs, files):
    with gr.Column(min_width=220):
        outs.append(gr.Image(label=label, type="pil", image_mode="RGBA", format="png", elem_classes="checker"))
        files.append(gr.File(label=f"{label} PNG 다운로드"))


with gr.Blocks(title="캐릭터 배경 분리 비교") as demo:
    gr.Markdown("# 캐릭터 배경 분리 비교\n이미지를 올리고 **분리 실행**을 누르면 A, B 결과와 레이어 편집기가 준비됩니다.")
    with gr.Row():
        with gr.Column(scale=2):
            src = gr.Image(label="원본", type="pil", image_mode="RGB")
            btn = gr.Button("분리 실행", variant="primary")
        with gr.Column(scale=1):
            model = gr.Dropdown(["isnet-anime", "u2net"], value="isnet-anime", label="A: rembg 모델")
            band_choice = gr.Dropdown([*BAND_PRESETS, BAND_CUSTOM], value="경계 중간 (10px)", label="B: 매팅 경계 폭",
                                      elem_id="band-choice")
            band_custom = gr.Slider(2, 30, value=10, step=1, label="B: 매팅 경계 폭 사용자 설정 (px, 클수록 느림)",
                                    visible=False)
            log_box = gr.Textbox(label="진행 로그", lines=12, max_lines=12, interactive=False,
                                 autoscroll=True, elem_classes="log")

    outs, files = [], []
    gr.Markdown("## 결과")
    with gr.Row():
        result_column("A: rembg", outs, files)
        result_column("B: 알파 매팅", outs, files)
    gr.Markdown("## A/B 레이어 편집기\n편집할 레이어를 고르고 지우개로 지우면 아래 레이어가 드러납니다. 레이어마다 불투명도를 따로 조절할 수 있습니다.")
    editor = layer_editor()
    gr.Markdown("## 테두리 강조\n투명 배경과 그림의 경계를 찾아 그림 바깥쪽에 테두리 픽셀을 추가합니다. 레이어 편집기의 현재 이미지나 외부 PNG를 가져와 쓸 수 있습니다.")
    outline_tool()

    band_choice.change(toggle_band, band_choice, band_custom)
    btn.click(run, [src, model, band_choice, band_custom, log_box], outs + files + [editor, log_box])

if __name__ == "__main__":
    # 주소 고정(포트가 사용 중이면 다른 포트로 넘어가지 않고 에러). 실행.bat은 --inbrowser로 준비되면 브라우저 자동 열기
    demo.launch(css=CSS, js=DARK_JS + HELP_JS, server_name="127.0.0.1", server_port=7860, inbrowser="--inbrowser" in sys.argv)
