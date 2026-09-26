"""
구성안 마크다운(storyboard_v1.md)을 검토용 웹 페이지(HTML)로 만든다.
사용: python3 storyboard_page.py ../storyboard_v1.md out.html [--audio ../music/preview/music_v1.mp3]
마크다운을 그대로 옮기지 않고, 샷 리스트를 필름 스트립으로, 구조를 박자 자로 다시 그린다.
"""
import base64
import html
import re
import sys


def parse_sections(md):
    """'## N. 제목' 단위로 나눈다. 반환: [(번호, 제목, 본문)]"""
    parts = re.split(r"^## (\d+)\. (.+)$", md, flags=re.M)
    out = []
    for i in range(1, len(parts), 3):
        out.append((int(parts[i]), parts[i + 1].strip(), parts[i + 2].strip()))
    return out


def parse_tables(text):
    """본문 안의 마크다운 표를 전부 찾는다. 반환: [ (헤더, 행들) ]"""
    tables, cur = [], []
    for line in text.splitlines() + [""]:
        if line.strip().startswith("|"):
            cur.append(line.strip())
        else:
            if len(cur) >= 2:
                header = [c.strip() for c in cur[0].strip("|").split("|")]
                rows = []
                for r in cur[2:]:
                    cells = [c.strip() for c in r.strip("|").split("|")]
                    if len(cells) == len(header):
                        rows.append(cells)
                tables.append((header, rows))
            cur = []
    return tables


def strip_tables(text):
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("|"))


