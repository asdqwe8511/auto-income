"""상호명 -> 장소 사실 정보.

지도 API(카카오)에서 '사실'만 가져온다. 이름, 주소, 전화, 분류, 좌표, 지도 링크.
주차/최대수용인원/대기여부는 지도에 없는 정보라 비워두고,
사용자가 직접 본 것을 적어 넣도록 남긴다. 다른 블로그 글을 옮겨 적지 않는다.
"""
from __future__ import annotations

import requests

from common import env, log

SEARCH = "https://dapi.kakao.com/v2/local/search/keyword.json"


def lookup(name: str) -> dict | None:
    """상호명으로 장소를 찾는다. 못 찾으면 None."""
    key = env("KAKAO_REST_API_KEY")
    if not key:
        log.warning("KAKAO_REST_API_KEY 없음 -> 장소 정보 건너뜀")
        return None
    try:
        r = requests.get(SEARCH, params={"query": name, "size": 5},
                         headers={"Authorization": f"KakaoAK {key}"}, timeout=15)
        r.raise_for_status()
        docs = r.json().get("documents", [])
    except (requests.RequestException, ValueError) as e:
        log.warning("카카오 장소 검색 실패: %s", e)
        return None
    if not docs:
        return None

    d = docs[0]
    return {
        "상호": d.get("place_name", ""),
        "분류": (d.get("category_name") or "").split(">")[-1].strip(),
        "도로명주소": d.get("road_address_name", ""),
        "지번주소": d.get("address_name", ""),
        "전화": d.get("phone", ""),
        "지도링크": d.get("place_url", ""),
        "좌표": {"lat": d.get("y", ""), "lng": d.get("x", "")},
        # 아래 셋은 지도에 없는 정보다. 사용자가 말해준 것만 채운다.
        "주차": "",
        "최대수용인원": "",
        "대기여부": "",
    }


def merge_user_facts(place: dict, said: dict) -> dict:
    """사용자가 텔레그램에서 직접 말해준 값으로 빈칸을 채운다."""
    for k in ("주차", "최대수용인원", "대기여부"):
        if said.get(k):
            place[k] = said[k]
    return place
