"""config/blog.yml 을 읽어온다."""
from __future__ import annotations

import yaml

from common import CONFIG_DIR, ROOT


def blog_cfg() -> dict:
    with open(CONFIG_DIR / "blog.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def out_dir():
    d = ROOT / blog_cfg().get("출력폴더", "data/blog")
    d.mkdir(parents=True, exist_ok=True)
    return d
