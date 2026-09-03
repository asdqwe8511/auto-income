"""도는 심장. 알림 -> 승인/수정/사진·영상 -> 발행 을 한 번에 처리한다.

버튼을 누르면 새 메시지를 보내지 않고 그 카드 안에서 바로 처리된다.
"""
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

import cardmaker
import generate
import imagegen
import store
import tg
import videomaker
from channels import threads as ch_threads
from channels import x as ch_x
from common import log, settings, pillars, now, today, iso, parse

PUBLISHERS = {"x": ch_x, "threads": ch_threads}
SLOT_LABEL = {"morning": "\U0001f305 아침", "lunch": "\U0001f35a 점심", "evening": "\U0001f319 저녁"}
CHANNEL_LABEL = {"x": "X", "threads": "스레드"}
LIVE = ("draft", "notified", "edit_requested", "media_requested", "approved")
LINE = "─────────────"

INTENT = {
    "x": "https://x.com/intent/post?text={}",
    "threads": "https://www.threads.net/intent/post?text={}",
}


# ================================================================= 카드 만들기
def card(item: dict, st: dict, note: str = "") -> str:
    n = item["idx"] + 1
    cap = st["channels"][item["channel"]]["slots"][item["slot"]]
    spec = pillars().get(item.get("pillar", ""), {})
    head = "{} · {} · {} ({}/{})".format(
        SLOT_LABEL[item["slot"]],
        CHANNEL_LABEL.get(item["channel"], item["channel"]),
        spec.get("label", item.get("pillar", "")), n, cap)

    lines = [head, LINE, item["text"], LINE]
    if item.get("source_url"):
        lines.append("\U0001f517 원문({}) — 승인 전에 확인하세요".format(
            item.get("source_press") or "출처"))
        if item.get("source_title"):
            lines.append("   " + item["source_title"][:60])
        lines.append("   " + item["source_url"])
    kind = item.get("media_kind")
    if kind == "auto":
        lines.append("\U0001f5bc {} — 직접 찍은 사진으로 바꾸려면 \U0001f5bc 버튼".format(
            "AI 사진 카드" if item.get("ai_image") else "자동 카드"))
    elif kind:
        lines.append("\U0001f5bc {} 붙어 있음".format("사진" if kind == "photo" else "영상"))
    if note:
        lines.append(note)
    elif item.get("needs_check"):
        lines.append("⚠️ 내용 확인 후 직접 승인해 주세요")
    else:
        auto = parse(item.get("auto_approve_at"))
        if auto:
            lines.append("⏳ {}까지 두면 자동 발행".format(auto.strftime("%H:%M")))
    return "\n".join(lines)


def _images_made_today(items: list[dict]) -> int:
    return sum(1 for i in items if i["date"] == today() and i.get("ai_image"))


def _auto_card(item: dict, st: dict, items: list[dict] | None = None) -> bool:
    """사진을 안 붙였을 때 이미지를 자동으로 만들어 붙인다.

    1순위: AI가 그린 사진 + 그 위에 한글 문구
    2순위: 글자만 있는 그라데이션 카드
    """
    cfg = st.get("card", {}) or {}
    if not cfg.get("auto_generate", True) or not cardmaker.enabled():
        return False
    if item.get("media_kind"):
        return False

    spec = pillars().get(item.get("pillar", ""), {})
    head = item["text"].strip().splitlines()[0]
    made = None

    quota_left = int((st.get("image", {}) or {}).get("max_per_day", 0))
    if items is not None and _images_made_today(items) >= quota_left:
        log.info("오늘 AI 사진 한도(%d장) 도달 -> 글자 카드", quota_left)
    else:
        scene = imagegen.make_scene(item["text"], item.get("pillar", ""))
        if scene:
            limit = int(cfg.get("headline_max_chars", 24))
            short = item.get("headline") or generate.headline(item["text"], limit)
            item["headline"] = short
            made = cardmaker.make(scene, short, _footer(st))
            if made:
                item["ai_image"] = True

    if not made:
        made = cardmaker.make_text_card(head, spec.get("label", ""), _footer(st),
                                        seed=item.get("idx", 0) + len(item.get("pillar", "")))
    if not made:
        return False
    mid, file_id = tg.upload_photo(
        made, card(item, st),
        tg.approval_buttons(item["id"], False, item.get("source_url")))
    if not mid:
        return False
    item["media_kind"] = "auto"          # 사진을 붙이면 이 자동 카드는 교체된다
    item["media_file_id"] = file_id
    item["tg_message_id"] = mid
    item["tg_is_photo"] = True
    return True


