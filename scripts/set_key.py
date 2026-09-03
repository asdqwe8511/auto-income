"""키를 물어보고 .env 에 안전하게 저장합니다.  (메모장 없이, 붙여넣기만 하면 끝)

실행: 프로젝트 폴더의 `키넣기.bat` 을 더블클릭하세요.
"""
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
EXAMPLE = os.path.join(ROOT, ".env.example")

# (환경변수 이름, 화면에 보여줄 설명, 이렇게 시작하면 정상(여러개 가능), 필수인가)
GROUPS = {
    "basic": [
        ("GEMINI_API_KEY", "[필수] Gemini API 키  (aistudio.google.com/apikey)", ("AQ.", "AIza"), True),
        ("TELEGRAM_BOT_TOKEN", "[필수] 텔레그램 봇 토큰  (@BotFather 가 준 것)", (), True),
        ("BLOG_BOT_TOKEN", "[블로그봇] 블로그 전용 텔레그램 봇 토큰  (위 봇과 반드시 다른 봇)", (), False),
        ("GOOGLE_CSE_KEY", "[선택] 구글 검색 API 키  (상위 글 벤치마킹용)", ("AIza",), False),
        ("GOOGLE_CSE_ID", "[선택] 구글 검색엔진 ID  (cx 값)", (), False),
        ("KAKAO_REST_API_KEY", "[선택] 카카오 REST API 키  (블로그 글의 장소 정보용)", (), False),
        ("COUPANG_ACCESS_KEY", "[선택] 쿠팡파트너스 ACCESS KEY  (2단계에서 사용)", (), False),
        ("COUPANG_SECRET_KEY", "[선택] 쿠팡파트너스 SECRET KEY  (2단계에서 사용)", (), False),
    ],
    "x": [
        ("X_API_KEY", "X - API Key  (Consumer Keys 의 첫 번째)", (), True),
        ("X_API_SECRET", "X - API Key Secret  (Consumer Keys 의 두 번째)", (), True),
        ("X_ACCESS_TOKEN", "X - Access Token  (숫자-문자 형태)", (), True),
        ("X_ACCESS_TOKEN_SECRET", "X - Access Token Secret", (), True),
    ],
}
FIELDS = GROUPS["basic"]


def read_env() -> dict[str, str]:
    if not os.path.exists(ENV):
        if os.path.exists(EXAMPLE):
            io.open(ENV, "w", encoding="utf-8").write(io.open(EXAMPLE, encoding="utf-8").read())
        else:
            io.open(ENV, "w", encoding="utf-8").write("")
    values = {}
    for raw in io.open(ENV, encoding="utf-8"):
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            name, _, val = raw.partition("=")
            values[name.strip()] = val.strip()
    return values


def write_env(updates: dict[str, str]) -> None:
    """기존 파일의 주석과 순서를 그대로 유지하면서 값만 갈아끼운다."""
    lines = io.open(ENV, encoding="utf-8").read().splitlines()
    done = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.split("=", 1)[0].strip()
            if name in updates:
                out.append(f"{name}={updates[name]}")
                done.add(name)
                continue
        out.append(line)
    for name, val in updates.items():
        if name not in done:
            out.append(f"{name}={val}")
    io.open(ENV, "w", encoding="utf-8").write("\n".join(out) + "\n")


def mask(val: str) -> str:
    if len(val) <= 8:
        return "*" * len(val)
    return val[:4] + "*" * (len(val) - 8) + val[-4:]


def ask(name: str, label: str, prefixes: tuple[str, ...], current: str) -> str | None:
    print()
    print("─" * 58)
    print(f"  {label}")
    if current:
        print(f"  지금 저장된 값: {mask(current)}")
        print("  그대로 두려면 그냥 Enter 를 누르세요.")
    print("─" * 58)
    try:
        value = input("  붙여넣고 Enter > ").strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print("\n  취소했습니다.")
        return None

    if not value:
        return current or ""
    if not value.isascii():
        print("  ⚠️  한글이 섞여 있습니다. 키를 다시 복사해서 붙여넣어 주세요. (건너뜁니다)")
        return current or ""
    if prefixes and not value.startswith(prefixes):
        print("  ⚠️  보통 " + " 또는 ".join(prefixes) + " 로 시작하는데 다릅니다. 그래도 저장할까요?")
        try:
            if input("  저장하려면 y, 다시 하려면 Enter > ").strip().lower() != "y":
                return ask(name, label, prefixes, current)
        except (EOFError, KeyboardInterrupt):
            return current or ""
    print(f"  ✅ 받았습니다: {mask(value)}  (바로 저장됩니다)")
    return value


def main() -> None:
    global FIELDS
    group = sys.argv[1].lower() if len(sys.argv) > 1 else "basic"
    FIELDS = GROUPS.get(group, GROUPS["basic"])

    print("=" * 58)
    print("  키 입력 도우미" + ("  [X 자동 발행용]" if group == "x" else ""))
    print("  키를 복사(Ctrl+C)한 뒤, 이 창에 붙여넣고 Enter 를 누르세요.")
    print("  * 붙여넣기가 안 되면 마우스 오른쪽 클릭 한 번 = 붙여넣기 입니다.")
    print("  * 건너뛰려면 아무것도 안 치고 그냥 Enter.")
    print("=" * 58)

    current = read_env()
    updates = dict(current)
    for name, label, prefix, _required in FIELDS:
        got = ask(name, label, prefix, current.get(name, ""))
        if got is None:
            print("\n  여기까지 입력한 내용은 이미 저장돼 있습니다. 창을 닫으셔도 됩니다.")
            return
        updates[name] = got
        write_env({name: got})      # 하나 받을 때마다 바로 저장 (중간에 멈춰도 안전)

    print()
    print("=" * 58)
    print("  .env 에 저장했습니다.")
    print("=" * 58)
    for name, _label, _prefix, required in FIELDS:
        val = updates.get(name, "")
        mark = "✅" if val else ("❌ 아직 비어있음" if required else "⚠️  비어있음")
        print(f"  {name:22} {mark}")
    print()
    if all(updates.get(n) for n, _l, _p, req in FIELDS if req):
        print("  다음 단계: 이 창을 닫고, 연결 검사를 돌려달라고 하세요.")
        if group == "x":
            print("  (X 앱 권한이 'Read and write' 인지 꼭 확인하세요. 아니면 발행이 실패합니다)")
    else:
        print("  비어있는 항목이 있습니다. 이 파일을 다시 실행해서 채우면 됩니다.")


if __name__ == "__main__":
    main()
