"""방식 A: rembg 딥러닝 배경 제거 (기본 모델 isnet-anime)."""
from functools import lru_cache

from PIL import Image
from rembg import new_session, remove


@lru_cache(maxsize=None)
def _session(model: str):
    # 모델 가중치는 첫 호출 시 ~/.u2net 에 자동 다운로드됨 (네트워크 필요)
    return new_session(model)


def cutout_rembg(pil: Image.Image, model: str = "isnet-anime") -> Image.Image:
    # 알파 매팅은 방식 E(matting_method)로 분리됨
    result = remove(pil.convert("RGB"), session=_session(model))
    return result.convert("RGBA")