def _post_card(item: dict, st: dict, items: list[dict] | None = None) -> None:
    """카드를 새로 보낸다. 이전 카드가 있으면 지워서 대화창을 깔끔하게 유지한다."""
    old = item.get("tg_message_id")

    if not item.get("media_kind") and _auto_card(item, st, items):
        if old and old != item["tg_message_id"]:
            tg.delete(old)
        return

    text = card(item, st)
    buttons = tg.approval_buttons(item["id"], bool(item.get("media_kind")),
                                  item.get("source_url"))

    if item.get("media_kind") in ("photo", "auto") and item.get("media_file_id"):
        mid = tg.send_photo(item["media_file_id"], text, buttons)
        is_photo = True
    else:
        mid = tg.send(text, buttons)
        is_photo = False

    if mid:
        item["tg_message_id"] = mid
        item["tg_is_photo"] = is_photo
        if old and old != mid:
            tg.delete(old)


def _drop_prompt(state: dict) -> None:
    """입력창을 열려고 보냈던 안내 메시지를 치운다. 대화창이 지저분해지지 않게."""
    mid = state.pop("media_prompt_id", None)
    if mid:
        tg.delete(mid)


def _refresh(item: dict, st: dict, note: str = "", buttons=None) -> None:
    """그 자리에서 카드 문구/버튼만 갈아끼운다. 새 메시지를 안 보낸다."""
    mid = item.get("tg_message_id")
    if not mid:
        return
    if buttons is None:
        buttons = tg.approval_buttons(item["id"], bool(item.get("media_kind")),
                                      item.get("source_url"))
    elif buttons == []:
        buttons = tg._source_row(item.get("source_url"))   # 끝난 카드에도 원문은 남긴다
    tg.update_card(mid, bool(item.get("tg_is_photo")), card(item, st, note), buttons)


# ================================================================= 미디어 가공
def _footer(st: dict) -> str:
    return (st.get("card", {}) or {}).get("footer", "") or ""


def _build_media(item: dict, st: dict, kind: str, source_file_id: str) -> bool:
    """받은 사진/영상에 대표 문구를 얹어 카드로 만든다."""
    raw = tg.download(source_file_id)
    if not raw:
        tg.send("⚠️ 파일을 받지 못했습니다.\n"
                "영상이 20MB를 넘으면 텔레그램 봇이 받을 수 없습니다. 더 짧게 잘라 보내주세요.")
        return False

    limit = int((st.get("card", {}) or {}).get("headline_max_chars", 24))
    head = item.get("headline") or generate.headline(item["text"], limit)
    item["headline"] = head

    if kind == "photo":
        made = cardmaker.make(raw, head, _footer(st)) if cardmaker.enabled() else None
        if not made:
            item["media_kind"] = "photo"
            item["media_file_id"] = source_file_id       # 가공 실패 시 원본 사용
            item["media_source_file_id"] = source_file_id
            return True
        mid, file_id = tg.upload_photo(
            made, card(item, st, "\U0001f5bc 카드 완성 — 확인하고 승인하세요"),
            tg.approval_buttons(item["id"], True, item.get("source_url")))
    else:
        if not (st.get("video", {}) or {}).get("enabled", True) or not videomaker.available():
            tg.send("⚠️ 영상 가공 도구(ffmpeg)가 없어 원본 그대로 씁니다.")
            item["media_kind"] = "video"
            item["media_file_id"] = source_file_id
            item["media_source_file_id"] = source_file_id
            return True
        tg.send("\U0001f3ac 영상을 가공하는 중입니다… (길이에 따라 1분쯤 걸립니다)")
        made = videomaker.make(raw, head, _footer(st))
        if not made:
            tg.send("⚠️ 영상 가공에 실패했습니다. 원본이 그대로 남아 있습니다.")
            return False
        mid, file_id = tg.upload_video(
            made, card(item, st, "\U0001f3ac 영상 완성 — 확인하고 승인하세요"),
            tg.approval_buttons(item["id"], True, item.get("source_url")))

    if not mid:
        return False

    old = item.get("tg_message_id")
    item["media_kind"] = kind
    item["media_file_id"] = file_id
    item["media_source_file_id"] = source_file_id
    item["tg_message_id"] = mid
    item["tg_is_photo"] = (kind == "photo")
    if old and old != mid:
        tg.delete(old)
    return True


