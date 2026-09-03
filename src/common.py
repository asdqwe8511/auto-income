"""공통 유틸: 경로, 설정, 시간(한국시간), 로그."""
from __future__ import annotations

import os
import re
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")  # 로컬 실행용. GitHub Actions에서는 Secrets가 환경변수로 들어온다.

KST = timezone(timedelta(hours=9))

# 윈도우 콘솔에서 한글/이모지가 깨지거나 오류나지 않도록
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("auto-income")


def settings() -> dict:
    with open(CONFIG_DIR / "settings.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def topics() -> dict:
    with open(CONFIG_DIR / "topics.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pillars() -> dict:
    with open(CONFIG_DIR / "pillars.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, default: str = "") -> str:
    """환경변수 읽기. 예시 문구가 그대로 남아 있으면 '안 넣은 것'으로 취급한다."""
    value = (os.environ.get(name) or default).strip().strip('"').strip("'")
    if not value:
        return ""
    if not value.isascii():          # '여기에붙여넣기' 같은 안내 문구
        log.warning("%s 에 예시 문구가 그대로 남아 있습니다. 실제 키로 바꿔주세요.", name)
        return ""
    if value.lower() in ("123456789", "1234567890", "your_key_here", "changeme"):
        log.warning("%s 가 예시값 그대로입니다. 실제 값으로 바꿔주세요.", name)
        return ""
    return value


def has_env(*names: str) -> bool:
    return all(env(n) for n in names)


def now() -> datetime:
    """지금(한국시간)."""
    return datetime.now(KST)


def today() -> str:
    return now().strftime("%Y-%m-%d")


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def at_time(date_str: str, hhmm: str) -> datetime:
    """'2026-08-31' + '07:00' -> 한국시간 datetime."""
    h, m = (int(x) for x in hhmm.split(":"))
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return datetime(d.year, d.month, d.day, h, m, tzinfo=KST)


_SECRET = re.compile(r"(key=|x-goog-api-key[\"'\s:]+)[A-Za-z0-9._:\-]{8,}|\d{8,12}:[A-Za-z0-9_\-]{30,}")


def scrub(text) -> str:
    """로그에 남기기 전 키·토큰처럼 생긴 문자열을 가린다."""
    return _SECRET.sub("[가림]", str(text))
