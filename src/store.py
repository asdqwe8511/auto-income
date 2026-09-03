"""JSON 파일 저장소. (DB 없이 깃 저장소 자체를 데이터베이스로 쓴다)"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common import DATA_DIR, now, iso, parse, settings

QUEUE = DATA_DIR / "queue.json"      # 오늘/최근 글 목록
STATE = DATA_DIR / "state.json"      # 텔레그램 offset 등 내부 상태
HISTORY = DATA_DIR / "history.json"  # 과거 발행 글(중복 방지용)


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_queue() -> list[dict]:
    return _read(QUEUE, {"items": []}).get("items", [])


def save_queue(items: list[dict], replace: bool = False) -> None:
    """저장 직전에 파일을 다시 읽어 합친다.

    봇이 도는 중에 글 생성이 새 항목을 넣으면, 봇이 들고 있던 옛 목록으로
    통째로 덮어써서 새 글이 사라진다. 그래서 '내가 모르는 항목'은 살려 둔다.
    일부러 지우려는 경우에는 replace=True 로 통째 교체한다.
    """
    if replace:
        _write(QUEUE, {"updated_at": iso(now()), "items": items})
        return

    known = {it.get("id") for it in items}
    on_disk = _read(QUEUE, {"items": []}).get("items", [])
    kept = [it for it in on_disk if it.get("id") not in known]
    if kept:
        from common import log
        log.info("다른 작업이 새로 넣은 %d개를 함께 보존합니다.", len(kept))
    merged = kept + items
    merged.sort(key=lambda it: (it.get("date", ""), it.get("publish_at", "")))
    _write(QUEUE, {"updated_at": iso(now()), "items": merged})


def load_state() -> dict:
    return _read(STATE, {})


def save_state(state: dict) -> None:
    _write(STATE, state)


def load_history() -> list[dict]:
    return _read(HISTORY, {"items": []}).get("items", [])


def save_history(items: list[dict]) -> None:
    cutoff_days = settings().get("history_days", 60)
    cutoff = now().timestamp() - cutoff_days * 86400
    kept = [
        h for h in items
        if (parse(h.get("at")) or now()).timestamp() >= cutoff
    ]
    _write(HISTORY, {"items": kept[-1000:]})


def add_history(channel: str, text: str) -> None:
    items = load_history()
    items.append({"at": iso(now()), "channel": channel, "text": text})
    save_history(items)


def find(items: list[dict], item_id: str) -> dict | None:
    for it in items:
        if it.get("id") == item_id:
            return it
    return None
