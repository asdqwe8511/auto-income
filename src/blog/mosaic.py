"""사진 속 한글이 보이는 부분을 뭉갠다.

검출 방법 두 가지를 순서대로 시도한다.
  1) easyocr 가 깔려 있으면 그것 (정확함, 설치 용량 큼)
  2) 없으면 Gemini 비전에게 글자 위치를 물어본다 (설치 0, 무료)
둘 다 실패하면 원본을 그대로 두고 '확인 필요' 경고를 돌려준다.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import requests
from PIL import Image, ImageFilter

from common import env, log, scrub
from blog.config import blog_cfg

HANGUL = re.compile(r"[가-힣]")
GEMINI_VISION = ("https://generativelanguage.googleapis.com/v1beta/"
                 "models/{model}:generateContent")
VISION_MODELS = ["gemini-flash-latest", "gemini-3.7-flash", "gemini-3.6-flash"]

_reader = None


def _easyocr_boxes(path: Path) -> list[tuple[int, int, int, int]] | None:
    """easyocr 로 한글이 든 글상자를 찾는다. 없으면 None."""
    global _reader
    try:
        import easyocr  # noqa: PLC0415
    except ImportError:
        return None
    try:
        if _reader is None:
            _reader = easyocr.Reader(["ko", "en"], gpu=False)
        boxes = []
        for quad, text, conf in _reader.readtext(str(path)):
            if conf < 0.2 or not HANGUL.search(text):
                continue
            xs = [int(p[0]) for p in quad]
            ys = [int(p[1]) for p in quad]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        return boxes
    except Exception as e:  # noqa: BLE001 - OCR은 무슨 에러든 그냥 넘어간다
        log.warning("easyocr 실패: %s", e)
        return None


def _gemini_boxes(path: Path) -> list[tuple[int, int, int, int]] | None:
    """Gemini 비전에게 한글 글자 영역을 물어본다. 좌표는 0~1000 정규화 값."""
    key = env("GEMINI_API_KEY")
    if not key:
        return None
    img_b64 = base64.b64encode(path.read_bytes()).decode()
    prompt = (
        "이 사진에서 한글 글자가 보이는 영역을 모두 찾아주세요. "
        "간판, 명찰, 이름표, 현수막, 메뉴판, 학교/유치원 이름, 차량 번호판, "
        "화면 속 글자까지 전부 포함합니다. "
        '답은 JSON 배열로만 주세요: [{"box_2d":[ymin,xmin,ymax,xmax]}, ...] '
        "좌표는 0~1000 사이 정수입니다. 글자가 없으면 [] 만 주세요."
    )
    body = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    for model in VISION_MODELS:
        try:
            r = requests.post(GEMINI_VISION.format(model=model), json=body, timeout=90,
                              headers={"x-goog-api-key": key})
            if r.status_code == 404:
                continue
            r.raise_for_status()
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M))
            w, h = Image.open(path).size
            out = []
            for item in data:
                b = item.get("box_2d") or item.get("box") or []
                if len(b) != 4:
                    continue
                ymin, xmin, ymax, xmax = b
                out.append((int(xmin / 1000 * w), int(ymin / 1000 * h),
                            int(xmax / 1000 * w), int(ymax / 1000 * h)))
            return out
        except Exception as e:  # noqa: BLE001
            log.warning("Gemini 비전 실패(%s): %s", model, scrub(e))
    return None


def apply(src: Path, dst: Path) -> tuple[bool, int]:
    """src 사진의 한글 영역을 뭉개서 dst 로 저장.

    돌려주는 값: (검출에 성공했는가, 가린 영역 개수)
    검출 실패면 (False, 0) — 사람이 직접 확인해야 한다.
    """
    cfg = blog_cfg().get("모자이크", {})
    img = Image.open(src).convert("RGB")

    if not cfg.get("켜기", True):
        img.save(dst, quality=92)
        return True, 0

    boxes = _easyocr_boxes(src)
    if boxes is None:
        boxes = _gemini_boxes(src)
    if boxes is None:
        img.save(dst, quality=92)
        return False, 0

    pad = int(cfg.get("여백", 6))
    power = int(cfg.get("세기", 18))
    w, h = img.size
    for x0, y0, x1, y1 in boxes:
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
        if x1 <= x0 or y1 <= y0:
            continue
        patch = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(power))
        img.paste(patch, (x0, y0))

    img.save(dst, quality=92)
    return True, len(boxes)
