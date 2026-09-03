"""블로그 봇 전용 텔레그램 통신.

기존 시스템(src/tg.py)과 **다른 봇**을 쓴다.
텔레그램은 한 봇의 메시지를 한 곳에서만 가져갈 수 있어서,
같은 토큰으로 두 프로그램이 돌면 서로 메시지를 뺏어간다.
"""
from __future__ import annotations

import requests

from common import env, log

API = "https://api.telegram.org/bot{token}/{method}"
FILE = "https://api.telegram.org/file/bot{token}/{path}"


def token() -> str:
    """블로그 봇 전용 토큰. 기존 봇을 빌려 쓰지 않는다."""
    return env("BLOG_BOT_TOKEN")


def call(method: str, **payload):
    t = token()
    if not t:
        log.error("BLOG_BOT_TOKEN 이 없습니다.")
        return None
    try:
        r = requests.post(API.format(token=t, method=method), json=payload, timeout=40)
        data = r.json()
        if not data.get("ok"):
            desc = data.get("description", "")
            if "Conflict" in desc:
                log.error("다른 프로그램이 같은 봇을 보고 있습니다. 봇을 분리하세요.")
            else:
                log.warning("텔레그램 %s 실패: %s", method, desc)
            return None
        return data.get("result")
    except (requests.RequestException, ValueError) as e:
        log.warning("텔레그램 %s 예외: %s", method, e)
        return None


def check() -> str | None:
    """켜지기 전 점검. 문제가 있으면 사람이 읽을 안내문을 돌려준다."""
    t = token()
    if not t:
        return ("BLOG_BOT_TOKEN 이 없습니다."
                "\n  1) 텔레그램에서 @BotFather 에게 /newbot 을 보내 새 봇을 만드세요."
                "\n  2) 폴더의 `키넣기.bat` 을 더블클릭해 받은 토큰을 붙여넣으세요.")
    if t == env("TELEGRAM_BOT_TOKEN"):
        return ("BLOG_BOT_TOKEN 이 메인 시스템 봇과 같습니다."
                "\n  같은 봇을 두 프로그램이 보면 메시지를 서로 뺏어갑니다."
                "\n  @BotFather 에서 새 봇을 하나 더 만들어 그 토큰을 넣어주세요.")
    me = call("getMe")
    if not me:
        return "토큰으로 텔레그램에 연결하지 못했습니다. 토큰을 다시 확인해주세요."
    log.info("연결된 봇: @%s (%s)", me.get("username", "?"), me.get("first_name", ""))
    return None


def download(file_id: str, dest):
    """사진을 내려받아 dest 경로에 저장한다."""
    info = call("getFile", file_id=file_id)
    if not info:
        return None
    try:
        r = requests.get(FILE.format(token=token(), path=info["file_path"]), timeout=60)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest
    except requests.RequestException as e:
        log.warning("사진 내려받기 실패: %s", e)
        return None


def say(chat_id, text: str) -> None:
    call("sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
