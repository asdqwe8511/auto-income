"""콘텐츠 엔진: 트렌드 수집 -> 카테고리별 글 생성 -> 슬롯에 섞어 배치 -> 예약 큐 저장."""
from __future__ import annotations

import random
import sys
from datetime import timedelta
from difflib import SequenceMatcher

import llm
import news
import store
import trends
from common import log, settings, topics, pillars, now, today, iso, at_time

SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "text": {"type": "string"},
                    "source_no": {"type": "integer"},
                },
                "required": ["topic", "text", "source_no"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["posts"],
    "additionalProperties": False,
}


def _require_key() -> None:
    if not llm.ready():
        log.error("%s 가 없습니다. .env 또는 GitHub Secrets를 확인하세요. (현재 엔진: %s)",
                  llm.key_name(), llm.provider())
        sys.exit(1)


def _too_similar(text: str, past: list[str], threshold: float) -> bool:
    return any(SequenceMatcher(None, text, p).ratio() >= threshold for p in past)


# ------------------------------------------------------------------ 프롬프트 만들기
def _system_prompt(channel: str, pillar: str, spec: dict, max_chars: int) -> str:
    channel_rule = {
        "x": "X(트위터)에 올릴 글이다. 링크와 해시태그는 쓰지 않는다.",
        "threads": ("스레드(Threads)에 올릴 글이다. 마지막 줄은 반드시 가벼운 질문으로 끝내서 "
                    "댓글을 유도한다. 해시태그는 0~2개까지만."),
    }.get(channel, "")

    return "\n".join([
        "너는 한국어 소셜미디어 카피라이터다. 아래 규칙을 어기면 결과물은 폐기된다.",
        "설명하지 말고 결과만 낸다.",
        "",
        f"## 이 글의 목적 [{spec['label']}]",
        spec["goal"].strip(),
        "",
        "## 쓰는 방법",
        spec["guide"].strip(),
        "",
        "## 절대 금지",
        spec["never"].strip(),
        "",
        "## 형식 규칙 (모든 글에 공통, 반드시 지킬 것)",
        "1. 두괄식으로 쓴다. 첫 줄에 결론이나 가장 강한 한마디를 먼저 던진다.",
        "   배경 설명부터 시작하면 스크롤에서 그냥 지나간다.",
        "2. 한 줄은 30자 안팎으로 끊는다. 길면 의미가 끊기는 자리에서 줄을 바꾼다.",
        "3. 조사나 어미 앞에서 줄을 끊지 않는다. (X: '고정 지출을\\n밖으로' / O: '고정 지출을 밖으로\\n빼낸다')",
        "4. 2~3줄마다 빈 줄을 하나 넣어 덩어리를 나눈다. 빽빽하면 안 읽힌다.",
        "5. 띄어쓰기를 정확히 지킨다. 붙여 쓰면 읽는 속도가 떨어진다.",
        "",
        "## 채널 규칙",
        channel_rule,
        f"한 글당 {max_chars}자 이내(공백 포함). 글 전체를 따옴표로 감싸지 말 것.",
        "",
        "## 이런 느낌 (베끼지 말고 톤만 참고)",
        spec["example"].strip(),
    ])


def _user_prompt(pillar: str, count: int, trend_words: list[str], past: list[str],
                 headlines: list[str] | None = None) -> str:
    bank = topics().get(pillar, [])
    picked = random.sample(bank, min(6, len(bank))) if bank else []
    parts = [f"오늘은 {today()} 입니다. 위 규칙에 맞는 글 {count}개를 만들어 주세요."]

    if headlines:
        parts += [
            "",
            "## 지금 사람들이 많이 보는 뉴스 (제목만 있습니다)",
            "여기서 서로 다른 기사를 골라 한 개씩 쓰세요.",
            "⚠️ 아래 제목에 적힌 것 말고는 아무 사실도 지어내지 마세요. 본문은 없습니다.",
            *headlines,
            "",
            "각 글마다 source_no 에 사용한 기사 번호를 적어주세요. "
            "뉴스를 안 쓴 글은 0 을 적습니다.",
        ]

    parts += [
        "",
        "## 글감 후보 (이 중에서 고르거나, 비슷한 결로 새로 잡아도 됩니다)",
        "- " + (", ".join(picked) if picked else "자유"),
    ]
    if pillar == "humor" and trend_words:
        parts += ["",
                  "## 오늘 화제인 검색어",
                  "어울리는 것만 한두 개 자연스럽게 녹이세요. 억지로 끼워 맞추면 안 됩니다.",
                  "- " + ", ".join(trend_words)]
    if not headlines:
        parts += ["", "source_no 에는 0 을 적어주세요. (참고한 기사가 없습니다)"]

    parts += [
        "",
        "## 반드시 피할 것 (최근에 이미 올린 글)",
        ("\n".join(f"- {p}" for p in past[-20:]) if past else "- (아직 없음)"),
        "",
        f"posts 배열에 {count}개를 담아 주세요. text 에는 올릴 본문만 넣고 번호나 설명은 넣지 마세요.",
        "서로 소재와 문장 구조를 최대한 다르게 하세요.",
    ]
    return "\n".join(parts)


