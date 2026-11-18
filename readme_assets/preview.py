"""Build a self-contained HTML preview of README.md for visual QA.

Usage:
    python readme_assets/preview.py

External images are downloaded once into readme_assets/_cache and inlined via
file:// URIs, so the screenshot works even on a restricted network.
"""

from __future__ import annotations

import html
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "readme_assets"
CACHE = ASSETS / "_cache"
CACHE.mkdir(exist_ok=True)

TEXT = "#e6edf7"
MUTED = "#9198a1"
LINK = "#4493f8"
BORDER = "#3d444d"

BLOCK_TAGS = ("p", "div", "table", "tr", "td", "th", "img", "br", "hr", "details",
              "summary", "center", "picture", "source", "a", "b", "i", "sub", "sup",
              "h1", "h2", "h3", "ul", "li", "code", "pre")


def fetch(url: str, name: str) -> str:
    """Download once, keep the real extension so the browser sniffs the right MIME type."""
    base = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)[:72]
    for cached in CACHE.glob(base + ".*"):
        return cached.as_uri()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        ctype = (resp.headers.get("content-type") or "").lower()
    if "svg" in ctype or body.lstrip()[:5] == b"<svg" or b"<svg" in body[:400]:
        suffix = ".svg"
    elif "png" in ctype:
        suffix = ".png"
    elif "gif" in ctype:
        suffix = ".gif"
    elif "jpeg" in ctype or "jpg" in ctype:
        suffix = ".jpg"
    else:
        suffix = ".img"
    target = CACHE / (base + suffix)
    target.write_bytes(body)
    return target.as_uri()


