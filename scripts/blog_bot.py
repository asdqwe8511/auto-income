"""블로그 글쓰기 봇 실행 진입점."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from blog.bot import run  # noqa: E402

if __name__ == "__main__":
    run()