# ------------------------------------------------------------------ 생성
def generate_pillar(channel: str, pillar: str, count: int, cfg: dict,
                    trend_words: list[str], past: list[str],
                    news_items: list[dict] | None = None) -> list[dict]:
    spec = pillars().get(pillar)
    if not spec:
        log.error("config/pillars.yml 에 '%s' 카테고리가 없습니다. 건너뜁니다.", pillar)
        return []

    st = settings()
    limit = min(int(spec.get("max_chars", cfg["max_chars"])), cfg["max_chars"])
    system = _system_prompt(channel, pillar, spec, limit)
    sources = news.for_pillar(pillar, news_items or [], max(4, count * 2))
    headlines = news.as_prompt_lines(sources)
    if headlines:
        log.info("[%s/%s] 뉴스 글감 %d건 사용", channel, pillar, len(headlines))
    got: list[dict] = []

    for attempt in range(2):        # 중복이 많으면 한 번 더
        need = count - len(got)
        if need <= 0:
            break
        data = llm.complete_json(
            system,
            _user_prompt(pillar, need, trend_words, past + [g["text"] for g in got], headlines),
            SCHEMA)
        if not data:
            log.error("[%s/%s] 글을 받지 못했습니다 (시도 %d).", channel, pillar, attempt + 1)
            continue
        for p in data.get("posts", []):
            body = (p.get("text") or "").strip().strip('"')
            if not body or len(body) > limit * 1.2:
                continue
            if _too_similar(body, past + [g["text"] for g in got], st["similarity_threshold"]):
                log.info("[%s/%s] 과거 글과 유사 -> 버림: %s", channel, pillar, body[:25])
                continue
            entry = {"pillar": pillar, "topic": p.get("topic", ""), "text": body,
                     "needs_check": bool(spec.get("needs_check")),
                     "source_url": None, "source_press": None, "source_title": None}
            try:
                no = int(str(p.get("source_no") or 0).strip())
            except ValueError:
                no = 0
            if 1 <= no <= len(sources):
                src = sources[no - 1]
                entry["source_url"] = src.get("url")
                entry["source_press"] = src.get("press")
                entry["source_title"] = src.get("title")
            got.append(entry)

    log.info("[%s] %s %d/%d개", channel, spec["label"], len(got), count)
    return got[:count]


def generate_channel(channel: str, cfg: dict, trend_words: list[str],
                     news_items: list[dict]) -> list[dict]:
    past = [h["text"] for h in store.load_history() if h.get("channel") == channel]
    posts: list[dict] = []
    for pillar, count in cfg.get("mix", {}).items():
        posts += generate_pillar(channel, pillar, count, cfg, trend_words,
                                 past + [p["text"] for p in posts], news_items)
    return posts


