"""64x64 게임 프레임을 이미지로 렌더링한다.

VLM에게 보내기 위해 프레임을 확대된 PNG 이미지로 변환.
ARC-AGI 16색 팔레트 사용.
"""

import base64
import io

import numpy as np
import numpy.typing as npt

# ARC-AGI 16색 팔레트 (index 0-15 → RGB)
ARC_PALETTE = [
    (255, 255, 255),  #  0: white
    (204, 204, 204),  #  1: off-white
    (153, 153, 153),  #  2: light-gray
    (102, 102, 102),  #  3: gray
    (51, 51, 51),     #  4: dark-gray
    (0, 0, 0),        #  5: black
    (229, 58, 163),   #  6: magenta
    (255, 123, 204),  #  7: pink
    (249, 60, 49),    #  8: red
    (30, 147, 255),   #  9: blue
    (136, 216, 241),  # 10: light-blue
    (255, 220, 0),    # 11: yellow
    (255, 133, 27),   # 12: orange
    (146, 18, 49),    # 13: maroon
    (79, 204, 48),    # 14: green
    (163, 86, 214),   # 15: purple
]


def frame_to_rgb(
    frame: npt.NDArray[np.int_],
    scale: int = 8,
) -> npt.NDArray[np.uint8]:
    """프레임을 RGB 이미지로 변환한다.

    Args:
        frame: 64x64 int array (values 0-15)
        scale: 확대 배율 (8이면 512x512)

    Returns:
        (H*scale, W*scale, 3) uint8 RGB array
    """
    h, w = frame.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for val, color in enumerate(ARC_PALETTE):
        mask = frame == val
        rgb[mask] = color

    # 확대
    if scale > 1:
        rgb = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)

    return rgb


def frame_to_png_bytes(
    frame: npt.NDArray[np.int_],
    scale: int = 8,
) -> bytes:
    """프레임을 PNG 바이트로 변환한다."""
    rgb = frame_to_rgb(frame, scale)

    # PIL 없이 간단한 PPM → PNG 변환은 어려우므로 PIL 사용
    try:
        from PIL import Image
    except ImportError:
        # PIL 없으면 raw PPM 포맷
        return _to_ppm(rgb)

    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def frame_to_base64(
    frame: npt.NDArray[np.int_],
    scale: int = 8,
) -> str:
    """프레임을 base64 인코딩된 PNG로 변환한다. (API 전송용)"""
    png_bytes = frame_to_png_bytes(frame, scale)
    return base64.standard_b64encode(png_bytes).decode("utf-8")


def _to_ppm(rgb: npt.NDArray[np.uint8]) -> bytes:
    """RGB array를 PPM 바이트로 변환 (PIL fallback)."""
    h, w, _ = rgb.shape
    header = f"P6\n{w} {h}\n255\n".encode()
    return header + rgb.tobytes()
