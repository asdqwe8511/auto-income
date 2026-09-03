"""초안 + 사진 -> 확인용 HTML 팝업.

글 / 사진 / 글 / 사진 순으로 맥락마다 사진을 끼운다.
자동 발행은 하지 않는다. 사람이 보고 직접 티스토리에 올린다.
"""
from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path

from blog.config import out_dir

CSS = """
:root{--bg:#F4F6F2;--card:#fff;--ink:#1D231E;--ink2:#4C584E;--line:#D7DED2;--accent:#1F6A47;--warn:#8E5C0C;--warnbg:#F6EAD4}
@media(prefers-color-scheme:dark){:root{--bg:#131714;--card:#1A201B;--ink:#E7EDE6;--ink2:#AFBBB1;--line:#2D362E;--accent:#71C295;--warn:#DDA850;--warnbg:#342D1D}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.75 "Malgun Gothic",system-ui,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:32px 20px 80px;display:flex;flex-direction:column;gap:24px}
h1{font-size:27px;line-height:1.3;margin:0}
.meta{display:flex;flex-wrap:wrap;gap:8px}
.chip{font:12px ui-monospace,monospace;background:var(--card);border:1px solid var(--line);border-radius:99px;padding:4px 11px;color:var(--ink2)}
.chip.ok{border-color:var(--accent);color:var(--accent)}
.warn{background:var(--warnbg);border-left:3px solid var(--warn);padding:14px 16px;border-radius:3px;font-size:14.5px}
.post{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:26px 28px;display:flex;flex-direction:column;gap:18px}
h2{font-size:20px;margin:14px 0 0}
p{margin:0}
figure{margin:0;display:flex;flex-direction:column;gap:6px}
figure img{width:100%;border-radius:5px;display:block}
figcaption{font-size:13px;color:var(--ink2)}
.slot{font:12px ui-monospace,monospace;color:var(--accent)}
.bar{position:sticky;bottom:0;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:14px 16px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
button{font:14px inherit;padding:9px 16px;border-radius:5px;border:1px solid var(--accent);background:var(--accent);color:#fff;cursor:pointer}
button.ghost{background:transparent;color:var(--accent)}
.note{font-size:13px;color:var(--ink2)}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{border:1px solid var(--line);padding:8px 12px;text-align:left}
th{width:34%;background:var(--bg)}
"""


def _place_table(place: dict) -> str:
    rows = []
    order = ["상호", "분류", "도로명주소", "전화", "주차", "최대수용인원", "대기여부"]
    for k in order:
        v = place.get(k)
        rows.append(f"<tr><th>{k}</th><td>{html.escape(v) if v else '<i>미확인 — 직접 채우세요</i>'}</td></tr>")
    link = place.get("지도링크")
    if link:
        rows.append(f'<tr><th>지도</th><td><a href="{html.escape(link)}">{html.escape(link)}</a></td></tr>')
    return "<table>" + "".join(rows) + "</table>"


def build(draft: dict, photos: list[Path], place: dict | None,
          mosaic_warn: list[str]) -> Path:
    """확인용 HTML 을 만들고 경로를 돌려준다."""
    caps = draft.get("photo_captions") or []
    blocks: list[str] = []
    plain: list[str] = []          # 티스토리에 붙여넣을 순수 본문

    def add_photo(i: int) -> None:
        if i >= len(photos):
            return
        cap = caps[i] if i < len(caps) else ""
        blocks.append(
            f'<figure><span class="slot">[사진 {i+1}] {html.escape(photos[i].name)}</span>'
            f'<img src="{photos[i].as_uri()}" alt="">'
            f'<figcaption>{html.escape(cap)}</figcaption></figure>')
        plain.append(f"[사진 {i+1}] {cap}")

    intro = draft.get("intro", "")
    blocks.append(f"<p>{html.escape(intro).replace(chr(10), '<br>')}</p>")
    plain.append(intro)

    photo_i = 0
    add_photo(photo_i); photo_i += 1                       # 글 다음 사진

    sections = draft.get("sections", [])
    for s in sections:
        head = s.get("heading", "")
        blocks.append(f"<h2>{html.escape(head)}</h2>")
        plain.append(f"\n## {head}")
        for para in [p for p in s.get("body", "").split("\n") if p.strip()]:
            blocks.append(f"<p>{html.escape(para)}</p>")
            plain.append(para)
        if place and s is sections[0]:
            blocks.append(_place_table(place))
            plain.append("[장소 정보 표 — 티스토리에서 표로 다시 만드세요]")
        add_photo(photo_i); photo_i += 1                   # 맥락마다 한 장

    while photo_i < len(photos):                           # 남은 사진은 뒤에 이어 붙임
        add_photo(photo_i); photo_i += 1

    outro = draft.get("outro", "")
    blocks.append(f"<p>{html.escape(outro)}</p>")
    plain.append(outro)

    tags = draft.get("tags", [])
    missing = draft.get("missing", [])
    warns = ""
    if mosaic_warn:
        warns += ('<div class="warn"><b>사진 확인 필요</b><br>' +
                  html.escape(", ".join(mosaic_warn)) +
                  " — 글자 검출에 실패했습니다. 한글이 그대로 보이는지 직접 보고 올리세요.</div>")
    if missing:
        warns += ('<div class="warn"><b>정보가 부족해 비워둔 부분</b><br>' +
                  html.escape(" / ".join(missing)) + "</div>")

    body = "".join(blocks)
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>{html.escape(draft.get('title', '초안'))}</title><style>{CSS}</style></head><body>
<div class="wrap">
  <h1>{html.escape(draft.get('title', ''))}</h1>
  <div class="meta">
    <span class="chip ok">공백 제외 {draft.get('_chars_nospace', 0)}자</span>
    <span class="chip">소주제 {len(sections)}개</span>
    <span class="chip">사진 {len(photos)}장</span>
    <span class="chip">태그 {len(tags)}개</span>
  </div>
  {warns}
  <div class="post">{body}</div>
  <div class="meta">{"".join(f'<span class="chip">{html.escape(t)}</span>' for t in tags)}</div>
  <div class="bar">
    <button onclick="copyBody()">본문 복사</button>
    <button class="ghost" onclick="copyTags()">태그 복사</button>
    <span class="note">복사해서 티스토리에 붙여넣고, [사진 n] 자리에 같은 번호 사진을 올리세요. 자동 발행은 하지 않습니다.</span>
  </div>
</div>
<script>
const BODY = {json.dumps(chr(10).join(plain), ensure_ascii=False)};
const TAGS = {json.dumps(", ".join(tags), ensure_ascii=False)};
function flash(msg){{ const b=document.querySelector('.note'); const old=b.textContent; b.textContent=msg; setTimeout(()=>b.textContent=old,1500); }}
function copyBody(){{ navigator.clipboard.writeText(BODY).then(()=>flash('본문을 복사했어요.')); }}
function copyTags(){{ navigator.clipboard.writeText(TAGS).then(()=>flash('태그를 복사했어요.')); }}
</script>
</body></html>"""

    path = out_dir() / "preview.html"
    path.write_text(doc, encoding="utf-8")
    return path


def popup(path: Path) -> None:
    """기본 브라우저로 확인 창을 띄운다."""
    webbrowser.open(path.as_uri())
