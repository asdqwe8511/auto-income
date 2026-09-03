"""X 자동 업로드 봇 — 상시 감시 모드.

몇 초마다 tick 을 돌려서 텔레그램 버튼이 바로바로 반응하게 합니다.
클라우드(GitHub Actions)에서는 10분마다 도니까 이 파일은 필요 없습니다.
내 컴퓨터에서 눌러보며 확인할 때 씁니다. Ctrl+C 로 멈춥니다.

⚠️ 반드시 하나만 돌아야 합니다. 두 개가 돌면 서로가 보낸 메시지를 지웁니다.
   그래서 잠금 파일(data/watch.lock)로 중복 실행을 막습니다.

실행: 폴더의 `테스트모드.bat` 더블클릭
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

import tick  # noqa: E402
from common import DATA_DIR, log  # noqa: E402

INTERVAL = 5              # 초
LOCK = DATA_DIR / "watch.lock"
STALE = INTERVAL * 4      # 이보다 오래 갱신이 없으면 죽은 것으로 본다


def _another_is_running() -> bool:
    if not LOCK.exists():
        return False
    return (time.time() - LOCK.stat().st_mtime) < STALE


def main() -> None:
    if _another_is_running():
        print("=" * 58)
        print("  이미 봇이 돌고 있습니다. 이 창은 닫아주세요.")
        print("  (봇이 두 개면 서로 메시지를 지워서 글이 사라집니다)")
        print("=" * 58)
        return

    print("=" * 58)
    print("  X 자동 업로드 봇 — 텔레그램 버튼이 바로 반응합니다")
    print(f"  {INTERVAL}초마다 확인합니다. 멈추려면 Ctrl+C")
    print("=" * 58)

    rounds = 0
    try:
        while True:
            LOCK.write_text(str(os.getpid()), encoding="utf-8")   # 살아있다는 표시
            try:
                tick.main()
            except KeyboardInterrupt:
                raise
            except Exception:              # noqa: BLE001 - 멈추면 안 된다
                log.error("오류가 났지만 계속 돕니다:\n%s", traceback.format_exc())
            rounds += 1
            if rounds % 12 == 0:
                print(f"  … {rounds * INTERVAL}초째 감시 중 (Ctrl+C 로 종료)")
            time.sleep(INTERVAL)
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n감시를 멈췄습니다.")