def static_svg(path: Path) -> Path:
    """Write an animation-free twin of a card SVG so screenshots show the final frame."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'class="(fade|grow)" style="animation-delay:[^"]*"', r'class="\1"', text)
    text = text.replace(
        ".fade { animation: fadeUp .9s cubic-bezier(.2,.7,.2,1) both; }",
        ".fade { opacity: 1; }",
    )
    text = text.replace(
        ".grow { transform-origin: left center; animation: growX 1.1s cubic-bezier(.2,.7,.2,1) both; }",
        ".grow { transform: none; }",
    )
    text = re.sub(r'class="(a[1-4]|cursor|node|float|flow)"', 'class="static"', text)
    text = re.sub(r' style="animation-delay:[^"]*"', "", text)
    text = text.replace(
        "</style>",
        "  .static, .a1, .a2, .a3, .a4, .fade, .grow, .node, .float, .flow, .cursor"
        " { animation: none !important; opacity: 1 !important; }\n    </style>",
    )
    twin = path.with_name("_static_" + path.name)
    twin.write_text(text, encoding="utf-8")
    return twin


def localize_images(block: str) -> str:
    """Rewrite every image source — markdown or raw HTML — to a local file URI."""

    def resolve(src: str, label: str = "img") -> str:
        if src.startswith("http"):
            try:
                return fetch(src, src.rsplit("/", 1)[-1] + "_" + str(abs(hash(src))))
            except Exception:
                return src
        if "://" in src:
            return src
        for base in (ROOT, ASSETS):
            candidate = (base / src).resolve()
            if candidate.exists():
                if candidate.suffix == ".svg":
                    candidate = static_svg(candidate)
                return candidate.as_uri()
        return src

    def md_repl(match: re.Match) -> str:
        return f"![{match.group(1)}]({resolve(match.group(2), match.group(1))})"

    def html_repl(match: re.Match) -> str:
        return f'<img src="{resolve(match.group(1))}"{match.group(2)}>'

    block = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", md_repl, block)
    return re.sub(
        r'<img\s+src="([^"]+)"([^>]*)>',
        html_repl,
        block,
    )


def inline_md(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f'<img src="{m.group(2)}" alt="{html.escape(m.group(1))}"/>',
        text,
    )
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def is_html_start(line: str) -> bool:
    stripped = line.lstrip()
    return any(stripped.startswith(f"<{tag}") for tag in BLOCK_TAGS)


def block_tag(line: str) -> str:
    match = re.match(r"\s*<([a-zA-Z0-9]+)", line)
    return match.group(1).lower() if match else ""


def render(md: str) -> str:
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    in_code = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("<!--"):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue

        if stripped.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                out.append("<pre><code>")
                in_code = True
            i += 1
            continue

        if in_code:
            out.append(html.escape(line) + "\n")
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        # raw HTML block: consume until the matching closing tag
        if is_html_start(stripped) or stripped.startswith("</"):
            start = block_tag(stripped)
            block = [line]
            i += 1
            if start in ("hr", "br", "img"):
                out.append(stripped)
                continue
            close = f"</{start}>"
            if close not in stripped:
                while i < len(lines):
                    block.append(lines[i])
                    if close in lines[i]:
                        i += 1
                        break
                    i += 1
            out.append("\n".join(block))
            continue

        # markdown table
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            header = [c.strip() for c in rows[0].strip("|").split("|")]
            body = [[c.strip() for c in r.strip("|").split("|")] for r in rows[2:]]
            table = ['<table><thead><tr>']
            table += [f"<th>{inline_md(c)}</th>" for c in header]
            table.append("</tr></thead><tbody>")
            for row in body:
                table.append("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in row) + "</tr>")
            table.append("</tbody></table>")
            out.append("".join(table))
            continue

        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + "".join(f"<p>{inline_md(q)}</p>" for q in quote) + "</blockquote>")
            continue

        if stripped == "---":
            out.append("<hr/>")
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline_md(heading.group(2))}</h{level}>")
            i += 1
            continue

        out.append("<p>" + inline_md(stripped) + "</p>")
        i += 1

    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def main() -> None:
    source = (ROOT / "README.md").read_text(encoding="utf-8")
    body = render(localize_images(source))
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>README preview</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0; background: #0d1117; color: {TEXT};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial,
      "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 16px; line-height: 1.5;
  }}
  main {{ max-width: 1012px; margin: 0 auto; padding: 40px 32px 64px; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid {BORDER}; padding-bottom: .3em; margin: 32px 0 16px; }}
  h1 {{ font-size: 2em; }}
  p {{ margin: 0 0 16px; }}
  a {{ color: {LINK}; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  img {{ max-width: 100%; }}
  code {{ background: #262c36; padding: .2em .4em; border-radius: 6px; font-size: 85%;
        font-family: ui-monospace, SFMono-Regular, "Cascadia Code", Consolas, monospace; }}
  pre {{ background: #151b23; padding: 16px; border-radius: 6px; overflow: auto; }}
  blockquote {{ margin: 0 0 16px; padding: 0 1em; color: {MUTED}; border-left: .25em solid #3d444d; }}
  blockquote p {{ margin: 0 0 8px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0 0 16px; }}
  table th, table td {{ padding: 6px 13px; border: 1px solid {BORDER}; text-align: left; vertical-align: top; }}
  table tr:nth-child(2n) {{ background: #151b23; }}
  table th {{ font-weight: 600; }}
  table img {{ vertical-align: middle; }}
  hr {{ height: .25em; padding: 0; margin: 24px 0; background: {BORDER}; border: 0; }}
  sub {{ font-size: .75em; color: {MUTED}; }}
  p[align="center"] {{ margin: 8px 0 16px; }}
  p[align="center"] img {{ margin: 2px 3px; }}
  td[width] p {{ margin: 0; }}
</style>
<script>
  // Freeze the typing SVG mid-word so the screenshot shows real text.
  window.addEventListener("load", () => {{
    document.querySelectorAll('img[alt="typing"]').forEach((img) => {{
      const svg = img.contentDocument && img.contentDocument.documentElement;
      if (svg) {{
        svg.pauseAnimations();
        svg.setCurrentTime(2.2);
      }}
    }});
  }});
</script>
</head>
<body><main>
{body}
</main></body></html>"""
    target = ASSETS / "_preview.html"
    target.write_text(page, encoding="utf-8")
    print(f"wrote {target} ({len(page)} bytes)")


if __name__ == "__main__":
    main()
