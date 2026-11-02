#!/usr/bin/env python3
"""Generate animated SVG cards for a GitHub profile README.

Reads public data from the GitHub GraphQL API and writes:
  assets/profile.svg   - header card with stats + pixel portrait
  assets/stack.svg     - repository-weighted language stack
  assets/year.svg      - contribution numbers for the last year

Usage:
  GH_TOKEN=... python scripts/generate.py <username>
  python scripts/generate.py <username> --sample   # offline preview data
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.request
from datetime import date, timedelta
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets"

# ---------- theme ----------
BG = "#0d1117"
PANEL = "#0f161f"
BORDER = "#1e2a36"
GRID = "#16202b"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#3ddc97"
ACCENT_DIM = "#1f6f4f"
FONT = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
W = 860

# ---------- data ----------
QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    login name bio avatarUrl(size:160)
    followers { totalCount }
    repositories(ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false, first:100, after:$cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def gql(token: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def fetch(login: str, token: str) -> dict:
    user, cursor, repos = None, None, []
    while True:
        u = gql(token, {"login": login, "cursor": cursor})
        user = user or u
        repos += u["repositories"]["nodes"]
        page = u["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]

    langs: dict[str, list] = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or MUTED])
            langs[n][0] += e["size"]

    days = [
        (d["date"], d["contributionCount"])
        for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    ]
    avatar = None
    try:
        with urllib.request.urlopen(user["avatarUrl"], timeout=30) as r:
            avatar = r.read()
    except Exception as exc:  # portrait is optional
        print(f"avatar download failed: {exc}", file=sys.stderr)

    return {
        "login": user["login"],
        "name": user["name"] or user["login"],
        "bio": user["bio"] or "",
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "languages": langs,
        "days": days,
        "avatar": avatar,
    }


def sample(login: str) -> dict:
    import random

    random.seed(7)
    start = date.today() - timedelta(days=364)
    days = []
    for i in range(365):
        c = random.choice([0, 0, 0, 1, 2, 3, 5, 8]) if random.random() > 0.35 else 0
        days.append(((start + timedelta(days=i)).isoformat(), c))
    return {
        "login": login,
        "name": "Afrizal Yogi P.",
        "bio": "Building Full-Stack Systems and Workflow Automation",
        "followers": 31,
        "repos": 28,
        "stars": 12,
        "contributions": sum(c for _, c in days),
        "languages": {
            "TypeScript": [520000, "#3178c6"],
            "PHP": [310000, "#4F5D95"],
            "Python": [140000, "#3572A5"],
            "CSS": [90000, "#663399"],
            "HTML": [60000, "#e34c26"],
        },
        "days": days,
        "avatar": None,
    }


# ---------- helpers ----------
def smil_fade(body: str) -> str:
    """Turn class="fade" markers into SMIL fade-ins (they run even where CSS animations stall)."""

    def sub(m: re.Match) -> str:
        delay = float(m.group(3) or 0)
        dur = delay + 0.6
        return (
            f'{m.group(1)}><animate attributeName="opacity" values="0;0;1" '
            f'keyTimes="0;{delay / dur:.3f};1" dur="{dur:.2f}s" fill="freeze"/>'
        )

    return re.sub(r'(<(g|text)[^>]*?) class="fade"(?: style="animation-delay:([\d.]+)s")?>', sub, body)


def frame(h: int, title: str, body: str, right: str = "") -> str:
    body = smil_fade(body)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img" aria-label="{escape(title)}">
<style>
  text {{ font-family: {FONT}; }}
  @keyframes blink {{ 50% {{ opacity: 0; }} }}
  .cursor {{ animation: blink 1s steps(1) infinite; }}
</style>
<rect x="1" y="1" width="{W-2}" height="{h-2}" rx="14" fill="{BG}" stroke="{BORDER}" stroke-width="1.5"/>
<circle cx="24" cy="22" r="5.5" fill="#ff5f57"/><circle cx="42" cy="22" r="5.5" fill="#febc2e"/><circle cx="60" cy="22" r="5.5" fill="#28c840"/>
<text x="82" y="26.5" fill="{MUTED}" font-size="12">{escape(title)}</text>
{right}
<line x1="1" y1="42" x2="{W-1}" y2="42" stroke="{BORDER}"/>
{body}
</svg>
"""


def wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines[:2]


def top_languages(langs: dict, n: int = 5) -> list[tuple[str, float, str]]:
    total = sum(v[0] for v in langs.values()) or 1
    items = sorted(langs.items(), key=lambda kv: -kv[1][0])[:n]
    return [(k, v[0] * 100 / total, v[1]) for k, v in items]


# ---------- cards ----------
def portrait(avatar: bytes | None, x0: int, y0: int, size: int) -> str:
    n = 34
    cell = size / n
    out = []
    if avatar:
        from PIL import Image, ImageEnhance

        img = Image.open(io.BytesIO(avatar)).convert("RGB").resize((n, n), Image.LANCZOS)
        img = ImageEnhance.Color(img).enhance(1.35)
        px = img.load()
        for j in range(n):
            for i in range(n):
                r, g, b = px[i, j]
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                rad = cell * (0.18 + 0.32 * lum)
                out.append(
                    f'<circle cx="{x0 + (i + .5) * cell:.1f}" cy="{y0 + (j + .5) * cell:.1f}" r="{rad:.2f}" fill="#{r:02x}{g:02x}{b:02x}"/>'
                )
    else:  # fallback: abstract dot field
        import math

        for j in range(n):
            for i in range(n):
                d = math.hypot(i - n / 2, j - n / 2) / (n / 2)
                if d > 1:
                    continue
                rad = cell * (0.12 + 0.3 * (1 - d))
                out.append(
                    f'<circle cx="{x0 + (i + .5) * cell:.1f}" cy="{y0 + (j + .5) * cell:.1f}" r="{rad:.2f}" fill="{ACCENT}" opacity="{0.25 + 0.75 * (1 - d):.2f}"/>'
                )
    scan = (
        f'<rect x="{x0}" y="{y0}" width="{size}" height="3" fill="{ACCENT}" opacity=".55">'
        f'<animate attributeName="y" values="{y0};{y0 + size - 3};{y0}" dur="6s" repeatCount="indefinite"/></rect>'
    )
    return f'<g>{"".join(out)}</g>{scan}'


def profile_card(d: dict) -> str:
    h = 344
    body = [
        f'<text x="36" y="84" fill="{ACCENT}" font-size="15" class="fade">@{escape(d["login"])}</text>',
        f'<text x="36" y="126" fill="{TEXT}" font-size="36" font-weight="700" class="fade" style="animation-delay:.1s">{escape(d["name"])}</text>',
    ]
    for i, line in enumerate(wrap(d["bio"], 44)):
        body.append(
            f'<text x="36" y="{156 + i * 20}" fill="{MUTED}" font-size="14" class="fade" style="animation-delay:.2s">{escape(line)}</text>'
        )
    stats = [
        ("▣", d["repos"], "Repositories"),
        ("☆", d["stars"], "Stars earned"),
        ("◆", d["contributions"], "Contributions this year"),
        ("◉", d["followers"], "Followers"),
    ]
    for i, (icon, val, label) in enumerate(stats):
        y = 206 + i * 24
        body.append(
            f'<g class="fade" style="animation-delay:{.3 + i * .12:.2f}s">'
            f'<text x="36" y="{y}" fill="{ACCENT}" font-size="14">{icon}</text>'
            f'<text x="60" y="{y}" fill="{TEXT}" font-size="14" font-weight="700">{val:,}</text>'
            f'<text x="{68 + 9 * len(f"{val:,}")}" y="{y}" fill="{MUTED}" font-size="14">{label}</text></g>'
        )
    x = 36
    for i, (name, _, color) in enumerate(top_languages(d["languages"], 4)):
        w = 34 + 8.4 * len(name)
        body.append(
            f'<g class="fade" style="animation-delay:{.8 + i * .1:.2f}s">'
            f'<rect x="{x}" y="296" width="{w:.0f}" height="24" rx="12" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<circle cx="{x + 14}" cy="308" r="4.5" fill="{color}"/>'
            f'<text x="{x + 25}" y="312.5" fill="{TEXT}" font-size="12">{escape(name)}</text></g>'
        )
        x += w + 10
    body.append(f'<rect x="546" y="58" width="284" height="256" rx="10" fill="{PANEL}" stroke="{BORDER}"/>')
    body.append(portrait(d["avatar"], 568, 66, 240))
    return frame(h, "README.md", "\n".join(body))


