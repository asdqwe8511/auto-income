"""X(트위터) 발행. 키가 없으면 '수동 모드'로 동작한다."""
from __future__ import annotations

import requests
from requests_oauthlib import OAuth1

from common import env, log

KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
ENDPOINT = "https://api.x.com/2/tweets"

# 이미지 업로드 주소. 위에서부터 시도한다(정책이 바뀌어도 하나는 살아있게).
MEDIA_ENDPOINTS = [
    ("https://api.x.com/2/media/upload", {"media_category": "tweet_image"}),
    ("https://upload.twitter.com/1.1/media/upload.json", {}),
]


def ready() -> bool:
    return all(env(k) for k in KEYS)


def _auth() -> OAuth1:
    return OAuth1(env("X_API_KEY"), env("X_API_SECRET"),
                  env("X_ACCESS_TOKEN"), env("X_ACCESS_TOKEN_SECRET"))


def upload_image(image: bytes) -> str | None:
    """사진을 먼저 올리고 media_id 를 받아온다. 실패하면 None."""
    auth = _auth()
    for url, extra in MEDIA_ENDPOINTS:
        try:
            r = requests.post(url, auth=auth, files={"media": ("image.jpg", image)},
                              data=extra, timeout=90)
        except requests.RequestException as e:
            log.warning("사진 업로드 통신 오류(%s): %s", url, e)
            continue
        if r.status_code in (200, 201):
            try:
                j = r.json()
            except ValueError:
                continue
            media_id = (j.get("data") or {}).get("id") or j.get("media_id_string")
            if media_id:
                log.info("사진 업로드 성공 (%s)", url)
                return str(media_id)
        log.warning("사진 업로드 실패 %s: %s", r.status_code, r.text[:200])
    return None


def post(text: str, image: bytes | None = None) -> tuple[bool, str]:
    """(성공여부, 글주소 또는 에러메시지)"""
    if not ready():
        return False, "NO_KEYS"

    payload: dict = {"text": text}
    if image:
        media_id = upload_image(image)
        if media_id:
            payload["media"] = {"media_ids": [media_id]}
        else:
            log.warning("사진 없이 글만 올립니다.")

    try:
        r = requests.post(ENDPOINT, auth=_auth(), json=payload, timeout=60)
        if r.status_code in (200, 201):
            tid = r.json().get("data", {}).get("id", "")
            return True, f"https://x.com/i/web/status/{tid}"
        log.warning("X 발행 실패 %s: %s", r.status_code, r.text[:300])
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, f"네트워크 오류: {e}"
