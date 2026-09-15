"""방식 B: 알파 매팅 (pymatting closed-form) — trimap은 isnet-anime 마스크에서 생성."""
import cv2
import numpy as np
from PIL import Image
from pymatting import estimate_alpha_cf, estimate_foreground_ml, stack_images
from rembg import remove

from .rembg_method import _session


def cutout_matting(pil: Image.Image, band: int = 10, log=None) -> Image.Image:
    log = log or (lambda msg: None)  # 진행 로그 콜백 (GUI 로그 창용)
    rgb = pil.convert("RGB")
    # 가정: trimap의 기준 마스크는 isnet-anime 결과 (애니 캐릭터 대상이므로)
    mask = np.array(remove(rgb, session=_session("isnet-anime"), only_mask=True).convert("L"))

    # 마스크 경계 안팎 band px를 "모름(128)" 영역으로 두는 trimap
    k = np.ones((3, 3), np.uint8)
    fg = cv2.erode((mask > 240).astype(np.uint8), k, iterations=band)
    bg = cv2.erode((mask < 10).astype(np.uint8), k, iterations=band)
    trimap = np.full(mask.shape, 0.5)
    trimap[fg == 1] = 1.0
    trimap[bg == 1] = 0.0

    # 확실한 전경/배경이 둘 다 없으면 매팅 불가 → 기준 마스크를 그대로 알파로 사용
    if not fg.any() or not bg.any():
        log("B: 기준 마스크에 확실한 전경/배경이 없어 매팅 생략 → isnet-anime 마스크 그대로 사용")
        return Image.fromarray(np.dstack([np.array(rgb), mask]), "RGBA")

    unknown = int((trimap == 0.5).sum())
    log(f"B: trimap 미지 영역 {unknown:,}px ({unknown / trimap.size:.1%}) 매팅 중…")
    img = np.array(rgb) / 255.0
    alpha = np.clip(estimate_alpha_cf(img, trimap), 0, 1)
    fg_rgb = estimate_foreground_ml(img, alpha)  # 경계의 배경색 번짐 제거
    out = (stack_images(fg_rgb, alpha) * 255).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")