def stack_card(d: dict) -> str:
    langs = top_languages(d["languages"], 5)
    h = 86 + len(langs) * 34 + 30
    right = (
        f'<text x="{W - 30}" y="26.5" fill="{ACCENT}" font-size="12" text-anchor="end">&gt; stack.scan'
        f'<tspan class="cursor">_</tspan></text>'
    )
    body = [
        f'<text x="36" y="74" fill="{TEXT}" font-size="18" font-weight="700">Language Stack</text>',
        f'<text x="36" y="94" fill="{ACCENT}" font-size="12">Repository-weighted technologies</text>',
    ]
    for i, (name, pct, color) in enumerate(langs):
        y = 128 + i * 34
        bar = 470 * pct / 100
        body.append(
            f'<circle cx="42" cy="{y - 4}" r="5" fill="{color}"/>'
            f'<text x="58" y="{y}" fill="{TEXT}" font-size="14">{escape(name)}</text>'
            f'<text x="260" y="{y}" fill="{color}" font-size="14" text-anchor="end" font-weight="700">{pct:.0f}%</text>'
            f'<rect x="300" y="{y - 11}" width="470" height="10" rx="5" fill="{GRID}"/>'
            f'<rect x="300" y="{y - 11}" width="0" height="10" rx="5" fill="{color}">'
            f'<animate attributeName="width" from="0" to="{max(bar, 6):.1f}" begin="{i * .15:.2f}s" dur="1s" fill="freeze" calcMode="spline" keySplines=".2 .8 .2 1" keyTimes="0;1"/></rect>'
        )
    return frame(h, "stack.md", "\n".join(body), right)


def year_card(d: dict) -> str:
    days = d["days"]
    counts = [c for _, c in days]
    active = sum(1 for c in counts if c)
    busiest = max(counts or [0])
    longest = cur = 0
    for c in counts:
        cur = cur + 1 if c else 0
        longest = max(longest, cur)
    h = 180
    body = [
        f'<text x="36" y="80" fill="{TEXT}" font-size="18" font-weight="700">The city I built this year</text>',
        f'<text x="36" y="100" fill="{MUTED}" font-size="12">Last 365 days · refreshed weekly</text>',
    ]
    stats = [
        (d["contributions"], "contributions"),
        (active, "active days"),
        (busiest, "busiest day"),
        (longest, "longest streak"),
    ]
    for i, (val, label) in enumerate(stats):
        x = 36 + i * 205
        body.append(
            f'<g class="fade" style="animation-delay:{i * .12:.2f}s">'
            f'<text x="{x}" y="136" fill="{ACCENT}" font-size="26" font-weight="700">{val:,}</text>'
            f'<text x="{x}" y="152" fill="{MUTED}" font-size="12">{label}</text></g>'
        )
    # mini sparkline of weekly totals on the right of the title
    weeks = [sum(counts[i:i + 7]) for i in range(0, len(counts), 7)]
    peak = max(weeks or [1]) or 1
    for i, wk in enumerate(weeks[-26:]):
        bh = 4 + 34 * wk / peak
        body.append(
            f'<rect x="{560 + i * 10}" y="{104 - bh:.1f}" width="7" height="{bh:.1f}" rx="1.5" fill="{ACCENT}" opacity="{0.35 + 0.65 * wk / peak:.2f}"/>'
        )
    return frame(h, "contributions.log", "\n".join(body))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    login = sys.argv[1]
    if "--sample" in sys.argv:
        data = sample(login)
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("Set GH_TOKEN (or GITHUB_TOKEN) to read the GitHub API.")
        data = fetch(login, token)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "profile.svg").write_text(profile_card(data), encoding="utf-8")
    (OUT / "stack.svg").write_text(stack_card(data), encoding="utf-8")
    (OUT / "year.svg").write_text(year_card(data), encoding="utf-8")
    print(f"wrote cards for @{login} -> {OUT}")


if __name__ == "__main__":
    main()
