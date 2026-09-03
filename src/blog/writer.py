"""사진 설명 + 장소 사실 -> 검색형 경험 포스팅 초안.

규격(config/blog.yml): 네이버 검색 의도 / 1,500자 이상(공백 제외) /
소주제 4개(명사형) / 고민-원인-확인-해결 / "~했어요" 문체 / 태그 5개.
사용자가 말해준 것만 쓴다. 없는 경험을 지어내지 않는다.
"""
from __future__ import annotations

import re

import llm
from common import log
from blog.config import blog_cfg

SCHEMA = {
    "title": "제목",
    "keywords": ["키워드"],
    "tags": ["태그"],
    "intro": "도입 문단",
    "sections": [{"heading": "명사형 소제목", "body": "본문 여러 문단"}],
    "photo_captions": ["사진 설명"],
    "outro": "마무리 문단",
    "missing": ["더 필요한 정보"],
}


def _system() -> str:
    cfg = blog_cfg()
    who = cfg.get("화자", "아빠")
    kid = cfg.get("아이", {})
    first = kid.get("첫째", {})
    second = kid.get("둘째", {})
    spec = cfg.get("규격", {})
    return f"""너는 한국 티스토리 육아 블로그의 글을 대신 써주는 작가다.

글쓴이는 {first.get('나이', 8)}세({first.get('소속','초등학교 1학년')})와 {second.get('나이', 6)}세({second.get('소속','유치원')}) 형제를 키우는 **{who}**다.
모든 문장은 {who} 1인칭이다.

지켜야 할 규격:
1. 네이버에서 검색해 들어올 사람이 궁금해할 것에 실제로 답한다.
2. 공백 제외 {spec.get('최소글자수', 1500)}자 이상.
3. 소주제 {spec.get('소주제개수', 4)}개. 제목은 **간결한 명사형**(서술어 없이).
4. 소주제 순서는 반드시 고민 -> 원인 -> 확인 -> 해결 에 대응한다.
5. 문체는 "{spec.get('문체', '~했어요')}"로 통일. 과장·감탄사 금지.
6. 검색 키워드를 제목, 도입, 소제목 하나, 본문 2~3회에 자연스럽게 넣는다.
7. 가격·시간·개수 같은 숫자를 3개 이상 넣는다. 단, 사용자가 말해준 숫자만 쓴다.
8. 태그 {spec.get('태그개수', 5)}개. 글 내용과 무관한 범용 태그 금지.

절대 규칙:
- 사용자가 말해준 경험만 쓴다. 에피소드, 상호, 가격, 시간, 아이 반응을 **지어내지 않는다**.
- 정보가 모자라면 그 부분을 쓰지 말고 missing 배열에 무엇이 더 필요한지 적는다.
- 아이 실명, 학교·유치원 이름, 아파트 동호수, 차량 번호는 쓰지 않는다. "첫째", "둘째"로만 부른다.
- 단정적인 건강·발달 조언 금지. 경험담 어투로만 쓴다.
- 장소 정보 중 값이 비어 있는 항목은 아는 척하지 말고 아예 언급하지 않는다.

photo_captions 는 사진 장수만큼, 각 사진이 들어갈 자리의 맥락에 맞는 한 줄 설명이다."""


def _user(desc: str, place: dict | None, photo_count: int, extra: str = "") -> str:
    parts = [f"[사용자가 말해준 내용]\n{desc.strip()}"]
    if place:
        known = {k: v for k, v in place.items() if v and k != "좌표"}
        parts.append("[지도에서 확인된 장소 사실 — 이 값만 사용]\n" +
                     "\n".join(f"- {k}: {v}" for k, v in known.items()))
        empty = [k for k in ("주차", "최대수용인원", "대기여부") if not place.get(k)]
        if empty:
            parts.append("[확인되지 않은 항목 — 절대 지어내지 말고 언급하지 말 것]\n" +
                         ", ".join(empty))
    parts.append(f"[사진 {photo_count}장]\n본문 맥락에 맞게 사진 설명 {photo_count}개를 써라.")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


def body_len(draft: dict) -> int:
    """공백 제외 글자 수."""
    text = draft.get("intro", "") + draft.get("outro", "")
    for s in draft.get("sections", []):
        text += s.get("heading", "") + s.get("body", "")
    return len(re.sub(r"\s", "", text))


def write(desc: str, place: dict | None, photo_count: int,
          bench: str = "") -> dict | None:
    """초안을 만든다. 짧으면 한 번 더 늘려서 다시 받는다."""
    draft = llm.complete_json(_system(), _user(desc, place, photo_count, bench), SCHEMA)
    if not draft:
        return None

    need = blog_cfg().get("규격", {}).get("최소글자수", 1500)
    if body_len(draft) < need:
        log.info("초안이 %d자(공백 제외) -> %d자까지 늘립니다.", body_len(draft), need)
        extra = (f"[다시 쓰기] 방금 쓴 글이 공백 제외 {body_len(draft)}자로 짧다. "
                 f"{need}자를 넘기게 늘려라. 단 없는 사실을 새로 만들지 말고, "
                 "이미 말해준 상황의 앞뒤 맥락과 그때 느낀 점을 더 풀어 써라.")
        longer = llm.complete_json(_system(),
                                   _user(desc, place, photo_count,
                                         (bench + chr(10) + chr(10) + extra).strip()), SCHEMA)
        if longer and body_len(longer) > body_len(draft):
            draft = longer

    draft["_chars_nospace"] = body_len(draft)
    return draft
