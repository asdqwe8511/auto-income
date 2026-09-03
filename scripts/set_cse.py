"""구글 검색용 키 2개만 물어보고 .env 에 저장합니다."""
from __future__ import annotations

import io
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env")


def load() -> list[str]:
    if not os.path.exists(ENV):
        io.open(ENV, "w", encoding="utf-8").write("")
    return io.open(ENV, encoding="utf-8").read().splitlines()


def get(lines: list[str], name: str) -> str:
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and s.split("=", 1)[0].strip() == name:
            return s.split("=", 1)[1].strip()
    return ""


def save(updates: dict[str, str]) -> None:
    lines, done = load(), set()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            name = s.split("=", 1)[0].strip()
            if name in updates:
                out.append(f"{name}={updates[name]}")
                done.add(name)
                continue
        out.append(line)
    for k, v in updates.items():
        if k not in done:
            out.append(f"{k}={v}")
    io.open(ENV, "w", encoding="utf-8").write("\n".join(out) + "\n")


def ask(title: str, hint: str, shape: str, current: str) -> str:
    print()
    print("─" * 62)
    print(f"  {title}")
    print(f"  {hint}")
    print(f"  생김새: {shape}")
    if current:
        print(f"  지금 값: {current[:6]}***  (그대로 두려면 Enter)")
    print("─" * 62)
    try:
        return input("  붙여넣고 Enter > ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        return ""


def main() -> None:
    lines = load()
    print("=" * 62)
    print("  구글 상위 글 벤치마킹 - 키 2개 넣기")
    print("=" * 62)

    key = ask("① GOOGLE_CSE_KEY  (API 키)",
              "console.cloud.google.com > 사용자 인증 정보 > API 키",
              "AIzaSy...", get(lines, "GOOGLE_CSE_KEY"))
    cid = ask("② GOOGLE_CSE_ID  (검색엔진 ID)",
              "programmablesearchengine.google.com > 설정 > 기본 > 검색엔진 ID",
              "a1b2c3d4e5f6g7h8i", get(lines, "GOOGLE_CSE_ID"))

    updates = {}
    if key:
        if ":" in key:
            print("\n  ✗ 텔레그램 봇 토큰처럼 보입니다. API 키가 맞는지 확인해 주세요.")
            return
        if not key.startswith("AIza"):
            print("\n  ⚠ 보통 AIza 로 시작합니다. 그래도 저장하려면 y, 아니면 Enter")
            if input("  > ").strip().lower() != "y":
                return
        updates["GOOGLE_CSE_KEY"] = key
    if cid:
        updates["GOOGLE_CSE_ID"] = cid

    if not updates:
        print("\n  입력한 값이 없어 저장하지 않았습니다.")
        return

    save(updates)
    print("\n  ✓ 저장했습니다. 실제로 검색되는지 확인합니다...")

    lines = load()
    k, c = get(lines, "GOOGLE_CSE_KEY"), get(lines, "GOOGLE_CSE_ID")
    if not (k and c):
        print("  (둘 다 있어야 검색됩니다. 나머지 하나를 마저 넣어주세요.)")
        return
    try:
        import requests
        r = requests.get("https://www.googleapis.com/customsearch/v1", timeout=30,
                         params={"key": k, "cx": c, "q": "초등학생 아침 등교 준비",
                                 "num": 3, "hl": "ko", "lr": "lang_ko"})
        if r.status_code == 200:
            items = r.json().get("items", [])
            print(f"  ✓ 검색 성공 — 상위 {len(items)}개를 받아왔습니다.")
            for i, it in enumerate(items, 1):
                print(f"    {i}. {it.get('title', '')[:50]}")
            print("\n  이제 블로그 봇이 실제 상위 글을 보고 분석합니다.")
        else:
            msg = r.json().get("error", {}).get("message", "")[:150]
            print(f"  ✗ 검색 실패 ({r.status_code})")
            print(f"    {msg}")
            print("    - API 가 '사용 설정' 됐는지, 검색엔진 ID가 맞는지 확인해 주세요.")
    except Exception as e:  # noqa: BLE001
        print(f"  (확인 실패: {e})")


if __name__ == "__main__":
    main()