def md_inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def md_block(text):
    """표를 뺀 마크다운 본문을 단락, 목록, 코드블록으로. 최소 구현."""
    out, buf, in_code, code = [], [], False, []
    def flush():
        if buf:
            out.append("<p>" + md_inline(" ".join(buf)) + "</p>")
            buf.clear()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.strip().startswith("```"):
            flush()
            if in_code:
                out.append("<pre class='copy'>" + html.escape("\n".join(code)) + "</pre>")
                code = []
            in_code = not in_code
            i += 1
            continue
        if in_code:
            code.append(l)
            i += 1
            continue
        if re.match(r"^\s*[-*] ", l):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                items.append("<li>" + md_inline(re.sub(r"^\s*[-*] ", "", lines[i])) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^\s*\d+\. ", l):
            flush()
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\. ", lines[i]):
                items.append("<li>" + md_inline(re.sub(r"^\s*\d+\. ", "", lines[i])) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        if not l.strip():
            flush()
        else:
            buf.append(l.strip())
        i += 1
    flush()
    return "\n".join(out)


def table_html(header, rows, cls="tbl"):
    h = "".join(f"<th>{md_inline(c)}</th>" for c in header)
    b = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<div class='scroll'><table class='{cls}'><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>"


def parse_time(s):
    m = re.match(r"\s*([\d.]+)\s*~\s*([\d.]+)", s)
    return (float(m[1]), float(m[2])) if m else (None, None)


def frame_html(text, visual, source):
    """샷의 화면을 16:9 미니 프레임으로. 검은 화면 글자는 글자 그대로, 실사는 라벨."""
    is_black = "검은 화면" in visual or source.strip() in ("없음", "")
    is_photo = "의뢰인" in source or "사진" in visual and "의뢰인" in visual
    is_logo = "로고" in visual and not text.strip() and "없음" == text.strip() or ("로고" in visual and text.strip() == "없음")
    t = text.strip()
    if t == "없음":
        t = ""
    # 슬래시로 나눈 두 줄
    lines = [x.strip() for x in t.split(" / ")] if " / " in t else [t]
    n = max(len(x) for x in lines) if t else 0
    size = "xl" if n <= 2 else "lg" if n <= 5 else "md" if n <= 12 else "sm"
    if is_black:
        cls = "frame black"
    elif is_photo:
        cls = "frame photo"
    else:
        cls = "frame footage"
    inner = "".join(f"<span>{html.escape(x)}</span>" for x in lines) if t else ""
    label = ""
    if "로고" in visual:
        label = "<em class='lbl'>로고</em>"
    elif not is_black:
        label = "<em class='lbl'>" + ("실제 사진" if is_photo else "실사") + "</em>"
    return f"<div class='{cls}'><div class='words {size}'>{inner}</div>{label}</div>"


SECTION_COLORS = ["#8ec1ff", "#5b9cf6", "#3b7fe0", "#1f63c9", "#7fb0f0", "#2f74d6", "#a6cdff", "#4a8ae6", "#6aa3f3", "#1958b8"]


def build(md, audio_b64=None, audio_mime="audio/mpeg"):
    title_m = re.search(r"^# (.+)$", md, flags=re.M)
    doc_title = title_m[1].strip() if title_m else "구성안"
    secs = {n: (t, b) for n, t, b in parse_sections(md)}

    # 1. 콘셉트
    concept_html = md_block(strip_tables(secs[1][1])) if 1 in secs else ""
    # 2. 스펙 표 → 칩
    spec_rows = parse_tables(secs[2][1])[0][1] if 2 in secs and parse_tables(secs[2][1]) else []
    chips = "".join(f"<div class='chip'><b>{md_inline(k)}</b><span>{md_inline(v)}</span></div>" for k, v in spec_rows)
    # 3. 구조 → 박자 자
    struct_tables = parse_tables(secs[3][1]) if 3 in secs else []
    struct_rows = struct_tables[0][1] if struct_tables else []
    total = 0.0
    segs = []
    for r in struct_rows:
        a, b = parse_time(r[1])
        if a is None:
            continue
        segs.append({"name": r[0], "a": a, "b": b, "purpose": r[2], "screen": r[3], "sound": r[4]})
        total = max(total, b)
    ruler = ""
    for i, s in enumerate(segs):
        w = (s["b"] - s["a"]) / total * 100
        ruler += (f"<div class='seg' style='width:{w:.3f}%;background:{SECTION_COLORS[i % len(SECTION_COLORS)]}' "
                  f"title='{html.escape(s['name'])} {s['a']:g}~{s['b']:g}s'><i>{html.escape(s['name'])}</i></div>")
    ticks = "".join(f"<span style='left:{t / total * 100:.3f}%'>{t}</span>" for t in range(0, int(total) + 1, 5))
    struct_list = "".join(
        f"<li><span class='swatch' style='background:{SECTION_COLORS[i % len(SECTION_COLORS)]}'></span>"
        f"<span class='tc'>{s['a']:g}~{s['b']:g}s</span><b>{md_inline(s['name'])}</b>"
        f"<span class='pur'>{md_inline(s['purpose'])}</span></li>" for i, s in enumerate(segs))
    struct_note = md_block(strip_tables(secs[3][1])) if 3 in secs else ""

    # 4. 샷 리스트 → 필름 스트립
    shot_tables = parse_tables(secs[4][1]) if 4 in secs else []
    shots = shot_tables[0][1] if shot_tables else []
    strip = ""
    cur_seg = None
    for r in shots:
        no, tm, beat, text, visual, source, sound, motion = (r + [""] * 8)[:8]
        a, b = parse_time(tm)
        seg = next((s for s in segs if a is not None and s["a"] <= a < s["b"]), None)
        if seg and seg is not cur_seg:
            cur_seg = seg
            idx = segs.index(seg)
            strip += (f"<h3 class='seghead'><span class='swatch' style='background:{SECTION_COLORS[idx % len(SECTION_COLORS)]}'></span>"
                      f"{md_inline(seg['name'])} <span class='tc'>{seg['a']:g}~{seg['b']:g}s</span></h3>")
        dur = f"{(b - a):g}초" if a is not None else ""
        strip += f"""<article class='shot'>
  {frame_html(text, visual, source)}
  <div class='meta'>
    <div class='row1'><span class='no'>#{html.escape(no)}</span><span class='tc'>{html.escape(tm.split(',')[0])}</span><span class='dur'>{dur}</span><span class='beat'>{html.escape(beat)}</span></div>
    <p class='vis'>{md_inline(visual)}</p>
    <dl>
      <dt>소스</dt><dd>{md_inline(source)}</dd>
      <dt>소리</dt><dd>{md_inline(sound)}</dd>
      <dt>모션</dt><dd>{md_inline(motion)}</dd>
    </dl>
  </div>
</article>"""
    shot_note = md_block(strip_tables(secs[4][1])) if 4 in secs else ""

    # 5~11
    def sec_html(n):
        if n not in secs:
            return ""
        t, b = secs[n]
        tabs = parse_tables(b)
        body = md_block(strip_tables(b))
        return f"<section id='s{n}'><h2>{md_inline(t)}</h2>{body}{''.join(table_html(h, r) for h, r in tabs)}</section>"

    audio_html = ""
    if audio_b64:
        audio_html = f"""<div class='player'><p>배경음악 v1 스케치 (50초, 신스 합성). 임팩트 시점이 구성안과 같다.</p>
<audio id='bgm' controls preload='none' src='data:{audio_mime};base64,{audio_b64}'></audio></div>"""

    page = f"""<title>김철신정형외과 브랜드 필름</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#0b0b0e; --surface:#15151a; --surface2:#1d1d24; --line:#2a2a33; --text:#f1f1f4; --muted:#9b9ba6;
  --accent:#4f95f0; --accent-ink:#0b0b0e; --frame:#000; --footage:#1c2431; --photo:#2a2418;
  color-scheme: dark;
}}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{
    --bg:#f4f5f8; --surface:#ffffff; --surface2:#eef1f6; --line:#dde2ea; --text:#15161c; --muted:#646a78;
    --accent:#0b5fc9; --accent-ink:#ffffff; --frame:#000; --footage:#2c3a52; --photo:#5a4a2a; color-scheme: light;
  }}
}}
:root[data-theme="light"] {{
  --bg:#f4f5f8; --surface:#ffffff; --surface2:#eef1f6; --line:#dde2ea; --text:#15161c; --muted:#646a78;
  --accent:#0b5fc9; --accent-ink:#ffffff; --frame:#000; --footage:#2c3a52; --photo:#5a4a2a; color-scheme: light;
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Noto Sans KR", "Pretendard", system-ui, sans-serif; font-size:15px; line-height:1.6; }}
.wrap {{ max-width: 980px; margin: 0 auto; padding-inline: 16px; padding-block: 24px 80px; }}
h1 {{ font-size: clamp(28px, 6vw, 44px); font-weight: 900; letter-spacing:-0.03em; line-height:1.15; margin: 8px 0 6px; text-wrap: balance; }}
h2 {{ font-size: 20px; font-weight: 700; letter-spacing:-0.01em; margin: 44px 0 12px; padding-top: 18px; border-top: 1px solid var(--line); }}
h3.seghead {{ font-size: 15px; font-weight: 700; margin: 28px 0 10px; display:flex; align-items:center; gap:8px; color:var(--text); }}
p {{ margin: 0 0 10px; max-width: 70ch; }}
ul, ol {{ margin: 0 0 12px; padding-left: 20px; max-width: 75ch; }}
li {{ margin-bottom: 4px; }}
code {{ font-family:"IBM Plex Mono", monospace; font-size: 0.9em; background: var(--surface2); padding: 1px 5px; border-radius: 4px; }}
.eyebrow {{ font-family:"IBM Plex Mono", monospace; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }}
.lead {{ color: var(--muted); max-width: 70ch; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; margin: 14px 0 6px; }}
.chip {{ background: var(--surface); border:1px solid var(--line); border-radius: 10px; padding: 8px 12px; display:flex; flex-direction:column; gap:2px; min-width: 120px; flex: 1 1 140px; }}
.chip b {{ font-size: 12px; color: var(--muted); font-weight: 500; }}
.chip span {{ font-size: 13px; }}
.ruler {{ margin: 18px 0 6px; }}
.bar {{ display:flex; height: 44px; border-radius: 8px; overflow:hidden; border:1px solid var(--line); }}
.seg {{ position:relative; display:flex; align-items:flex-end; padding: 4px 6px; color:#0b0b0e; font-size: 11px; font-weight: 700; overflow:hidden; white-space:nowrap; }}
.seg i {{ font-style: normal; opacity: .85; }}
.ticks {{ position:relative; height: 18px; font-family:"IBM Plex Mono", monospace; font-size: 11px; color: var(--muted); }}
.ticks span {{ position:absolute; transform: translateX(-50%); }}
.struct {{ list-style:none; padding:0; margin: 12px 0 0; max-width: none; }}
.struct li {{ display:grid; grid-template-columns: 12px 92px 130px 1fr; gap: 10px; align-items:baseline; padding: 6px 0; border-bottom: 1px dashed var(--line); font-size: 14px; }}
.struct .pur {{ color: var(--muted); }}
.swatch {{ display:inline-block; width:12px; height:12px; border-radius:3px; }}
.tc {{ font-family:"IBM Plex Mono", monospace; font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }}
.shot {{ display:grid; grid-template-columns: 240px 1fr; gap: 16px; padding: 14px 0; border-bottom: 1px solid var(--line); }}
.frame {{ aspect-ratio: 16/9; width: 100%; max-width:100%; border-radius: 6px; position:relative; display:flex; align-items:center; justify-content:center; overflow:hidden; background: var(--frame); }}
.frame.footage {{ background: linear-gradient(135deg, var(--footage), #0f131c); }}
.frame.photo {{ background: linear-gradient(135deg, var(--photo), #14110a); }}
.frame .words {{ color:#fff; font-weight: 900; letter-spacing: -0.03em; line-height: 1.08; text-align:center; display:flex; flex-direction:column; gap: 2px; padding: 8px 12px; text-shadow: 0 1px 10px rgba(0,0,0,.4); }}
.frame .words.xl {{ font-size: 44px; }} .frame .words.lg {{ font-size: 30px; }} .frame .words.md {{ font-size: 20px; }} .frame .words.sm {{ font-size: 12px; font-weight: 500; }}
.frame .lbl {{ position:absolute; left:8px; top:6px; font-style:normal; font-size: 10px; letter-spacing:.08em; color: rgba(255,255,255,.55); font-family:"IBM Plex Mono", monospace; }}
.meta .row1 {{ display:flex; flex-wrap:wrap; gap: 10px; align-items:baseline; margin-bottom: 4px; }}
.meta .no {{ font-family:"IBM Plex Mono", monospace; font-weight:500; color: var(--accent); }}
.meta .dur {{ font-size: 12px; color: var(--muted); }}
.meta .beat {{ font-size: 12px; color: var(--muted); }}
.meta .vis {{ margin: 0 0 6px; font-size: 14.5px; max-width: none; }}
.meta dl {{ margin:0; display:grid; grid-template-columns: 40px 1fr; gap: 2px 10px; font-size: 13px; }}
.meta dt {{ color: var(--muted); }} .meta dd {{ margin:0; }}
.scroll {{ overflow-x:auto; margin: 10px 0 16px; }}
table.tbl {{ border-collapse: collapse; font-size: 13.5px; min-width: 640px; width:100%; }}
table.tbl th, table.tbl td {{ text-align:left; vertical-align:top; padding: 8px 10px; border-bottom: 1px solid var(--line); }}
table.tbl th {{ color: var(--muted); font-weight: 500; font-size: 12.5px; white-space:nowrap; }}
pre.copy {{ background: var(--frame); color:#fff; border-radius: 10px; padding: 22px 20px; font-family: "Noto Sans KR", sans-serif; font-weight: 900; font-size: 20px; letter-spacing: -0.02em; line-height: 1.5; white-space: pre-wrap; overflow-x:auto; }}
.player {{ background: var(--surface); border:1px solid var(--line); border-radius: 12px; padding: 14px 16px; margin: 12px 0 16px; }}
.player audio {{ width: 100%; }}
.player p {{ margin: 0 0 8px; font-size: 14px; color: var(--muted); }}
section strong {{ font-weight: 700; }}
.toc {{ display:flex; flex-wrap:wrap; gap: 6px 14px; margin: 14px 0 0; font-size: 13px; }}
.toc a {{ color: var(--muted); text-decoration:none; border-bottom: 1px solid var(--line); }}
.toc a:hover, .toc a:focus-visible {{ color: var(--accent); outline: none; border-color: var(--accent); }}
@media (max-width: 640px) {{
  .shot {{ grid-template-columns: 1fr; gap: 10px; }}
  .frame .words.xl {{ font-size: 54px; }} .frame .words.lg {{ font-size: 38px; }} .frame .words.md {{ font-size: 26px; }} .frame .words.sm {{ font-size: 15px; }}
  .struct li {{ grid-template-columns: 12px 80px 1fr; }} .struct .pur {{ grid-column: 2 / -1; }}
  .seg i {{ display:none; }}
}}
@media (prefers-reduced-motion: no-preference) {{ .toc a {{ transition: color .15s; }} }}
</style>
<div class="wrap">
  <div class="eyebrow">Brand film storyboard · v1 · 검토용</div>
  <h1>{html.escape(doc_title.replace(' (버전 1)', ''))}</h1>
  <p class="lead">아이폰 티저 문법으로 만드는 50초. 검은 화면과 큰 글자, 1박 1단어 드롭, 실제 방문자의 문장, 마지막에 로고. 아래 순서대로 보고 11번 확인 요청에 답해 주면 제작에 들어간다.</p>
  <nav class="toc">
    <a href="#s1">콘셉트</a><a href="#s3">구조</a><a href="#s4">샷 리스트</a><a href="#s5">카피</a><a href="#s6">브랜드 한 줄</a><a href="#s7">리뷰</a><a href="#s8">음악</a><a href="#s9">타이포</a><a href="#s10">소스</a><a href="#s11">확인 요청</a>
  </nav>

  <section id="s1"><h2>1. 콘셉트와 본질 가치</h2>{concept_html}
    <div class="chips">{chips}</div>
  </section>

  <section id="s3"><h2>3. 구조 (50초, 25마디)</h2>
    <div class="ruler"><div class="bar">{ruler}</div><div class="ticks">{ticks}</div></div>
    <ul class="struct">{struct_list}</ul>
    {struct_note}
  </section>

  <section id="s4"><h2>4. 샷 리스트 (필름 스트립)</h2>
    <p class="lead">왼쪽 프레임은 화면 글자를 실제 비율로 놓아 본 것이다. 회색빛 프레임은 무료 실사, 갈색빛 프레임은 의뢰인 제공 실제 사진, 검은 프레임은 글자만.</p>
    {strip}
    {shot_note}
  </section>

  {sec_html(5)}
  {sec_html(6)}
  {sec_html(7)}
  <section id="s8"><h2>8. 음악 설계</h2>{audio_html}{md_block(strip_tables(secs[8][1])) if 8 in secs else ''}{''.join(table_html(h, r) for h, r in (parse_tables(secs[8][1]) if 8 in secs else []))}</section>
  {sec_html(9)}
  {sec_html(10)}
  {sec_html(11)}
</div>
"""
    return page


if __name__ == "__main__":
    md_path, out_path = sys.argv[1], sys.argv[2]
    audio = None
    if "--audio" in sys.argv:
        ap = sys.argv[sys.argv.index("--audio") + 1]
        audio = base64.b64encode(open(ap, "rb").read()).decode()
    md = open(md_path, encoding="utf-8").read()
    open(out_path, "w", encoding="utf-8").write(build(md, audio))
    print("wrote", out_path)
