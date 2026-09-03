"""텔레그램 대화창에 쌓인 봇 메시지를 지웁니다.

봇은 자기가 보낸 메시지만, 그것도 48시간 안의 것만 지울 수 있습니다.
실행: python scripts/clean_chat.py [훑을 개수, 기본 300]
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

import store  # noqa: E402
import tg  # noqa: E402


def main() -> None:
    if not tg.enabled():
        print("텔레그램 설정이 없습니다.")
        return

    logging.getLogger("auto-income").setLevel(logging.ERROR)  # 실패 경고가 도배되지 않게

    known = [it.get("tg_message_id") for it in store.load_queue() if it.get("tg_message_id")]
    probe = tg.send("\U0001f9f9 대화창을 정리하는 중입니다…")
    top = max([m for m in known + [probe] if m] or [0])
    if not top:
        print("지울 메시지를 찾지 못했습니다.")
        return

    span = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    removed = 0
    for mid in range(top, max(0, top - span), -1):
        if tg.call("deleteMessage", chat_id=tg._chat(), message_id=mid) is not None:
            removed += 1

    print(f"{top}번부터 {span}개를 훑어 {removed}개를 지웠습니다.")

    items = store.load_queue()
    for it in items:
        it["tg_message_id"] = None
        it["tg_is_photo"] = False
    store.save_queue(items)
    print("큐에 남아 있던 메시지 기록도 비웠습니다.")


if __name__ == "__main__":
    main()
