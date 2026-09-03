"""카드뉴스 첫 페이지 스타일 이미지 제작.

받은 사진을 정사각형으로 자르고, 아래쪽에 어두운 그라데이션을 깔고,
글을 대표하는 문구를 얹는다. 100% 내가 만든 이미지라 저작권 문제가 없다.
(단, 재료가 되는 사진은 직접 찍었거나 사용권이 있는 것이어야 한다)
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import log, settings

# 윈도우/리눅스(깃허브 액션) 어느 쪽에서 돌아도 한글이 나오게
FONT_CANDIDATES = {
    "bold": [
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ],
    "regular": [
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ],
}


def _cfg() -> dict:
    return settings().get("card", {})


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont | None:
    for path in FONT_CANDIDATES[kind]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return None


def strip_symbols(text: str) -> str:
    """폰트에 없는 이모지를 걷어낸다. 카드에 네모(□)가 찍히는 걸 막는다."""
    keep = []
    for ch in text:
        code = ord(ch)
        if code < 0x2000 or 0xAC00 <= code <= 0xD7A3 or 0x3130 <= code <= 0x318F:
            keep.append(ch)
    return " ".join("".join(keep).split())


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """비율을 유지하면서 화면을 꽉 채우도록 자른다 (CSS의 object-fit: cover)."""
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h = h
        new_w = int(h * src_ratio)
    else:
        new_w = w
        new_h = int(w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 3        # 인물 사진은 위쪽이 중요해서 살짝 위로
    return img.crop((left, top, left + w, top + h))


def _wrap(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """어절 단위로 줄바꿈. 한국어는 띄어쓰기 기준으로 끊어야 읽힌다."""
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_text_card(headline: str, label: str = "", footer: str = "",
                   seed: int = 0) -> bytes | None:
    """사진 없이 글만으로 카드를 만든다.

    100% 직접 만든 이미지라 저작권 걱정이 없고, 사진을 붙이지 않아도
    모든 글에 이미지가 붙어서 X 노출이 올라간다.
    """
    cfg = _cfg()
    size = int(cfg.get("size", 1080))
    margin = int(size * 0.085)
    max_text_w = size - margin * 2

    palettes = cfg.get("palettes") or [
        [[22, 30, 46], [46, 62, 92]],
        [[38, 26, 46], [78, 48, 84]],
        [[18, 40, 40], [34, 78, 74]],
        [[46, 32, 22], [96, 62, 38]],
        [[26, 26, 34], [64, 62, 78]],
    ]
    top_rgb, bottom_rgb = palettes[seed % len(palettes)]

    canvas = Image.new("RGB", (size, size), tuple(top_rgb))
    draw = ImageDraw.Draw(canvas)
    for y in range(size):
        t = y / size
        draw.line([(0, y), (size, y)], fill=tuple(
            int(top_rgb[i] + (bottom_rgb[i] - top_rgb[i]) * t) for i in range(3)))

    accent = tuple(cfg.get("accent_rgb", [255, 210, 60]))

    # 위쪽 카테고리 딱지
    y = margin
    label = strip_symbols(label)
    if label:
        lf = _font("bold", int(size * 0.030))
        if lf:
            draw.text((margin, y), label, font=lf, fill=accent)
            y += int(size * 0.070)

    # 가운데 큰 문구
    lines: list[str] = []
    font = None
    for pt in range(int(size * 0.085), int(size * 0.042), -2):
        font = _font("bold", pt)
        if font is None:
            log.warning("한글 폰트를 찾지 못했습니다.")
            return None
        lines = _wrap(headline, font, max_text_w - int(size * 0.035), draw)
        if len(lines) <= 4:
            break

    line_h = int(font.size * 1.40)
    block_h = line_h * len(lines)
    y = max(y, (size - block_h) // 2 - int(size * 0.02))

    bar_w = max(5, int(size * 0.010))
    draw.rounded_rectangle(
        [margin, y + int(line_h * 0.16), margin + bar_w, y + block_h - int(line_h * 0.32)],
        radius=bar_w, fill=accent)

    text_x = margin + bar_w + int(size * 0.030)
    for line in lines:
        draw.text((text_x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    if footer:
        ff = _font("regular", int(size * 0.028))
        if ff:
            draw.text((margin, size - margin), footer, font=ff,
                      fill=(210, 210, 210), anchor="ls")

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    log.info("글자 카드 제작 완료 (%dx%d)", size, size)
    return out.getvalue()


def make(image_bytes: bytes, headline: str, footer: str = "") -> bytes | None:
    """사진 + 문구 -> 카드뉴스 이미지(PNG 바이트). 실패하면 None."""
    cfg = _cfg()
    size = int(cfg.get("size", 1080))
    margin = int(size * 0.075)
    max_text_w = size - margin * 2

    try:
        photo = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:  # noqa: BLE001 - 어떤 이미지가 올지 모른다
        log.warning("사진을 읽지 못했습니다: %s", e)
        return None

    canvas = _cover(photo, size, size)

    # 아래쪽 어두운 그라데이션 (글자가 사진 위에서도 읽히게)
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    start = int(size * float(cfg.get("gradient_start", 0.42)))
    peak = int(255 * float(cfg.get("gradient_strength", 0.90)))
    for y in range(start, size):
        ratio = (y - start) / max(1, size - start)
        od.line([(0, y), (size, y)], fill=(0, 0, 0, int(peak * (ratio ** 1.35))))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(canvas)

    # 문구 크기를 줄여가며 3줄 안에 들어오게 맞춘다
    lines: list[str] = []
    font = None
    for pt in range(int(size * 0.072), int(size * 0.040), -2):
        font = _font("bold", pt)
        if font is None:
            log.warning("한글 폰트를 찾지 못했습니다. 카드 제작을 건너뜁니다.")
            return None
        lines = _wrap(headline, font, max_text_w, draw)
        if len(lines) <= 3:
            break

    line_h = int(font.size * 1.42)
    foot_font = _font("regular", int(size * 0.028))
    foot_h = int(size * 0.055) if (footer and foot_font) else 0

    block_h = line_h * len(lines)
    bottom = size - margin - foot_h
    y = bottom - block_h

    # 문구 왼쪽의 포인트 막대
    bar_w = max(4, int(size * 0.008))
    accent = tuple(cfg.get("accent_rgb", [255, 210, 60]))
    draw.rounded_rectangle(
        [margin, y + int(line_h * 0.18), margin + bar_w, y + block_h - int(line_h * 0.30)],
        radius=bar_w, fill=accent)

    text_x = margin + bar_w + int(size * 0.028)
    for line in lines:
        draw.text((text_x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    if footer and foot_font:
        draw.text((margin, size - margin - int(size * 0.030)), footer,
                  font=foot_font, fill=(215, 215, 215))

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    log.info("카드 이미지 제작 완료 (%dx%d, %.0fKB)", size, size, len(out.getvalue()) / 1024)
    return out.getvalue()