# ================================================================= 버튼 처리
def handle_callback(cq: dict, items: list[dict], state: dict, st: dict) -> bool:
    data = cq.get("data", "")
    if "|" not in data:
        return False
    action, item_id = data.split("|", 1)
    item = store.find(items, item_id)
    if not item:
        tg.answer(cq["id"], "이미 지난 글입니다")
        return False

    if (cq.get("message") or {}).get("message_id"):
        item["tg_message_id"] = cq["message"]["message_id"]

    if action == "a":
        item["status"] = "approved"
        item["approved_at"] = iso(now())
        if st.get("publish_on_approve", True):
            item["publish_at"] = iso(now())        # 승인 즉시 발행
            note = "✅ 승인됨 — 곧 올라갑니다"
        else:
            note = "✅ 승인됨 — 예정 시간에 올라갑니다"
        tg.answer(cq["id"], "승인했습니다")
        _refresh(item, st, note, [])

    elif action == "d":
        item["status"] = "rejected"
        tg.answer(cq["id"], "삭제했습니다")
        _refresh(item, st, "\U0001f5d1 삭제됨 — 올라가지 않습니다", [])

    elif action == "p":
        item["status"] = "media_requested"
        state["awaiting_media"] = item_id
        state["awaiting_edit"] = None
        tg.answer(cq["id"], "첨부창을 열었습니다")
        _refresh(item, st,
                 "\U0001f5bc 사진 또는 영상을 기다리는 중입니다.\n"
                 "   대표 문구를 얹어 카드로 만들어 드립니다.",
                 tg.cancel_buttons(item_id, item.get("source_url")))
        _drop_prompt(state)
        hint = tg.escape_html(imagegen.korean_prompt(item["text"], item.get("pillar", "")))
        state["media_prompt_id"] = tg.ask_reply(
            "\U0001f4ce 클립 버튼으로 사진·영상을 보내주세요.\n\n"
            "\U0001f3a8 <b>Gemini 앱에 붙여넣을 문구</b> (눌러서 복사)\n"
            f"<code>{hint}</code>\n\n"
            "만든 이미지를 여기로 보내면 문구를 얹어 카드로 만들어 드립니다.",
            "사진·영상을 첨부하세요", html=True)

    elif action == "e":
        item["status"] = "edit_requested"
        state["awaiting_edit"] = item_id
        state["awaiting_media"] = None
        tg.answer(cq["id"], "입력창을 열었습니다")
        _refresh(item, st,
                 "✏️ 어떻게 고칠까요?\n"
                 "   예) 더 짧게 / 더 담담하게 / 숫자 빼줘\n"
                 "   직접 쓴 글로 바꾸려면 맨 앞에 = 를 붙이세요",
                 tg.cancel_buttons(item_id, item.get("source_url")))
        _drop_prompt(state)
        state["media_prompt_id"] = tg.ask_reply(
            "✏️ 어떻게 고칠지 아래에 적어 보내주세요.", "예) 더 짧게")

    elif action == "c":
        state["awaiting_edit"] = None
        state["awaiting_media"] = None
        _drop_prompt(state)
        item["status"] = "notified"
        tg.answer(cq["id"], "취소했습니다")
        _refresh(item, st)

    else:
        return False
    return True


