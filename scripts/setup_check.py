"""설정이 제대로 됐는지 한 번에 검사합니다.  실행:  python scripts/setup_check.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402

from common import env  # noqa: E402

OK, NO, WARN = "✅", "❌", "⚠️ "
problems: list[str] = []


def title(t: str) -> None:
    print("\n" + "=" * 46)
    print(t)
    print("=" * 46)


def check_llm() -> None:
    import llm
    name = llm.provider()
    title(f"1. 글을 만드는 AI 엔진 [{name}] — 필수")
    print("   (엔진을 바꾸려면 config/settings.yml 의 llm.provider 를 고치세요)")

    if not llm.ready():
        print(NO, f"{llm.key_name()} 가 없습니다.")
        problems.append(f"{llm.key_name()} 를 .env 에 넣으세요."
                        + ("  ← aistudio.google.com/apikey 에서 무료 발급" if name == "gemini" else ""))
        return

    answer = llm.complete_text("너는 테스트용 도우미다.", "'연결 성공' 이라고만 답해줘.")
    if answer:
        print(OK, f"{name} 연결됨 →", answer[:30])
    else:
        print(NO, f"{name} 연결 실패 (위 로그의 오류 메시지를 확인하세요)")
        if name == "gemini":
            problems.append("GEMINI_API_KEY 가 맞는지, settings.yml 의 llm.model 이름이 맞는지 확인하세요.")
        else:
            problems.append("ANTHROPIC_API_KEY 가 맞는지, 크레딧이 충전돼 있는지 확인하세요.")


def check_telegram() -> None:
    title("2. 텔레그램 봇 (승인 버튼) — 필수")
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        print(NO, "TELEGRAM_BOT_TOKEN 이 없습니다.")
        problems.append("텔레그램에서 @BotFather 에게 /newbot 하고 받은 토큰을 .env 에 넣으세요.")
        return
    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15).json()
    except requests.RequestException as e:
        print(NO, "네트워크 오류:", e)
        return
    if not me.get("ok"):
        print(NO, "토큰이 틀렸습니다:", me.get("description"))
        problems.append("TELEGRAM_BOT_TOKEN 을 다시 확인하세요.")
        return
    print(OK, "봇 이름: @" + me["result"]["username"])

    chat = env("TELEGRAM_CHAT_ID")
    if not chat:
        print(WARN, "TELEGRAM_CHAT_ID 가 비어 있습니다. 지금 찾아볼게요…")
        print("   → 텔레그램에서 위 봇에게 아무 말이나 (예: 안녕) 보낸 뒤 이 검사를 다시 실행하세요.")
        ups = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
        ids = {str(u.get("message", {}).get("chat", {}).get("id"))
               for u in ups.get("result", []) if u.get("message")}
        ids.discard("None")
        if not ids:
            problems.append("내 봇에게 '안녕' 이라고 먼저 말을 건 뒤, 이 검사를 다시 실행하세요.")
            return

        found = sorted(ids)[0]
        sys.path.insert(0, str(ROOT / "scripts"))
        from set_key import write_env
        write_env({"TELEGRAM_CHAT_ID": found})
        os.environ["TELEGRAM_CHAT_ID"] = found
        print(OK, f"CHAT_ID {found} 를 찾아서 .env 에 자동으로 저장했습니다.")
        chat = found

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": "✅ 연결 테스트 성공! 이제 이 봇으로 글을 받게 됩니다."},
                      timeout=15).json()
    if r.get("ok"):
        print(OK, "테스트 메시지를 보냈습니다. 텔레그램을 확인하세요.")
    else:
        print(NO, "메시지 발송 실패:", r.get("description"))
        problems.append("TELEGRAM_CHAT_ID 가 맞는지 확인하세요.")


def check_x() -> None:
    title("3. X 자동 발행 — 선택 (없으면 텔레그램으로 복사용 글이 옵니다)")
    keys = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
    if not all(env(k) for k in keys):
        print(WARN, "X 키 없음 → '수동 모드'로 동작합니다. (지금은 이대로 괜찮습니다)")
        return
    try:
        from requests_oauthlib import OAuth1
        auth = OAuth1(env(keys[0]), env(keys[1]), env(keys[2]), env(keys[3]))
        r = requests.get("https://api.twitter.com/2/users/me", auth=auth, timeout=20)
        if r.status_code == 200:
            print(OK, "X 연결됨 → @" + r.json().get("data", {}).get("username", "?"))
        else:
            print(NO, f"X 연결 실패 {r.status_code}: {r.text[:200]}")
            problems.append("X 앱 권한이 'Read and write' 인지, 토큰을 권한 변경 후 재발급했는지 확인하세요.")
    except Exception as e:  # noqa: BLE001
        print(NO, "X 확인 중 오류:", e)


def check_threads() -> None:
    title("4. 스레드 자동 발행 — 선택")
    if not (env("THREADS_USER_ID") and env("THREADS_ACCESS_TOKEN")):
        print(WARN, "스레드 키 없음 → '수동 모드'로 동작합니다.")
        return
    try:
        r = requests.get(f"https://graph.threads.net/v1.0/{env('THREADS_USER_ID')}",
                         params={"fields": "username", "access_token": env("THREADS_ACCESS_TOKEN")},
                         timeout=20)
        if r.status_code == 200:
            print(OK, "스레드 연결됨 → @" + r.json().get("username", "?"))
        else:
            print(NO, f"스레드 연결 실패 {r.status_code}: {r.text[:200]}")
    except requests.RequestException as e:
        print(NO, "스레드 확인 중 오류:", e)


def main() -> None:
    if not (ROOT / ".env").exists():
        print(WARN, ".env 파일이 없습니다. .env.example 을 복사해서 .env 로 만들고 키를 채우세요.")
    check_llm()
    check_telegram()
    check_x()
    check_threads()

    title("검사 결과")
    if problems:
        print("아직 해야 할 일:")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
        sys.exit(1)
    print(OK, "전부 통과! 이제 `python src/generate.py` 로 오늘치 글을 만들어 보세요.")


if __name__ == "__main__":
    main()