# ------------------------------------------------------------------ 슬롯 배치
def to_queue_items(channel: str, cfg: dict, posts: list[dict]) -> list[dict]:
    """카테고리가 한 슬롯에 몰리지 않도록 섞어서 아침/점심/저녁에 나눠 담는다."""
    st = settings()
    date = today()

    # 카테고리별로 줄을 세운 뒤 번갈아 뽑으면 자연스럽게 섞인다
    by_pillar: dict[str, list[dict]] = {}
    for p in posts:
        by_pillar.setdefault(p["pillar"], []).append(p)
    queues = list(by_pillar.values())
    mixed: list[dict] = []
    while any(queues):
        for q in queues:
            if q:
                mixed.append(q.pop(0))

    # 슬롯에 카드 돌리듯 배분한다. 슬롯을 하나씩 채우면 뒤쪽 슬롯이
    # 남은 카테고리(보통 유머)로만 채워지기 때문에 반드시 번갈아 넣는다.
    buckets: dict[str, list[dict]] = {slot: [] for slot in cfg["slots"]}
    slot_names = list(cfg["slots"])
    turn = 0
    for p in mixed:
        for _ in range(len(slot_names)):
            slot = slot_names[turn % len(slot_names)]
            turn += 1
            if len(buckets[slot]) < cfg["slots"][slot]:
                buckets[slot].append(p)
                break

    items: list[dict] = []
    for slot in slot_names:
        base = at_time(date, st["slots"][slot])
        for idx, p in enumerate(buckets[slot]):
            publish_at = base + timedelta(minutes=idx * cfg["publish_gap_minutes"])
            items.append({
                "id": f"{date}-{channel}-{slot}-{idx + 1}",
                "date": date,
                "channel": channel,
                "slot": slot,
                "idx": idx,
                "pillar": p["pillar"],
                "needs_check": p["needs_check"],
                "source_url": p.get("source_url"),
                "source_press": p.get("source_press"),
                "source_title": p.get("source_title"),
                "topic": p.get("topic", ""),
                "text": p["text"],
                "status": "draft",
                "created_at": iso(now()),
                "notify_at": iso(base),
                "publish_at": iso(publish_at),
                "notified_at": None,
                "auto_approve_at": None,
                "approved_at": None,
                "published_at": None,
                "post_url": None,
                "retry": 0,
                "error": None,
                "tg_message_id": None,
            })
    return items


def main() -> None:
    st = settings()
    _require_key()
    log.info("글 생성 엔진: %s", llm.provider())
    trend_words = trends.fetch()
    news_items = news.fetch()

    if [it for it in store.load_queue() if it["date"] == today()]:
        log.info("오늘(%s) 큐가 이미 있습니다. 새로 만들지 않습니다.", today())
        return

    keep = [it for it in store.load_queue() if it["date"] != today()][-200:]
    fresh: list[dict] = []

    for channel, cfg in st["channels"].items():
        if not cfg.get("enabled"):
            continue
        items = to_queue_items(channel, cfg,
                               generate_channel(channel, cfg, trend_words, news_items))
        log.info("[%s] 총 %d개 배치 완료", channel, len(items))
        fresh += items

    store.save_queue(keep + fresh)
    log.info("총 %d개를 오늘 큐에 넣었습니다.", len(fresh))


def rewrite(channel: str, original: str, instruction: str, max_chars: int,
            pillar: str = "humor") -> str | None:
    """텔레그램에서 '✏️ 수정'을 누르고 지시를 보냈을 때 글을 다시 씁니다."""
    spec = pillars().get(pillar) or pillars().get("humor", {})
    system = _system_prompt(channel, pillar, spec, max_chars) if spec else \
        "너는 한국어 소셜미디어 카피라이터다. 결과 본문만 낸다."
    user = ("아래 글을 사용자의 지시대로 고쳐 주세요.\n\n"
            f"[원문]\n{original}\n\n[지시]\n{instruction}\n\n"
            f"{max_chars}자 이내. 고친 본문만 출력하세요.")
    return llm.complete_text(system, user)


def headline(text: str, max_chars: int = 24) -> str:
    """이미지 아래에 얹을 후킹 문구. 요약이 아니라 '멈춰서 읽게 만드는' 한 줄."""
    system = "\n".join([
        "너는 카드뉴스 표지 문구를 쓰는 편집자다. 결과 문구 한 줄만 출력한다.",
        "",
        "[규칙]",
        f"- {max_chars}자 이내. 한 호흡에 읽혀야 한다.",
        "- 스크롤을 멈추게 하는 게 목적이다. 본문을 요약하지 마라.",
        "- 읽는 사람이 '어? 나도 그런데' 또는 '그래서 뭔데?' 하게 만들어라.",
        "- 손해·놓침·오해를 건드리면 잘 멈춘다.",
        "- 문장부호로 끝내지 마라. 물음표는 써도 된다.",
        "- 과장이나 낚시는 금지. 본문에 없는 내용을 지어내지 마라.",
        "- 해시태그, 이모지, 따옴표 금지.",
        "",
        "[좋은 예]",
        "월급날 이것부터 안 하면 돈이 샌다",
        "구독료는 앱이 아니라 여기서 끊긴다",
        "싼 멀티탭을 사면 절반은 못 쓴다",
    ])
    got = llm.complete_text(system, f"[본문]\n{text}\n\n표지 문구 한 줄만 출력하세요.")
    if got:
        got = got.splitlines()[0].strip().strip('"').strip("'").rstrip(".…")
        if 0 < len(got) <= max_chars * 1.5:
            return got
    return text.strip().splitlines()[0][:max_chars].rstrip()


if __name__ == "__main__":
    main()
