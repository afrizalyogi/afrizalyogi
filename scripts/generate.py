#!/usr/bin/env python3
"""Generate animated SVG cards for a GitHub profile README.

Reads public data from the GitHub GraphQL API and writes:
  assets/profile.svg   - header card with stats + pixel portrait
  assets/stack.svg     - repository-weighted language stack
  assets/year.svg      - contribution numbers for the last year
  assets/about.svg     - intro, shipped metrics and core stack
  assets/chess.svg     - auto-playing chess replay (The Opera Game, 1858)

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
        f'<text x="36" y="94" fill="{ACCENT}" font-size="12">Public repos · weighted by code size</text>',
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
        f'<text x="36" y="100" fill="{MUTED}" font-size="12">Last 365 days · refreshed daily</text>',
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


# ---------- about ----------
ABOUT = {
    "headline": "Built production systems for Indonesian enterprises.",
    "intro": "I run AY Labs: delivering ready-to-use products, crafting custom software, "
             "and building automation systems to scale businesses.",
    "shipped": [
        ("1M+", "Quision", "Requests served", "100+ universities · 4 countries"),
        ("<1s", "Wisecon", "Bank cash-mgmt load", "Lighthouse 40 → 99 · BCA, BRI"),
        ("7-in-1", "AY Labs", "Internal ERP + WA inbox", "CRM · finance · 3 portals"),
    ],
    "stack": [("TypeScript", "#3178c6"), ("PostgreSQL", "#336791")],
}


def about_card() -> str:
    a = ABOUT
    body = [
        f'<text x="36" y="80" fill="{TEXT}" font-size="20" font-weight="700" class="fade">{escape(a["headline"])}</text>'
    ]
    for i, line in enumerate(wrap(a["intro"], 96)):
        line = escape(line).replace("AY Labs", f'<tspan fill="{ACCENT}" font-weight="700">AY Labs</tspan>')
        body.append(
            f'<text x="36" y="{108 + i * 20}" fill="{MUTED}" font-size="13" class="fade" style="animation-delay:.1s">{line}</text>'
        )
    body.append(f'<text x="36" y="172" fill="{ACCENT}" font-size="12">&gt; shipped</text>')
    bw, gap = 252, 16
    for i, (val, tag, label, sub) in enumerate(a["shipped"]):
        x = 36 + i * (bw + gap)
        body.append(
            f'<g class="fade" style="animation-delay:{.25 + i * .15:.2f}s">'
            f'<rect x="{x}" y="184" width="{bw}" height="96" rx="10" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<text x="{x + 18}" y="206" fill="{MUTED}" font-size="11" letter-spacing="1">{escape(tag.upper())}</text>'
            f'<text x="{x + 18}" y="238" fill="{ACCENT}" font-size="28" font-weight="700">{escape(val)}</text>'
            f'<text x="{x + 18}" y="258" fill="{TEXT}" font-size="13">{escape(label)}</text>'
            f'<text x="{x + 18}" y="273" fill="{MUTED}" font-size="11">{escape(sub)}</text></g>'
        )
    body.append(f'<text x="36" y="314" fill="{ACCENT}" font-size="12">&gt; core_stack</text>')
    x = 150
    for i, (name, color) in enumerate(a["stack"]):
        w = 34 + 8.4 * len(name)
        body.append(
            f'<g class="fade" style="animation-delay:{.8 + i * .1:.2f}s">'
            f'<rect x="{x}" y="296" width="{w:.0f}" height="26" rx="13" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<circle cx="{x + 14}" cy="309" r="4.5" fill="{color}"/>'
            f'<text x="{x + 25}" y="313.5" fill="{TEXT}" font-size="12">{escape(name)}</text></g>'
        )
        x += w + 10
    right = (
        f'<text x="{W - 30}" y="26.5" fill="{ACCENT}" font-size="12" text-anchor="end">&gt; whoami'
        f'<tspan class="cursor">_</tspan></text>'
    )
    return frame(344, "about.md", "\n".join(body), right)


# ---------- chess replay ----------
OPERA = [
    "e2e4", "e7e5", "g1f3", "d7d6", "d2d4", "c8g4", "d4e5", "g4f3", "d1f3", "d6e5",
    "f1c4", "g8f6", "f3b3", "d8e7", "b1c3", "c7c6", "c1g5", "b7b5", "c3b5", "c6b5",
    "c4b5", "b8d7", "e1c1+a1d1", "a8d8", "d1d7", "d8d7", "h1d1", "e7e6", "b5d7", "f6d7",
    "b3b8", "d7b8", "d1d8",
]
SAN = [
    "e4", "e5", "Nf3", "d6", "d4", "Bg4", "dxe5", "Bxf3", "Qxf3", "dxe5", "Bc4", "Nf6",
    "Qb3", "Qe7", "Nc3", "c6", "Bg5", "b5", "Nxb5", "cxb5", "Bxb5+", "Nbd7", "O-O-O", "Rd8",
    "Rxd7", "Rxd7", "Rd1", "Qe6", "Bxd7+", "Nxd7", "Qb8+", "Nxb8", "Rd8#",
]
GLYPH = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}


def chess_card() -> str:
    cell, bx, by = 44, 36, 64
    board = {}
    back = "rnbqkbnr"
    for i, f in enumerate("abcdefgh"):
        board[f"{f}1"] = ("w", back[i])
        board[f"{f}2"] = ("w", "p")
        board[f"{f}7"] = ("b", "p")
        board[f"{f}8"] = ("b", back[i])
    pieces = {sq: {"side": s, "kind": k, "path": [(0.0, sq)], "captured": None} for sq, (s, k) in board.items()}
    at = {sq: sq for sq in board}  # square -> piece id

    start, ply, move = 1.5, 1.1, 0.4
    total = start + ply * len(OPERA) + 4.0
    for n, mv in enumerate(OPERA):
        t0 = start + n * ply
        for part in mv.split("+"):
            a, b = part[:2], part[2:]
            pid = at.pop(a)
            if b in at:
                pieces[at[b]]["captured"] = t0 + move
            at[b] = pid
            pieces[pid]["path"].append((t0, a))
            pieces[pid]["path"].append((t0 + move, b))

    def xy(sq: str) -> tuple[float, float]:
        f, r = "abcdefgh".index(sq[0]), int(sq[1])
        return bx + f * cell + cell / 2, by + (8 - r) * cell + cell / 2

    def kt(ts: list[float]) -> str:
        return ";".join(f"{t / total:.4f}" for t in ts)

    out = []
    for r in range(8):
        for f in range(8):
            fill = "#1b2733" if (r + f) % 2 else "#24333f"
            out.append(f'<rect x="{bx + f * cell}" y="{by + r * cell}" width="{cell}" height="{cell}" fill="{fill}"/>')
    for i, f in enumerate("abcdefgh"):
        out.append(f'<text x="{bx + i * cell + cell / 2}" y="{by + 8 * cell + 16}" fill="{MUTED}" font-size="11" text-anchor="middle">{f}</text>')
        out.append(f'<text x="{bx - 12}" y="{by + i * cell + cell / 2 + 4}" fill="{MUTED}" font-size="11" text-anchor="middle">{8 - i}</text>')

    # last-move highlight
    hv, ht = [], []
    for n, mv in enumerate(OPERA):
        x, y = xy(mv.split("+")[0][2:])
        hv.append(f"{x - cell / 2:.0f},{y - cell / 2:.0f}")
        ht.append(start + n * ply + move)
    out.append(
        f'<rect x="0" y="0" width="{cell}" height="{cell}" fill="{ACCENT}" opacity="0">'
        f'<animate attributeName="opacity" values="0;0;.22;.22;0" keyTimes="0;{ht[0] / total:.4f};{(ht[0] + .01) / total:.4f};{(total - .1) / total:.4f};1" dur="{total}s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="translate" calcMode="discrete" values="{hv[0]};{";".join(hv)}" keyTimes="0;{kt(ht)}" dur="{total}s" repeatCount="indefinite"/></rect>'
    )

    for p in pieces.values():
        frames = p["path"]
        x0, y0 = xy(frames[0][1])
        times = [0.0] + [t for t, _ in frames[1:]] + [total - 0.05, total]
        sqs = [frames[0][1]] + [s for _, s in frames[1:]] + [frames[-1][1], frames[0][1]]
        if p["captured"]:
            times = [t for t in times if t <= p["captured"]] + [total - 0.05, total]
            sqs = sqs[: len(times) - 2] + [sqs[len(times) - 3], frames[0][1]]
        vals = []
        for s in sqs:
            x, y = xy(s)
            vals.append(f"{x - x0:.1f},{y - y0:.1f}")
        color = TEXT if p["side"] == "w" else ACCENT
        anim = ""
        if len(frames) > 1 or p["captured"]:
            anim += f'<animateTransform attributeName="transform" type="translate" values="{";".join(vals)}" keyTimes="{kt(times)}" dur="{total}s" repeatCount="indefinite"/>'
        if p["captured"]:
            c = p["captured"]
            anim += (
                f'<animate attributeName="opacity" values="1;1;0;0;1" keyTimes="0;{(c - .15) / total:.4f};{c / total:.4f};{(total - .06) / total:.4f};1" dur="{total}s" repeatCount="indefinite"/>'
            )
        out.append(
            f'<text x="{x0}" y="{y0 + 11}" fill="{color}" font-size="32" text-anchor="middle">{GLYPH[p["kind"]]}&#xFE0E;{anim}</text>'
        )

    # move list
    lx, ly = 440, 92
    out.append(f'<text x="{lx}" y="{ly - 18}" fill="{TEXT}" font-size="18" font-weight="700">The Opera Game</text>')
    out.append(f'<text x="{lx}" y="{ly + 2}" fill="{MUTED}" font-size="12">Paul Morphy vs. Duke Karl &amp; Count Isouard · Paris, 1858</text>')
    rows = (len(SAN) + 1) // 2
    hl_vals, hl_times = [], []
    for i in range(rows):
        col, row = divmod(i, 9)
        x, y = lx + col * 196, ly + 34 + row * 25
        w = SAN[2 * i]
        b = SAN[2 * i + 1] if 2 * i + 1 < len(SAN) else ""
        out.append(
            f'<text x="{x + 8}" y="{y}" font-size="13"><tspan fill="{MUTED}">{i + 1:>2}.</tspan>'
            f'<tspan fill="{TEXT}" dx="8">{escape(w)}</tspan><tspan fill="{ACCENT}" dx="10">{escape(b)}</tspan></text>'
        )
        hl_vals.append(f"{x},{y - 16}")
        hl_times.append(start + 2 * i * ply)
    out.append(
        f'<rect x="0" y="0" width="186" height="22" rx="5" fill="{ACCENT}" opacity=".12">'
        f'<animateTransform attributeName="transform" type="translate" calcMode="discrete" values="{hl_vals[0]};{";".join(hl_vals)}" keyTimes="0;{kt(hl_times)}" dur="{total}s" repeatCount="indefinite"/></rect>'
    )
    mate_t = start + ply * (len(OPERA) - 1) + move
    out.append(
        f'<text x="{lx}" y="{by + 8 * cell - 6}" fill="{ACCENT}" font-size="15" font-weight="700" opacity="0">♚&#xFE0E; Checkmate — 1-0'
        f'<animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;{mate_t / total:.4f};{(mate_t + .3) / total:.4f};{(total - .1) / total:.4f};1" dur="{total}s" repeatCount="indefinite"/></text>'
    )
    right = f'<text x="{W - 30}" y="26.5" fill="{ACCENT}" font-size="12" text-anchor="end">replay ● live</text>'
    return frame(by + 8 * cell + 34, "chess.replay", "\n".join(out), right)


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
    (OUT / "chess.svg").write_text(chess_card(), encoding="utf-8")
    (OUT / "about.svg").write_text(about_card(), encoding="utf-8")
    print(f"wrote cards for @{login} -> {OUT}")


if __name__ == "__main__":
    main()
