"""구글 상위 글 벤치마킹.

상위 노출 글을 **구조 분석용으로만** 본다.
가져오는 것: 공통으로 다루는 항목, 제목 패턴, 화법, 그들이 빠뜨린 틈.
가져오지 않는 것: 문장, 표현, 문단, 그들이 주장하는 사실.
사실은 사용자 경험과 지도 API에서만 온다.

검색 경로:
  1) 구글 Custom Search API (무료 하루 100건) — 키가 있으면 진짜 상위 10개를 본다.
  2) 키가 없으면 검색 없이 일반적인 구성만 추정한다(정확도 낮음).
"""
from __future__ import annotations

import json
import re

import requests

import llm
from common import env, log, scrub

CSE = "https://www.googleapis.com/customsearch/v1"

SYSTEM = """너는 한국 블로그 검색 결과를 분석해 '글의 뼈대'만 뽑아내는 사람이다.

반드시 지킬 것:
- 남의 글 문장·표현·문단을 옮기지 않는다. 제목도 그대로 베끼지 않는다.
- 상위 글이 말하는 가격·시간·주차 같은 **사실을 가져오지 않는다.**
  내가 확인한 것이 아니기 때문이다. 어떤 **항목**을 다루는지만 본다.
- 아래 JSON 형식으로만 답한다.

{
  "covered_items": ["상위 글들이 공통으로 담는 정보 항목"],
  "title_patterns": ["제목이 짜여지는 방식 (예: 지역명 + 업종 + 아이랑)"],
  "tone": "상위 글들의 화법을 한 문장으로",
  "keywords": ["같이 검색되는 말 5개 이내"],
  "gaps": ["상위 글 대부분이 안 다루는 것 — 채우면 이길 수 있는 틈"],
  "must_ask": ["이 주제로 쓰려면 글쓴이에게 꼭 물어봐야 할 사실"]
}"""

SCHEMA = {"covered_items": [""], "title_patterns": [""], "tone": "",
          "keywords": [""], "gaps": [""], "must_ask": [""]}


def search(query: str, n: int = 10) -> list[dict]:
    """구글 상위 결과를 가져온다. 키가 없으면 빈 목록."""
    key, cx = env("GOOGLE_CSE_KEY"), env("GOOGLE_CSE_ID")
    if not (key and cx):
        return []
    try:
        r = requests.get(CSE, timeout=30, params={
            "key": key, "cx": cx, "q": query, "num": min(n, 10), "hl": "ko", "lr": "lang_ko"})
        r.raise_for_status()
        items = r.json().get("items", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("구글 검색 실패: %s", scrub(e))
        return []
    return [{"rank": i, "title": it.get("title", ""),
             "snippet": it.get("snippet", ""), "link": it.get("link", "")}
            for i, it in enumerate(items, 1)]


def analyze(place_name: str = "", topic: str = "") -> dict | None:
    """상호명이나 주제로 상위 글의 뼈대를 분석한다."""
    base = (place_name or topic or "").strip()
    if not base:
        return None
    query = f"{place_name} 아이랑" if place_name else base

    top = search(query)
    if top:
        log.info("구글 상위 %d개 확인: %s", len(top), query)
        listing = "\n".join(f'{t["rank"]}. {t["title"]} | {t["snippet"]}' for t in top)
        user = (f'검색어: "{query}"\n\n'
                f"아래는 구글 상위 노출 글의 제목과 요약이다.\n{listing}\n\n"
                "이 글들의 뼈대만 분석해라. 문장과 사실은 가져오지 마라.")
    else:
        log.info("검색 키 없음 -> 구성 추정 모드: %s", query)
        user = (f'검색어: "{query}"\n\n'
                "이 검색어로 한국 블로그를 검색하면 상위에 어떤 구성의 글이 나올지 "
                "일반적인 패턴으로 추정해라. 확실하지 않으면 gaps 에 적어라.")

    out = llm.complete_json(SYSTEM, user, SCHEMA)
    if not out:
        return None
    out["_searched"] = bool(top)
    out["_sources"] = [t["link"] for t in top]
    log.info("공통 항목 %d개 / 빈틈 %d개%s",
             len(out.get("covered_items", [])), len(out.get("gaps", [])),
             "" if top else " (추정)")
    return out


def to_prompt(bm: dict) -> str:
    """분석 결과를 글쓰기 지시문으로 바꾼다."""
    head = "[상위 노출 글 분석 — 구성 참고용]" if bm.get("_searched") else \
           "[상위 글 구성 추정 — 참고용, 실제 검색 결과 아님]"
    lines = [head,
             "아래는 남의 글에서 가져온 사실이 아니라 '어떤 항목을 다루는지'에 대한 분석이다.",
             "이 항목들을 목차로 삼되, 내용은 **사용자가 말해준 경험으로만** 채운다.",
             "사용자가 말해주지 않은 항목은 쓰지 말고 missing 에 적는다."]
    if bm.get("covered_items"):
        lines.append("공통으로 다루는 항목: " + ", ".join(bm["covered_items"]))
    if bm.get("tone"):
        lines.append("상위 글들의 화법: " + bm["tone"] + " (참고하되 문장은 새로 쓴다)")
    if bm.get("keywords"):
        lines.append("같이 검색되는 말: " + ", ".join(bm["keywords"]))
    if bm.get("gaps"):
        lines.append("상위 글이 안 다루는 틈(여기를 채우면 이긴다): " + ", ".join(bm["gaps"]))
    return "\n".join(lines)
