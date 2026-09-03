"""스레드(Threads) 발행. 키가 없으면 '수동 모드'로 동작한다."""
from __future__ import annotations

import time

import requests

from common import env, log

BASE = "https://graph.threads.net/v1.0"
KEYS = ("THREADS_USER_ID", "THREADS_ACCESS_TOKEN")


def ready() -> bool:
    return all(env(k) for k in KEYS)


def post(text: str) -> tuple[bool, str]:
    if not ready():
        return False, "NO_KEYS"
    uid, token = env("THREADS_USER_ID"), env("THREADS_ACCESS_TOKEN")
    try:
        r = requests.post(f"{BASE}/{uid}/threads",
                          data={"media_type": "TEXT", "text": text, "access_token": token},
                          timeout=30)
        if r.status_code != 200:
            log.warning("스레드 컨테이너 생성 실패 %s: %s", r.status_code, r.text[:300])
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        creation_id = r.json().get("id")

        time.sleep(20)  # Meta 권장: 컨테이너 생성 후 잠깐 대기

        r2 = requests.post(f"{BASE}/{uid}/threads_publish",
                           data={"creation_id": creation_id, "access_token": token},
                           timeout=30)
        if r2.status_code != 200:
            log.warning("스레드 발행 실패 %s: %s", r2.status_code, r2.text[:300])
            return False, f"HTTP {r2.status_code}: {r2.text[:200]}"
        media_id = r2.json().get("id")

        link = f"threads media id {media_id}"
        try:
            r3 = requests.get(f"{BASE}/{media_id}",
                              params={"fields": "permalink", "access_token": token}, timeout=20)
            if r3.status_code == 200:
                link = r3.json().get("permalink", link)
        except requests.RequestException:
            pass
        return True, link
    except requests.RequestException as e:
        return False, f"네트워크 오류: {e}"
