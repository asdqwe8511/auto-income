"""'.env' 에 값이 제대로 들어갔는지 확인합니다. 키 내용은 절대 화면에 안 보여줍니다."""
import io
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if not os.path.exists(PATH):
    print(".env 파일이 없습니다."); sys.exit(1)

print(f"{'항목':26} {'길이':>4}  {'상태'}")
print("-" * 60)
for raw in io.open(PATH, encoding="utf-8"):
    raw = raw.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    name, _, val = raw.partition("=")
    name, val = name.strip(), val.strip()
    if not val:
        state = "비어있음"
    elif not val.isascii():
        state = "!! 예시 문구가 그대로 남아있음 -> 실제 키로 바꾸세요"
    elif val.startswith(("AQ.", "AIza", "sk-ant-")) or ":" in val:
        state = "OK (" + val[:4] + "...)"
    else:
        state = "값 있음 (" + val[:2] + "...)"
    print(f"{name:26} {len(val):>4}  {state}")