# ================================================================= 메시지 처리
def handle_text(text: str, items: list[dict], state: dict, st: dict) -> bool:
    text = text.strip()
    today_items = [i for i in items if i["date"] == today()]

    if text.startswith("/"):
        cmd = text.split()[0].lower()
        if cmd == "/status":
            tg.send(summary(today_items))
        elif cmd == "/ok":
            n = 0
            for i in today_items:
                if i["status"] in ("draft", "notified", "edit_requested", "media_requested"):
                    i["status"] = "approved"
                    i["approved_at"] = iso(now())
                    n += 1
            tg.send("✅ 대기 중이던 {}개를 모두 승인했습니다.\n"
                    "(예정 시간에 순서대로 올라갑니다)".format(n))
        elif cmd == "/stop":
            n = 0
            for i in today_items:
                if i["status"] in LIVE:
                    i["status"] = "rejected"
                    n += 1
            tg.send("\U0001f6d1 오늘 남은 {}개를 모두 취소했습니다.".format(n))
        else:
            tg.send("사용법\n"
                    "/status — 오늘 현황\n"
                    "/ok — 대기 중인 글 전부 승인\n"
                    "/stop — 오늘 남은 글 전부 취소\n\n"
                    "글마다 버튼: ✅승인 ✏️수정 \U0001f5bc사진 \U0001f5d1삭제\n"
                    "승인하면 바로 올라갑니다.")
        return True

    item_id = state.get("awaiting_edit")
    if not item_id:
        return False
    item = store.find(items, item_id)
    state["awaiting_edit"] = None
    _drop_prompt(state)
    if not item:
        return True

    max_chars = st["channels"][item["channel"]]["max_chars"]
    if text.startswith("="):
        new_text = text[1:].strip()[:max_chars]
    else:
        _refresh(item, st, "\U0001f916 고치는 중입니다…", [])
        new_text = generate.rewrite(item["channel"], item["text"], text, max_chars,
                                    item.get("pillar", "humor"))

    if not new_text:
        item["status"] = "notified"
        _refresh(item, st, "⚠️ 고치지 못했습니다. 원래 글이 그대로입니다.")
        return True

    item["text"] = new_text
    item["status"] = "notified"
    item["headline"] = None                    # 글이 바뀌었으니 대표 문구도 다시
    item["auto_approve_at"] = None if item.get("needs_check") else _auto_at(st)

    if item.get("media_source_file_id"):       # 붙어 있던 사진/영상 카드도 다시 만든다
        _build_media(item, st, item["media_kind"], item["media_source_file_id"])
    else:
        _post_card(item, st)
    return True


def handle_media(msg: dict, items: list[dict], state: dict, st: dict) -> bool:
    """사진 또는 영상을 받아 카드로 만든다."""
    if msg.get("photo"):
        kind = "photo"
        best = max(msg["photo"], key=lambda p: p.get("file_size", 0) or p.get("width", 0))
        file_id = best["file_id"]
    elif msg.get("video"):
        kind, file_id = "video", msg["video"]["file_id"]
    elif msg.get("document", {}).get("mime_type", "").startswith("video/"):
        kind, file_id = "video", msg["document"]["file_id"]
    else:
        return False

    item_id = state.get("awaiting_media")
    if not item_id:
        tg.send("파일을 받았지만 어느 글에 붙일지 모르겠습니다.\n"
                "글 아래 \U0001f5bc 버튼을 먼저 눌러주세요.")
        return False
    item = store.find(items, item_id)
    state["awaiting_media"] = None
    _drop_prompt(state)
    if not item:
        return True

    item["headline"] = None
    if _build_media(item, st, kind, file_id):
        item["status"] = "notified"
        log.info("%s 첨부 완료: %s", kind, item["id"])
    else:
        item["status"] = "notified"
        _refresh(item, st)
    return True


def process_telegram(items: list[dict], state: dict, st: dict) -> bool:
    if not tg.enabled():
        return False
    offset = int(state.get("tg_offset", 0))
    ups = tg.updates(offset)
    changed = False
    for u in ups:
        offset = max(offset, int(u["update_id"]) + 1)
        if "callback_query" in u:
            changed |= handle_callback(u["callback_query"], items, state, st)
        elif "message" in u:
            msg = u["message"]
            if msg.get("photo") or msg.get("video") or msg.get("document"):
                changed |= handle_media(msg, items, state, st)
            elif msg.get("text"):
                changed |= handle_text(msg["text"], items, state, st)
    if ups:
        state["tg_offset"] = offset
        changed = True
    return changed


# ================================================================= 알림 / 자동승인
def _auto_at(st: dict):
    mins = st.get("auto_approve_after_minutes", 0)
    return iso(now() + timedelta(minutes=mins)) if mins else None


def notify_due(items: list[dict], st: dict) -> bool:
    changed = False
    due = [i for i in items
           if i["status"] == "draft" and i["date"] == today()
           and now() >= (parse(i["notify_at"]) or now())]
    due.sort(key=lambda i: (i["notify_at"], i["channel"], i["idx"]))
    for item in due:
        item["auto_approve_at"] = None if item.get("needs_check") else _auto_at(st)
        _post_card(item, st, items)
        item["status"] = "notified"
        item["notified_at"] = iso(now())
        changed = True
        log.info("알림 발송: %s", item["id"])
    return changed


