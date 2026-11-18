#!/usr/bin/env python3
"""Generate the self-hosted SVG cards used by this profile README.

Cards are committed to the repository, so the profile page never depends on a
third-party stats service (many of them are unreachable from mainland China).
The GitHub Actions workflow in .github/workflows/refreshed-cards.yml runs this
script every day and commits the refreshed SVGs.

Usage
-----
    GH_TOKEN=... python readme_assets/generate_cards.py
    python readme_assets/generate_cards.py --offline   # re-render from cache

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "Evan5321"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "readme_assets" / "cache.json"

# Minimal tech palette: near-black canvas, one cyan accent, one violet accent.
BG_TOP = "#070b14"
BG_BOTTOM = "#0b1220"
INK = "#e6edf7"
MUTED = "#7d8ba3"
DIM = "#4b5769"
CYAN = "#22d3ee"
VIOLET = "#a78bfa"
GREEN = "#4ade80"
LINE = "#1b2536"

LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "Java": "#b07219",
    "Jupyter Notebook": "#DA5B0B",
    "C++": "#f34b7d",
    "C": "#555555",
    "Rust": "#dea584",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "SQL": "#e38c00",
    "Shell": "#89e051",
    "Dockerfile": "#384d54",
    "TeX": "#3D6117",
    "Vue": "#41b883",
    "Go": "#00ADD8",
}


# --------------------------------------------------------------------------- #
# GitHub data
# --------------------------------------------------------------------------- #
def api(path: str) -> dict | list:
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "evan5321-profile-readme")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status == 204:
            return []
        raw = resp.read()
    if not raw.strip():
        return []
    return json.loads(raw)


def collect() -> dict:
    user = api(f"/users/{USER}")
    repos = []
    page = 1
    while True:
        chunk = api(f"/users/{USER}/repos?per_page=100&page={page}&sort=updated")
        if not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    own = [r for r in repos if not r.get("fork")]
    totals = {
        "repos": user.get("public_repos", len(repos)),
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "forks": sum(r.get("forks_count", 0) for r in repos),
        "followers": user.get("followers", 0),
    }

    # Primary language by repository, and bytes for a "real code" estimate.
    lang_repos: dict[str, int] = {}
    lang_bytes: dict[str, int] = {}
    for repo in own:
        name = repo.get("language")
        if name:
            lang_repos[name] = lang_repos.get(name, 0) + 1
        try:
            detailed = api(f"/repos/{USER}/{repo['name']}/languages")
        except urllib.error.URLError:
            detailed = {}
        for lang, count in (detailed or {}).items():
            lang_bytes[lang] = lang_bytes.get(lang, 0) + int(count)

    # Commit totals for user-owned repositories.
    commits = 0
    for repo in own:
        try:
            contributors = api(
                f"/repos/{USER}/{repo['name']}/contributors?per_page=100&anon=1"
            )
        except urllib.error.URLError:
            continue
        for person in contributors or []:
            login = (person.get("login") or "").lower()
            if login == USER.lower() or (
                not login and person.get("type") == "Anonymous"
            ):
                commits += int(person.get("contributions", 0))
    totals["commits"] = commits

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": {
            "login": user.get("login", USER),
            "name": user.get("name") or "",
            "created_at": user.get("created_at", ""),
        },
        "totals": totals,
        "languages": {
            "repos": lang_repos,
            "bytes": lang_bytes,
        },
        "projects": [
            {
                "name": r["name"],
                "description": r.get("description") or "",
                "language": r.get("language") or "",
                "stars": r.get("stargazers_count", 0),
                "updated_at": r.get("pushed_at") or r.get("updated_at") or "",
            }
            for r in own
        ],
    }


# --------------------------------------------------------------------------- #
# SVG helpers
# --------------------------------------------------------------------------- #
def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def defs() -> str:
    return f"""
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BG_TOP}"/>
      <stop offset="1" stop-color="{BG_BOTTOM}"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{CYAN}"/>
      <stop offset="1" stop-color="{VIOLET}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0.22"/>
      <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow2" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="{VIOLET}" stop-opacity="0.18"/>
      <stop offset="1" stop-color="{VIOLET}" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M28 0H0V28" fill="none" stroke="{LINE}" stroke-width="1" stop-opacity="0.5"/>
    </pattern>
    <style>
      .mono {{ font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, Menlo, monospace; }}
      .sans {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }}
      .muted {{ fill: {MUTED}; }}
      .dim {{ fill: {DIM}; }}
      .ink {{ fill: {INK}; }}
      .cyan {{ fill: {CYAN}; }}
      @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: translateY(0); }} }}
      @keyframes growX {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
      @keyframes pulse {{ 0%, 100% {{ opacity: .35; }} 50% {{ opacity: 1; }} }}
      @keyframes drift {{ 0%, 100% {{ transform: translate(0, 0); }} 50% {{ transform: translate(4px, -6px); }} }}
      .fade {{ animation: fadeUp .9s cubic-bezier(.2,.7,.2,1) both; }}
      .grow {{ transform-origin: left center; animation: growX 1.1s cubic-bezier(.2,.7,.2,1) both; }}
      .pulse {{ animation: pulse 3.2s ease-in-out infinite; }}
      .drift {{ animation: drift 7s ease-in-out infinite; }}
      @media (prefers-reduced-motion: reduce) {{
        .fade, .grow, .pulse, .drift {{ animation: none !important; }}
      }}
    </style>
  </defs>"""


def frame(width: int, height: int, label: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}">{defs()}
  <rect width="{width}" height="{height}" rx="18" fill="url(#bg)"/>
  <rect width="{width}" height="{height}" rx="18" fill="url(#grid)" opacity="0.55"/>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="17.5" fill="none" stroke="{LINE}"/>
  <ellipse cx="{width - 60}" cy="28" rx="190" ry="120" fill="url(#glow)"/>
  <ellipse cx="40" cy="{height - 20}" rx="170" ry="110" fill="url(#glow2)"/>
  <rect x="0" y="0" width="{width}" height="3" rx="1.5" fill="url(#accent)" opacity="0.9"/>"""


def stat_column(x: int, y: int, value: str, label: str, color: str, delay: float) -> str:
    return f"""
  <g class="fade" style="animation-delay:{delay}s">
    <rect x="{x}" y="{y - 34}" width="3" height="46" rx="1.5" fill="{color}" opacity="0.85"/>
    <text x="{x + 16}" y="{y}" class="mono ink" font-size="34" font-weight="700" letter-spacing="-1">{esc(value)}</text>
    <text x="{x + 16}" y="{y + 20}" class="mono" font-size="11" letter-spacing="1.6" fill="{MUTED}">{esc(label.upper())}</text>
  </g>"""


# --------------------------------------------------------------------------- #
# Card 1 — codebase overview
# --------------------------------------------------------------------------- #
def compact_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def render_overview(data: dict) -> str:
    width, height = 680, 340
    totals = data["totals"]
    lang_bytes = data["languages"]["bytes"]
    ranked = sorted(lang_bytes.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    top = ranked[0][1] if ranked else 1
    total_bytes = sum(lang_bytes.values())

    parts = [
        frame(width, height, "GitHub codebase overview"),
        f"""
  <g class="fade" style="animation-delay:.05s">
    <circle cx="40" cy="46" r="4" fill="{CYAN}"/>
    <circle cx="40" cy="46" r="9" fill="none" stroke="{CYAN}" stroke-opacity="0.4">
      <animate attributeName="r" values="6;13;6" dur="3s" repeatCount="indefinite"/>
      <animate attributeName="stroke-opacity" values=".55;0;.55" dur="3s" repeatCount="indefinite"/>
    </circle>
    <text x="62" y="51" class="mono" font-size="13" letter-spacing="3" fill="{INK}">CODEBASE</text>
    <text x="164" y="51" class="mono" font-size="13" letter-spacing="3" fill="{CYAN}">/</text>
    <text x="184" y="51" class="mono" font-size="13" letter-spacing="3" fill="{MUTED}">OVERVIEW</text>
  </g>
  <text x="{width - 28}" y="51" text-anchor="end" class="mono" font-size="11" fill="{DIM}">github.com/{esc(USER)}</text>
""",
        stat_column(44, 122, str(totals["repos"]), "repos", CYAN, 0.15),
        stat_column(228, 122, str(totals["stars"]), "stars", VIOLET, 0.25),
        stat_column(412, 122, str(totals["commits"]), "commits", GREEN, 0.35),
        f"""
  <text x="{width - 28}" y="106" text-anchor="end" class="sans" font-size="12" fill="{MUTED}">代码语言分布</text>
  <text x="{width - 28}" y="124" text-anchor="end" class="mono" font-size="10" fill="{DIM}">BY CODE VOLUME</text>
  <line x1="40" y1="158" x2="{width - 28}" y2="158" stroke="{LINE}" stroke-width="1"/>
""",
    ]

    y = 186
    for index, (name, size) in enumerate(ranked):
        color = LANG_COLORS.get(name, CYAN)
        bar_width = max(6, round((size / top) * 300))
        delay = 0.4 + index * 0.1
        parts.append(
            f"""
  <g class="fade" style="animation-delay:{delay}s">
    <circle cx="46" cy="{y - 4}" r="3.5" fill="{color}"/>
    <text x="60" y="{y}" class="mono" font-size="12" fill="{INK}">{esc(name)}</text>
    <rect x="220" y="{y - 11}" width="300" height="7" rx="3.5" fill="{LINE}"/>
    <g class="grow" style="animation-delay:{delay + 0.1}s">
      <rect x="220" y="{y - 11}" width="{bar_width}" height="7" rx="3.5" fill="{color}" opacity="0.9"/>
    </g>
    <text x="540" y="{y}" class="mono" font-size="11" fill="{MUTED}">{compact_bytes(size)}</text>
  </g>"""
        )
        y += 26

    if not ranked:
        parts.append(
            f"""  <text x="44" y="{y}" class="sans" font-size="12" fill="{MUTED}">暂无公开仓库</text>"""
        )

    generated = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    stamp = generated.strftime("%Y-%m-%d %H:%M UTC")
    parts.append(
        f"""
  <line x1="40" y1="{height - 34}" x2="{width - 28}" y2="{height - 34}" stroke="{LINE}" stroke-width="1"/>
  <text x="40" y="{height - 16}" class="mono" font-size="10" fill="{DIM}">auto-refreshed daily · {compact_bytes(total_bytes)} of public code</text>
  <text x="{width - 28}" y="{height - 16}" text-anchor="end" class="mono" font-size="10" fill="{DIM}">{stamp}</text>
</svg>"""
    )
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Card 2 — capability matrix
# --------------------------------------------------------------------------- #
SKILLS = [
    (
        "全栈工程",
        "React / Next.js / FastAPI / Flask",
        "ClipPoems · AI Market Sim",
        9,
        CYAN,
    ),
    (
        "LLM 应用",
        "多厂商接入 · Prompt · Token 优化",
        "ai-market-sim-finance",
        9,
        VIOLET,
    ),
    (
        "数据与 ML",
        "PyTorch CNN · 决策树 · 集成学习",
        "MLLearningDatabase",
        8,
        GREEN,
    ),
    (
        "系统与算法",
        "Java · C/C++ · MySQL / SQL",
        "Notes · QuizSys",
        8,
        "#f59e0b",
    ),
    (
        "工程实践",
        "Docker · Git · pytest · 架构设计",
        "MapCreator · 自动化卡片",
        9,
        "#f472b6",
    ),
]


def render_skills(data: dict) -> str:
    width, height = 680, 340
    parts = [
        frame(width, height, "Engineering capability matrix"),
        f"""
  <g class="fade" style="animation-delay:.05s">
    <circle cx="40" cy="46" r="4" fill="{VIOLET}"/>
    <text x="62" y="51" class="mono" font-size="13" letter-spacing="3" fill="{INK}">SKILL</text>
    <text x="136" y="51" class="mono" font-size="13" letter-spacing="3" fill="{VIOLET}">/</text>
    <text x="156" y="51" class="mono" font-size="13" letter-spacing="3" fill="{MUTED}">MATRIX</text>
  </g>
  <text x="{width - 28}" y="51" text-anchor="end" class="mono" font-size="11" fill="{DIM}">12+ 技术栈 · 5 个方向</text>
""",
    ]

    y = 84
    for index, (title, tools, proof, filled, color) in enumerate(SKILLS):
        delay = 0.15 + index * 0.08
        dots = []
        for slot in range(10):
            on = slot < filled
            dots.append(
                f'<rect x="{width - 280 + slot * 17}" y="{y - 13}" width="11" height="6" rx="3" '
                f'fill="{color if on else LINE}" opacity="{0.95 if on else 0.8}"/>'
            )
        parts.append(
            f"""
  <g class="fade" style="animation-delay:{delay}s">
    <rect x="40" y="{y - 22}" width="3" height="42" rx="1.5" fill="{color}" opacity="0.9"/>
    <text x="56" y="{y - 6}" class="sans" font-size="14.5" font-weight="600" fill="{INK}">{esc(title)}</text>
    <text x="56" y="{y + 8}" class="mono" font-size="10.5" fill="{MUTED}">{esc(tools)}</text>
    <text x="56" y="{y + 21}" class="sans" font-size="10.5" fill="{DIM}">↳ {esc(proof)}</text>
    {''.join(dots)}
  </g>"""
        )
        y += 48
        if index < len(SKILLS) - 1:
            parts.append(
                f'  <line x1="40" y1="{y - 37}" x2="{width - 28}" y2="{y - 37}" stroke="{LINE}" stroke-width="1"/>'
            )

    project_count = len(data.get("projects", []))
    lang_count = len(data["languages"]["bytes"])
    parts.append(
        f"""
  <line x1="40" y1="{height - 30}" x2="{width - 28}" y2="{height - 30}" stroke="{LINE}" stroke-width="1"/>
  <text x="40" y="{height - 13}" class="mono" font-size="10" fill="{DIM}">evidence: public repositories</text>
  <text x="{width - 28}" y="{height - 13}" text-anchor="end" class="mono" font-size="10" fill="{DIM}">{project_count} repos · {lang_count} languages</text>
</svg>"""
    )
    return "".join(parts)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="re-render from readme_assets/cache.json without calling the GitHub API",
    )
    args = parser.parse_args()

    if args.offline:
        if not CACHE.exists():
            print(f"cache not found: {CACHE}", file=sys.stderr)
            return 1
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        print(f"using cache from {data.get('generated_at')}")
    else:
        data = collect()
        CACHE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"fetched GitHub data at {data['generated_at']}")

    (ROOT / "readme_assets" / "card-overview.svg").write_text(
        render_overview(data), encoding="utf-8"
    )
    (ROOT / "readme_assets" / "card-skills.svg").write_text(
        render_skills(data), encoding="utf-8"
    )
    print("wrote card-overview.svg and card-skills.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
