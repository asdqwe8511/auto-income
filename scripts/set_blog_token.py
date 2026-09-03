"""블로그 봇 토큰 하나만 물어보고 .env 에 저장합니다."""
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
NAME = "BLOG_BOT_TOKEN"


def load() -> list[str]:
    if not os.path.exists(ENV):
        io.open(ENV, "w", encoding="utf-8").write("")
    return io.open(ENV, encoding="utf-8").read().splitlines()


def value_of(lines: list[str], name: str) -> str:
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and s.split("=", 1)[0].strip() == name:
            return s.split("=", 1)[1].strip()
    return ""


def save(lines: list[str], token: str) -> None:
    out, done = [], False
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and s.split("=", 1)[0].strip() == NAME:
            out.append(f"{NAME}={token}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{NAME}={token}")
    io.open(ENV, "w", encoding="utf-8").write("\n".join(out) + "\n")


def main() -> None:
    lines = load()
    print("=" * 60)
    print("  블로그 봇 토큰 넣기")
    print("=" * 60)
    print()
    print("  텔레그램에서 @BotFather 에게 /newbot 을 보내 만든")
    print("  **새 봇**의 토큰을 붙여넣으세요.")
    print("  생김새:  1234567890:AAH_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    print()
    print("  붙여넣기 = 마우스 오른쪽 클릭 (또는 Ctrl+V)")
    print()

    try:
        token = input("  토큰 > ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print("\n  취소했습니다.")
        return

    if not token:
        print("\n  아무것도 입력하지 않아 저장하지 않았습니다.")
        return
    if ":" not in token or not token.isascii():
        print("\n  ⚠ 토큰 형태가 아닙니다. (숫자:문자 모양이어야 합니다)")
        print("     그래도 저장할까요? 저장하려면 y, 아니면 Enter")
        if input("  > ").strip().lower() != "y":
            print("  저장하지 않았습니다.")
            return
    if token == value_of(lines, "TELEGRAM_BOT_TOKEN"):
        print("\n  ✗ 기존 시스템 봇과 같은 토큰입니다. 새 봇을 만들어 주세요.")
        return

    save(lines, token)
    print("\n  ✓ 저장했습니다.")

    try:
        import requests
        r = requests.post(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json()
        if r.get("ok"):
            print(f"  ✓ 연결 확인:  @{r['result'].get('username')}")
            print("\n  이제 `블로그봇.bat` 을 실행하면 됩니다.")
        else:
            print(f"  ✗ 텔레그램이 거부했습니다: {r.get('description')}")
            print("    토큰을 다시 확인해 주세요.")
    except Exception as e:  # noqa: BLE001
        print(f"  (연결 확인 실패: {e})")


if __name__ == "__main__":
    main()
