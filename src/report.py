"""매일 밤 23시: 오늘 하루 요약을 텔레그램으로 보낸다. (성과 루프의 1단계 버전)"""
from __future__ import annotations

import store
import tg
from common import log, today, settings

CHANNEL_LABEL = {"x": "X", "threads": "스레드"}
LINE = "─────────────"


def build() -> str:
    st = settings()
    items = [i for i in store.load_queue() if i["date"] == today()]
    if not items:
        return "\U0001f4ca 오늘({}) 만들어진 글이 없습니다.\n생성 워크플로가 돌았는지 확인해 주세요.".format(today())

    lines = ["\U0001f4ca 오늘({}) 마감 보고".format(today()), LINE]
    for ch in st["channels"]:
        mine = [i for i in items if i["channel"] == ch]
        if not mine:
            continue
        pub = [i for i in mine if i["status"] == "published"]
        rej = [i for i in mine if i["status"] == "rejected"]
        fail = [i for i in mine if i["status"] == "failed"]
        wait = [i for i in mine if i["status"] in ("draft", "notified", "approved", "edit_requested")]
        lines.append("[{}] 발행 {} / 삭제 {} / 실패 {} / 대기 {}".format(
            CHANNEL_LABEL.get(ch, ch), len(pub), len(rej), len(fail), len(wait)))

    fails = [i for i in items if i["status"] == "failed"]
    if fails:
        lines += ["", "⚠️ 실패한 글"]
        lines += ["· {} — {}".format(i["id"], (i.get("error") or "")[:80]) for i in fails[:5]]

    links = [i for i in items if i["status"] == "published" and str(i.get("post_url", "")).startswith("http")]
    if links:
        lines += ["", "\U0001f517 오늘 올라간 글"]
        lines += ["· " + i["post_url"] for i in links[:10]]

    lines += ["", "내일 아침 7시에 다시 만나요."]
    return "\n".join(lines)


def main() -> None:
    text = build()
    tg.send(text)
    log.info("일일 보고 발송 완료")
    print(text)


if __name__ == "__main__":
    main()
