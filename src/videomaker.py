"""영상에 문구를 얹어 카드뉴스 스타일로 가공한다. (ffmpeg 사용)

세로(9:16 등) : 영상 그대로 두고 아래쪽에 어두운 띠 + 문구
가로(16:9 등) : 위아래에 검은 여백을 만들어 위에는 아이디, 아래에는 문구

원본 영상은 사용자가 직접 올린 것이어야 한다. 남의 영상을 가공해 올리면 저작권 침해다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from cardmaker import FONT_CANDIDATES
from common import log, settings


def _cfg() -> dict:
    return settings().get("video", {})


def available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _font_path() -> str | None:
    for path in FONT_CANDIDATES["bold"]:
        if Path(path).exists():
            return path
    return None


def _ff_escape(text: str) -> str:
    """drawtext 필터에 넣을 수 있게 특수문자를 막아준다."""
    out = text.replace("\\", "").replace(":", "\\:").replace("'", "")
    return out.replace("%", "").replace(",", " ").replace("[", "(").replace("]", ")")


def _probe(path: Path) -> tuple[int, int, float] | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60)
        stream = json.loads(r.stdout)["streams"][0]
        return int(stream["width"]), int(stream["height"]), float(stream.get("duration") or 0)
    except (subprocess.SubprocessError, KeyError, ValueError, IndexError) as e:
        log.warning("영상 정보를 읽지 못했습니다: %s", e)
        return None


def _wrap_for_video(text: str, per_line: int) -> str:
    """글자 수 기준으로 어절 단위 줄바꿈."""
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 <= per_line or not line:
            line = f"{line} {w}".strip()
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    return "\n".join(lines[:3])


def make(video_bytes: bytes, headline: str, footer: str = "") -> bytes | None:
    """영상 + 문구 -> 가공된 mp4 바이트. 실패하면 None."""
    if not available():
        log.warning("ffmpeg 가 없어서 영상 가공을 건너뜁니다.")
        return None
    font = _font_path()
    if not font:
        log.warning("한글 폰트를 찾지 못해 영상 가공을 건너뜁니다.")
        return None

    cfg = _cfg()
    max_sec = int(cfg.get("max_seconds", 140))

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.mp4"
        dst = Path(tmp) / "out.mp4"
        src.write_bytes(video_bytes)

        info = _probe(src)
        if not info:
            return None
        w, h, dur = info
        portrait = h >= w
        target_w = int(cfg.get("width", 1080))

        # ffmpeg 의 drawtext 는 윈도우 경로의 콜론을 싫어한다
        font_arg = font.replace("\\", "/").replace(":", "\\:")

        if portrait:
            # 세로 영상: 그대로 두고 아래쪽에 반투명 띠 + 문구
            scale_h = int(target_w * h / w / 2) * 2
            head = _ff_escape(_wrap_for_video(headline, 16))
            band_h = int(scale_h * 0.26)
            filters = (
                f"scale={target_w}:{scale_h},"
                f"drawbox=x=0:y={scale_h - band_h}:w={target_w}:h={band_h}:"
                f"color=black@0.62:t=fill,"
                f"drawtext=fontfile='{font_arg}':text='{head}':"
                f"fontcolor=white:fontsize={int(target_w * 0.062)}:"
                f"line_spacing={int(target_w * 0.020)}:"
                f"x={int(target_w * 0.075)}:y={scale_h - band_h + int(band_h * 0.20)}"
            )
            if footer:
                filters += (
                    f",drawtext=fontfile='{font_arg}':text='{_ff_escape(footer)}':"
                    f"fontcolor=white@0.75:fontsize={int(target_w * 0.030)}:"
                    f"x={int(target_w * 0.075)}:y={scale_h - int(target_w * 0.055)}"
                )
        else:
            # 가로 영상: 위아래 검은 여백을 만들고 거기에 글자를 넣는다
            scale_h = int(target_w * h / w / 2) * 2
            pad_h = int(target_w * 4 / 3 / 2) * 2          # 3:4 세로 캔버스
            if pad_h < scale_h + int(target_w * 0.36):
                pad_h = scale_h + int(target_w * 0.36)
                pad_h = int(pad_h / 2) * 2
            top = int((pad_h - scale_h) / 2 / 2) * 2
            head = _ff_escape(_wrap_for_video(headline, 18))
            filters = (
                f"scale={target_w}:{scale_h},"
                f"pad={target_w}:{pad_h}:0:{top}:color=black,"
                f"drawtext=fontfile='{font_arg}':text='{_ff_escape(footer or '')}':"
                f"fontcolor=white@0.85:fontsize={int(target_w * 0.034)}:"
                f"x=(w-text_w)/2:y={max(20, int(top * 0.42))},"
                f"drawtext=fontfile='{font_arg}':text='{head}':"
                f"fontcolor=white:fontsize={int(target_w * 0.052)}:"
                f"line_spacing={int(target_w * 0.018)}:"
                f"x=(w-text_w)/2:y={top + scale_h + int(top * 0.22)}"
            )

        cmd = ["ffmpeg", "-y", "-i", str(src), "-t", str(max_sec),
               "-vf", filters, "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        cmd += ["-c:a", "aac", "-b:a", "128k"] if cfg.get("keep_audio", True) else ["-an"]
        cmd.append(str(dst))

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except subprocess.SubprocessError as e:
            log.warning("영상 가공 실패: %s", e)
            return None
        if r.returncode != 0 or not dst.exists():
            log.warning("ffmpeg 오류: %s", (r.stderr or "")[-500:])
            return None

        data = dst.read_bytes()
        log.info("영상 가공 완료 (%s, %.1f초, %.1fMB)",
                 "세로" if portrait else "가로", dur, len(data) / 1024 / 1024)
        return data
