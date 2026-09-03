"""텔레그램 봇 API 얇은 래퍼."""
from __future__ import annotations

import requests

from common import env, log

API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    return env("TELEGRAM_BOT_TOKEN")


def _chat() -> str:
    return env("TELEGRAM_CHAT_ID")


def enabled() -> bool:
    return bool(_token() and _chat())


def call(method: str, **payload):
    if not _token():
        log.warning("TELEGRAM_BOT_TOKEN 없음 -> 텔레그램 호출 건너뜀 (%s)", method)
        return None
    try:
        r = requests.post(API.format(token=_token(), method=method), json=payload, timeout=25)
        data = r.json()
        if not data.get("ok"):
            log.warning("텔레그램 %s 실패: %s", method, data.get("description"))
            return None
        return data.get("result")
    except (requests.RequestException, ValueError) as e:
        log.warning("텔레그램 %s 예외: %s", method, e)
        return None


def send(text: str, buttons: list[list[dict]] | None = None,
         preview: bool = False) -> int | None:
    payload = {"chat_id": _chat(), "text": text,
               "disable_web_page_preview": not preview}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = call("sendMessage", **payload)
    return res.get("message_id") if res else None


def edit(message_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
    payload = {"chat_id": _chat(), "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    if buttons is not None:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    call("editMessageText", **payload)


def answer(callback_id: str, text: str = "") -> None:
    call("answerCallbackQuery", callback_query_id=callback_id, text=text)


def update_card(message_id: int, is_photo: bool, text: str,
                buttons: list[list[dict]] | None = None) -> bool:
    """그 자리에서 카드 내용을 바꾼다. 새 메시지를 보내지 않는다."""
    payload: dict = {"chat_id": _chat(), "message_id": message_id}
    if buttons is not None:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    if is_photo:
        payload["caption"] = text[:1024]
        return call("editMessageCaption", **payload) is not None
    payload["text"] = text
    payload["disable_web_page_preview"] = True
    return call("editMessageText", **payload) is not None


def delete(message_id: int) -> None:
    call("deleteMessage", chat_id=_chat(), message_id=message_id)


def ask_reply(text: str, placeholder: str = "", html: bool = False) -> int | None:
    """입력창을 답장 모드로 열어준다. 사용자는 곧바로 📎 로 첨부만 하면 된다."""
    markup: dict = {"force_reply": True, "selective": False}
    if placeholder:
        markup["input_field_placeholder"] = placeholder[:64]
    payload: dict = {"chat_id": _chat(), "text": text, "reply_markup": markup,
                     "disable_web_page_preview": True}
    if html:
        payload["parse_mode"] = "HTML"
    res = call("sendMessage", **payload)
    return res.get("message_id") if res else None


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def updates(offset: int) -> list[dict]:
    res = call("getUpdates", offset=offset, timeout=0, limit=100,
               allowed_updates=["message", "callback_query"])
    return res or []


def _source_row(source_url: str | None) -> list[list[dict]]:
    """원문 기사 버튼. 카드가 어떻게 바뀌어도 항상 맨 위에 따라다닌다."""
    if not source_url:
        return []
    return [[{"text": "\U0001f517 원문 기사 보기", "url": source_url}]]


def approval_buttons(item_id: str, has_image: bool = False,
                     source_url: str | None = None) -> list[list[dict]]:
    photo = "\U0001f5bc 사진 바꾸기" if has_image else "\U0001f5bc 사진 붙이기"
    return _source_row(source_url) + [
        [
            {"text": "✅ 승인", "callback_data": f"a|{item_id}"},
            {"text": "✏️ 수정", "callback_data": f"e|{item_id}"},
        ],
        [
            {"text": photo, "callback_data": f"p|{item_id}"},
            {"text": "\U0001f5d1 삭제", "callback_data": f"d|{item_id}"},
        ],
    ]


def cancel_buttons(item_id: str, source_url: str | None = None) -> list[list[dict]]:
    return _source_row(source_url) + [
        [{"text": "↩️ 취소", "callback_data": f"c|{item_id}"}],
    ]


def send_photo(file_id: str, caption: str, buttons: list[list[dict]] | None = None) -> int | None:
    """텔레그램에 이미 올라온 사진(file_id)을 그대로 다시 보낸다."""
    payload = {"chat_id": _chat(), "photo": file_id, "caption": caption[:1024]}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = call("sendPhoto", **payload)
    return res.get("message_id") if res else None


def upload_photo(image: bytes, caption: str, buttons: list[list[dict]] | None = None) -> tuple[int | None, str | None]:
    """내가 만든 이미지를 텔레그램에 올린다. (message_id, file_id) 를 돌려준다."""
    if not _token():
        return None, None
    data: dict = {"chat_id": _chat(), "caption": caption[:1024]}
    if buttons:
        import json as _json
        data["reply_markup"] = _json.dumps({"inline_keyboard": buttons})
    try:
        r = requests.post(API.format(token=_token(), method="sendPhoto"),
                          data=data, files={"photo": ("card.png", image, "image/png")},
                          timeout=90)
        res = r.json()
        if not res.get("ok"):
            log.warning("이미지 업로드 실패: %s", res.get("description"))
            return None, None
        msg = res["result"]
        photos = msg.get("photo") or []
        best = max(photos, key=lambda p: p.get("file_size", 0)) if photos else {}
        return msg.get("message_id"), best.get("file_id")
    except (requests.RequestException, ValueError) as e:
        log.warning("이미지 업로드 예외: %s", e)
        return None, None


def upload_video(video: bytes, caption: str, buttons: list[list[dict]] | None = None) -> tuple[int | None, str | None]:
    """내가 만든 영상을 텔레그램에 올린다. (message_id, file_id)."""
    if not _token():
        return None, None
    data: dict = {"chat_id": _chat(), "caption": caption[:1024], "supports_streaming": True}
    if buttons:
        import json as _json
        data["reply_markup"] = _json.dumps({"inline_keyboard": buttons})
    try:
        r = requests.post(API.format(token=_token(), method="sendVideo"),
                          data=data, files={"video": ("card.mp4", video, "video/mp4")},
                          timeout=180)
        res = r.json()
        if not res.get("ok"):
            log.warning("영상 업로드 실패: %s", res.get("description"))
            return None, None
        msg = res["result"]
        vid = msg.get("video") or {}
        return msg.get("message_id"), vid.get("file_id")
    except (requests.RequestException, ValueError) as e:
        log.warning("영상 업로드 예외: %s", e)
        return None, None


def download(file_id: str) -> bytes | None:
    """사진 원본 바이트를 받아온다. (X에 올릴 때 사용)"""
    info = call("getFile", file_id=file_id)
    if not info or not info.get("file_path"):
        return None
    url = f"https://api.telegram.org/file/bot{_token()}/{info['file_path']}"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content
    except requests.RequestException as e:
        log.warning("사진 내려받기 실패: %s", e)
        return None
