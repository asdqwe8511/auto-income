"""실시간 뉴스 글감 수집.

내 news-ranking 사이트의 news.json 을 읽어서, 안전한 섹션의 화제 기사만 뽑는다.
기사 본문/사진/영상은 절대 가져오지 않는다. 제목과 섹션만 '글감'으로 쓴다.
(언론사 저작물을 재배포하면 저작권 침해이자 X 정책 위반이다)
"""
from __future__ import annotations

import html

import requests

from common import log, settings


def _cfg() -> dict:
    return settings().get("news", {})


def enabled() -> bool:
    return bool(_cfg().get("url"))


def fetch() -> list[dict]:
    """news.json 전체를 가져온다. 실패하면 빈 리스트 (시스템은 계속 돈다)."""
    url = _cfg().get("url")
    if not url:
        return []
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "auto-income/1.0"})
        r.raise_for_status()
        items = r.json().get("items", [])
        for it in items:                       # &#x27; 같은 특수문자를 사람이 읽는 글자로
            it["title"] = html.unescape(it.get("title") or "")
        log.info("뉴스 %d건 수집", len(items))
        return items
    except (requests.RequestException, ValueError) as e:
        log.warning("뉴스 수집 실패: %s (글감 은행으로 대체합니다)", e)
        return []


def _is_safe(item: dict, cfg: dict) -> bool:
    section = (item.get("section") or "").strip()
    title = item.get("title") or ""
    if section in cfg.get("block_sections", []):
        return False
    if any(word in title for word in cfg.get("block_keywords", [])):
        return False
    if item.get("commentCount", 0) < cfg.get("min_comments", 0):
        return False
    return True


def for_pillar(pillar: str, items: list[dict], limit: int = 8) -> list[dict]:
    """이 카테고리에 어울리는 섹션의 기사만, 화제성 높은 순으로."""
    cfg = _cfg()
    wanted = cfg.get("sections", {}).get(pillar, [])
    if not wanted or not items:
        return []

    picked = [
        it for it in items
        if (it.get("section") or "").strip() in wanted and _is_safe(it, cfg)
    ]
    picked.sort(key=lambda i: (i.get("hotScore", 0), i.get("commentCount", 0)), reverse=True)

    # 섹션별로 줄을 세운 뒤 번갈아 뽑는다.
    # 안 그러면 그날 화제인 사건 하나가 목록을 다 차지해서 글이 전부 같은 얘기가 된다.
    lanes: dict[str, list[dict]] = {}
    for it in picked:
        lanes.setdefault((it.get("section") or "").strip(), []).append(it)

    seen_head: list[str] = []
    seen_word: set[str] = set()
    unique: list[dict] = []
    while len(unique) < limit and any(lanes.values()):
        for lane in list(lanes.values()):
            if not lane or len(unique) >= limit:
                continue
            it = lane.pop(0)
            title = it.get("title") or ""
            if title[:12] in seen_head:
                continue
            # 같은 인물·기업이 계속 나오지 않게 (제목의 굵직한 낱말로 판단)
            words = {w for w in title.replace('"', " ").split() if len(w) >= 3}
            if words & seen_word:
                continue
            seen_head.append(title[:12])
            seen_word |= words
            unique.append(it)
    return unique


def as_prompt_lines(items: list[dict]) -> list[str]:
    """AI에게 넘길 글감 줄. 앞에 번호를 붙여서 어느 기사를 썼는지 되짚을 수 있게 한다."""
    return [
        "{}. [{}] {} ({}, 댓글 {}개)".format(
            n, it.get("section", ""), it.get("title", ""),
            it.get("press", ""), it.get("commentCount", 0))
        for n, it in enumerate(items, 1)
    ]
