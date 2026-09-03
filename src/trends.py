"""오늘의 트렌드 수집. 무료 소스만 사용하고, 실패해도 시스템은 계속 돈다."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from common import log

SOURCES = [
    "https://trends.google.co.kr/trending/rss?geo=KR",
    "https://trends.google.com/trending/rss?geo=KR",
]

# 글감으로 못 쓰는 주제는 아예 걸러낸다 (사고 방지)
BLOCKLIST = (
    "사망", "부고", "별세", "사고", "화재", "지진", "참사", "실종", "확진",
    "성폭", "마약", "살인", "테러", "전쟁", "폭행", "구속", "檢", "선거",
    "대통령", "의원", "정당", "코스피", "주가", "비트코인", "코인",
)


def fetch(limit: int = 12) -> list[str]:
    """구글 트렌드 실시간 검색어(한국). 실패하면 빈 리스트."""
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            words = [
                (t.text or "").strip()
                for t in root.iter("title")
                if (t.text or "").strip()
            ]
            words = words[1:]  # 첫 title은 피드 제목
            clean = [w for w in words if not any(b in w for b in BLOCKLIST)]
            if clean:
                log.info("트렌드 %d개 수집: %s", len(clean[:limit]), ", ".join(clean[:5]))
                return clean[:limit]
        except (requests.RequestException, ET.ParseError) as e:
            log.warning("트렌드 수집 실패(%s): %s", url, e)
    log.warning("트렌드를 못 가져왔습니다. 주제 은행(topics.yml)만 사용합니다.")
    return []
