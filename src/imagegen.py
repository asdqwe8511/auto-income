"""AI로 배경 이미지를 만든다. (Gemini 이미지 모델)

만든 사진 위에는 cardmaker 가 한글 문구를 얹는다.
AI가 한글을 그리게 하면 오타가 나기 쉬워서, 글씨는 우리가 직접 얹는 게 안전하다.

이미지 생성은 글 생성보다 무료 한도가 훨씬 적다.
한도를 넘으면 조용히 실패하고, 글자만 있는 카드로 대체된다.
"""
from __future__ import annotations

import base64
import time

import requests

import llm
from common import env, log, settings

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

FALLBACKS = [
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
]

# 사진 분위기를 통일해서 계정 전체가 한 브랜드처럼 보이게 한다
STYLE = ("photorealistic editorial photograph, natural window light, cinematic color grading, "
         "shallow depth of field, 16:9 composition with clear empty space in the lower third, "
         "calm and grounded mood, no text, no letters, no logos, no watermark")


def _cfg() -> dict:
    return settings().get("image", {})


def enabled() -> bool:
    return bool(_cfg().get("enabled")) and bool(env("GEMINI_API_KEY"))


def wants(pillar: str) -> bool:
    allow = _cfg().get("pillars")
    return True if not allow else pillar in allow


def build_prompt(text: str, pillar: str) -> str | None:
    """글을 보고 어떤 사진이 어울릴지 영어 묘사를 만든다."""
    system = (
        "You turn a Korean social media post into ONE English prompt for a photo generator.\n"
        "Describe a realistic everyday scene that fits the post's feeling.\n"
        "Rules: describe people as ordinary Korean adults in Korea. No celebrities, no brands, "
        "no logos, no readable text or signage. One or two sentences. Output the prompt only."
    )
    got = llm.complete_text(system, f"[Korean post]\n{text}\n\nWrite the photo prompt.")
    if not got:
        return None
    return f"{got.strip().splitlines()[0]} {STYLE}"


# 카테고리별로 어떤 장면이 어울리는지 힌트
SCENE_HINT = {
    "news": "뉴스를 접한 직장인의 표정과 사무실 또는 카페 풍경",
    "money": "가계부·통장·노트북을 앞에 둔 한국 30대의 차분한 집 안 풍경",
    "product": "책상 위 물건을 고르거나 살펴보는 손과 사무실 책상 클로즈업",
    "health": "퇴근 후 집에서 잠깐 쉬거나 스트레칭하는 평범한 일상 장면",
    "humor": "지친 표정의 한국 직장인과 사무실 책상 풍경",
}


def korean_prompt(text: str, pillar: str) -> str:
    """Gemini 앱에 그대로 붙여넣을 한국어 이미지 프롬프트.

    API 한도와 무관하게 항상 만들 수 있도록 템플릿으로 짠다.
    """
    # 두괄식이라 첫 '문장' 이 핵심이다. 줄바꿈으로 끊긴 문장을 다시 이어 붙인다.
    body = text.strip().split("\n\n")[0].replace("\n", " ")
    head = body.split(".")[0].strip().rstrip("…") or body[:60]
    hint = SCENE_HINT.get(pillar, SCENE_HINT["humor"])
    return (
        f"'{head}' 라는 내용에 어울리는 사진 한 장을 만들어줘.\n"
        f"장면: {hint}.\n"
        "스타일: 실사 사진 느낌, 한국인 30대, 자연광, 차분한 색감, 가로 16:9.\n"
        "구도: 아래쪽 3분의 1은 내가 문구를 얹을 자리다. "
        "그 부분에는 인물 얼굴이나 중요한 물건을 두지 말고 비교적 단순하게 비워둘 것.\n"
        "금지: 사진 안에 글자, 자막, 간판 문구, 로고, 워터마크를 절대 넣지 말 것."
    )


def generate(prompt: str) -> bytes | None:
    """영어 묘사로 사진을 만든다. 실패하면 None."""
    key = env("GEMINI_API_KEY")
    if not key:
        return None

    first = _cfg().get("model", FALLBACKS[0])
    candidates = [first] + [m for m in FALLBACKS if m != first]
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    for model in candidates:
        for attempt in range(2):
            try:
                r = requests.post(URL.format(model=model),
                                  headers={"x-goog-api-key": key}, json=body, timeout=240)
            except requests.RequestException as e:
                log.warning("이미지 생성 통신 오류: %s", e)
                return None
            if r.status_code in (429, 503):
                if attempt == 0:
                    time.sleep(12)
                    continue
                log.warning("[%s] 이미지 생성 한도/과부하 -> 다음 모델", model)
                break
            if r.status_code == 404:
                log.warning("[%s] 이미지 모델이 없습니다 -> 다음 모델", model)
                break
            if r.status_code != 200:
                log.warning("이미지 생성 오류 %s: %s", r.status_code, r.text[:200])
                return None

            parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            data = next((p["inlineData"]["data"] for p in parts if "inlineData" in p), None)
            if not data:
                log.warning("[%s] 응답에 이미지가 없습니다", model)
                break
            raw = base64.b64decode(data)
            log.info("AI 이미지 생성 완료 (%s, %dKB)", model, len(raw) // 1024)
            return raw

    log.warning("AI 이미지를 만들지 못했습니다. 글자 카드로 대체합니다.")
    return None


def make_scene(text: str, pillar: str) -> bytes | None:
    """글 -> 어울리는 사진. 실패하면 None (호출하는 쪽에서 글자 카드로 넘어간다)."""
    if not enabled() or not wants(pillar):
        return None
    prompt = build_prompt(text, pillar)
    if not prompt:
        return None
    log.info("이미지 묘사: %s", prompt[:90])
    return generate(prompt)
