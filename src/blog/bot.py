"""텔레그램으로 사진 + 설명을 받아 블로그 초안을 만든다.

쓰는 법 (텔레그램에서):
  /새글            -> 새 글 시작 (모아둔 것 비움)
  사진 여러 장 전송  -> 순서대로 모임
  설명 아무렇게나 전송 -> 글감이 됨
  상호: ○○식당      -> 지도에서 장소 사실을 가져옴
  주차: 무료 20대    -> 지도에 없는 항목은 이렇게 직접 알려줌
  /완성            -> 초안 생성 후 PC 브라우저에 확인 창이 뜸
"""
from __future__ import annotations

import time
from pathlib import Path

from common import env, log
from blog import benchmark, mosaic, place as place_mod, render, wire, writer
from blog.config import blog_cfg, out_dir

DIRECT_KEYS = ("상호", "주차", "최대수용인원", "대기여부")

HELP = """📝 블로그 글쓰기 봇

/새글 — 새로 시작
사진 여러 장 — 순서대로 모입니다
설명 — 아무렇게나 적어 보내면 글감이 됩니다
상호: ○○식당 — 지도에서 장소 정보를 가져옵니다
주차: 무료 20대 / 대기여부: 20분 — 직접 본 것만 적어주세요
/완성 — 초안을 만들고 PC에 확인 창을 띄웁니다
/취소 — 모아둔 것 버리기

자동 발행은 하지 않습니다. 확인하고 직접 올리세요."""


class Session:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.photos: list[Path] = []
        self.lines: list[str] = []
        self.facts: dict = {}

    @property
    def empty(self) -> bool:
        return not self.photos and not self.lines


def _say(chat_id, text: str) -> None:
    wire.say(chat_id, text)


def _handle_photo(sess: Session, chat_id, msg: dict) -> None:
    photo = max(msg["photo"], key=lambda p: p.get("file_size", 0))   # 가장 큰 해상도
    raw_dir = out_dir() / "raw"
    raw_dir.mkdir(exist_ok=True)
    n = len(sess.photos) + 1
    saved = wire.download(photo["file_id"], raw_dir / f"{n:02d}.jpg")
    if not saved:
        _say(chat_id, "사진을 받지 못했어요. 다시 보내주세요.")
        return
    sess.photos.append(saved)
    if msg.get("caption"):
        sess.lines.append(msg["caption"])
    _say(chat_id, f"사진 {len(sess.photos)}장 모았어요.")


def _handle_text(sess: Session, chat_id, text: str) -> None:
    head = text.split(":", 1)[0].strip()
    if ":" in text and head in DIRECT_KEYS:
        sess.facts[head] = text.split(":", 1)[1].strip()
        _say(chat_id, f"{head} 기록했어요.")
        return
    sess.lines.append(text)
    _say(chat_id, "설명 받았어요. 더 있으면 계속 보내고, 다 됐으면 /완성")


def _build(sess: Session, chat_id) -> None:
    if sess.empty:
        _say(chat_id, "아직 받은 게 없어요. 사진이나 설명을 먼저 보내주세요.")
        return

    _say(chat_id, "초안 만드는 중이에요. 1~2분 걸려요.")

    # 1) 사진에서 한글 가리기
    done_dir = out_dir() / "photo"
    done_dir.mkdir(exist_ok=True)
    ready: list[Path] = []
    warn: list[str] = []
    for i, src in enumerate(sess.photos, 1):
        dst = done_dir / f"{i:02d}.jpg"
        ok, hits = mosaic.apply(src, dst)
        ready.append(dst)
        if not ok:
            warn.append(dst.name)
        else:
            log.info("%s: 글자 %d곳 가림", dst.name, hits)

    # 2) 상호명이 있으면 지도에서 사실만 가져오기
    place = None
    if sess.facts.get("상호"):
        place = place_mod.lookup(sess.facts["상호"])
        if place:
            place = place_mod.merge_user_facts(place, sess.facts)
        else:
            _say(chat_id, f"'{sess.facts['상호']}' 를 지도에서 못 찾았어요. 장소 정보 없이 씁니다.")

    # 3) 상위 글 뼈대 분석 (문장·사실은 가져오지 않음)
    bench = ""
    if blog_cfg().get("벤치마킹", {}).get("켜기", True):
        _say(chat_id, "상위 글 구성을 살펴보는 중이에요.")
        bm = benchmark.analyze(sess.facts.get("상호", ""),
                               " ".join(sess.lines)[:60])
        if bm:
            bench = benchmark.to_prompt(bm)

    # 4) 글 쓰기
    draft = writer.write("\n".join(sess.lines), place, len(ready), bench)
    if not draft:
        _say(chat_id, "글 생성에 실패했어요. 잠시 뒤 /완성 을 다시 눌러주세요.")
        return

    # 5) 확인 창 띄우기 (자동 발행 없음)
    path = render.build(draft, ready, place, warn)
    render.popup(path)

    msg = [f"✅ 초안 완성 — {draft.get('title','')}",
           f"공백 제외 {draft.get('_chars_nospace',0)}자 · 사진 {len(ready)}장",
           f"PC 브라우저에 확인 창을 띄웠어요.\n{path}"]
    if warn:
        msg.append(f"⚠️ 글자 검출 실패: {', '.join(warn)} — 직접 확인하세요.")
    if draft.get("missing"):
        msg.append("ℹ️ 더 알려주면 좋을 것: " + " / ".join(draft["missing"]))
    _say(chat_id, "\n".join(msg))
    sess.reset()


def run() -> None:
    problem = wire.check()
    if problem:
        log.error("시작할 수 없습니다.%s%s", chr(10), problem)
        return

    sess = Session()
    offset = None
    log.info("블로그 글쓰기 봇 시작. 텔레그램에서 /새글 을 보내보세요. (끄려면 Ctrl+C)")

    while True:
        updates = wire.call("getUpdates", offset=offset, timeout=20,
                            allowed_updates=["message"]) or []
        for up in updates:
            offset = up["update_id"] + 1
            msg = up.get("message") or up.get("channel_post")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text = (msg.get("text") or "").strip()

            if text.startswith("/새글"):
                sess.reset()
                _say(chat_id, "새 글 시작할게요. 사진과 설명을 보내주세요.")
            elif text.startswith("/취소"):
                sess.reset()
                _say(chat_id, "버렸어요.")
            elif text.startswith("/완성"):
                _build(sess, chat_id)
            elif text.startswith(("/도움말", "/start", "/help")):
                _say(chat_id, HELP)
            elif msg.get("photo"):
                _handle_photo(sess, chat_id, msg)
            elif text:
                _handle_text(sess, chat_id, text)
        time.sleep(1)


if __name__ == "__main__":
    run()