def auto_approve(items: list[dict], st: dict) -> bool:
    if not st.get("auto_approve_after_minutes"):
        return False
    changed = False
    for item in items:
        if item.get("needs_check"):
            continue
        due = parse(item.get("auto_approve_at"))
        if item["status"] == "notified" and due and now() >= due:
            item["status"] = "approved"
            item["approved_at"] = iso(now())
            _refresh(item, st, "✅ 자동 승인됨 (시간 내 응답 없음)", [])
            changed = True
            log.info("자동 승인: %s", item["id"])
    return changed


# ================================================================= 발행
def publish_due(items: list[dict], st: dict) -> bool:
    changed = False
    published = {c: 0 for c in st["channels"]}
    for i in items:
        if i["date"] == today() and i["status"] == "published":
            published[i["channel"]] = published.get(i["channel"], 0) + 1

    due = [i for i in items
           if i["status"] == "approved" and now() >= (parse(i["publish_at"]) or now())]
    due.sort(key=lambda i: i["publish_at"])

    for item in due:
        ch = item["channel"]
        label = CHANNEL_LABEL.get(ch, ch)
        cap = st["channels"][ch].get("daily_publish_cap", 99)
        if published.get(ch, 0) >= cap:
            log.warning("[%s] 오늘 발행 한도(%d) 도달 -> 보류", ch, cap)
            continue

        mod = PUBLISHERS.get(ch)
        image = None
        if item.get("media_kind") in ("photo", "auto") and item.get("media_file_id"):
            image = tg.download(item["media_file_id"])

        if mod is None:
            ok, info = False, "NO_KEYS"
        elif ch == "x":
            ok, info = mod.post(item["text"], image)
        else:
            ok, info = mod.post(item["text"])

        if ok:
            item["status"] = "published"
            item["published_at"] = iso(now())
            item["post_url"] = info
            item["error"] = None
            store.add_history(ch, item["text"])
            published[ch] = published.get(ch, 0) + 1
            _refresh(item, st, "\U0001f680 발행 완료\n" + info, [])
            log.info("발행 완료: %s -> %s", item["id"], info)

        elif info == "NO_KEYS":
            item["status"] = "published"
            item["published_at"] = iso(now())
            item["post_url"] = "(직접 올림)"
            store.add_history(ch, item["text"])
            published[ch] = published.get(ch, 0) + 1
            buttons = [[{"text": "\U0001f4ee {}에 올리기".format(label),
                         "url": INTENT[ch].format(quote(item["text"]))}]] if ch in INTENT else None
            if item.get("media_kind") == "video":
                tg.send("\U0001f3ac 아래 영상을 저장해서 X에 올려주세요.", None)
            _refresh(item, st, "\U0001f4ee 아래 버튼을 눌러 직접 올려주세요", buttons)
            log.info("수동 발행 안내: %s", item["id"])

        else:
            item["retry"] = item.get("retry", 0) + 1
            item["error"] = info
            if item["retry"] >= 3:
                item["status"] = "failed"
                _refresh(item, st, "⚠️ 발행 실패 (3회 시도)\n" + info[:200], [])
            log.warning("발행 실패(%d회): %s / %s", item["retry"], item["id"], info)
        changed = True
    return changed


# ================================================================= 요약
def summary(today_items: list[dict]) -> str:
    if not today_items:
        return "오늘 만들어진 글이 없습니다."
    name = {"draft": "알림 전", "notified": "승인 대기", "edit_requested": "수정 중",
            "media_requested": "사진 대기", "approved": "승인됨",
            "published": "발행 완료", "rejected": "삭제됨", "failed": "발행 실패"}
    box: dict = {}
    for i in today_items:
        box[i["status"]] = box.get(i["status"], 0) + 1
    lines = ["\U0001f4ca 오늘({}) 현황".format(today()), LINE]
    lines += ["{}: {}개".format(name.get(k, k), v) for k, v in box.items()]
    return "\n".join(lines)


def main() -> None:
    st = settings()
    items = store.load_queue()
    state = store.load_state()

    changed = False
    changed |= process_telegram(items, state, st)
    changed |= notify_due(items, st)
    changed |= auto_approve(items, st)
    changed |= publish_due(items, st)

    if changed:
        store.save_queue(items)
        store.save_state(state)
        log.info("변경 사항 저장 완료")
    else:
        log.info("변경 없음")


if __name__ == "__main__":
    main()
