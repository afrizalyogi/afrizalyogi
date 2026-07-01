"""Generate terminal-style stats SVG for GitHub profile README.
AY design system: #1A1A2E navy, #3B82F6 blue, #10B981 green, #0D1117 bg
Only public repo data."""

import json
import os
import urllib.request
from pathlib import Path
from datetime import datetime

TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
USERNAME = "afrizalyogi"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "stats"))
OUTPUT_DIR.mkdir(exist_ok=True)

# AY design system colors
NAVY = "#1A1A2E"
BLUE = "#3B82F6"
GREEN = "#10B981"
AMBER = "#F59E0B"
BG = "#0D1117"
CARD_BG = "#161B22"
TEXT_PRIMARY = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
BORDER = "#30363D"


def graphql(query, variables=None):
    """Execute a GitHub GraphQL query."""
    data = {"query": query}
    if variables:
        data["variables"] = variables
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_user_public_stats():
    """Fetch all public stats for user."""
    query = """
    query($login: String!) {
      user(login: $login) {
        login
        name
        avatarUrl
        repositories(privacy: PUBLIC, first: 1, ownerAffiliations: OWNER) {
          totalCount
        }
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
        }
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) {
          totalCount
        }
        pullRequests(states: MERGED) {
          totalCount
        }
        issues(states: CLOSED) {
          totalCount
        }
        followers {
          totalCount
        }
        starredBy {
          totalCount
        }
      }
    }
    """
    result = graphql(query, {"login": USERNAME})
    user = result["data"]["user"]
    return {
        "public_repos": user["repositories"]["totalCount"],
        "total_commits": user["contributionsCollection"]["totalCommitContributions"],
        "prs_merged": user["pullRequests"]["totalCount"],
        "issues_closed": user["issues"]["totalCount"],
        "repos_contributed": user["repositoriesContributedTo"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "total_stars": user["starredBy"]["totalCount"],
    }


def generate_overview_svg(stats):
    """Generate overview SVG card with terminal aesthetic."""
    w, h = 400, 180
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<defs><style>text{{font-family:"JetBrains Mono","Courier New",monospace;font-size:13px}} .hl{{fill:{BLUE}}} .num{{fill:{GREEN}}} .dim{{fill:{TEXT_SECONDARY}}} .label{{fill:{TEXT_PRIMARY}}}</style></defs>',
        f'<rect width="{w}" height="{h}" fill="{BG}" rx="8"/>',
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" fill="none" stroke="{BORDER}" stroke-width="1" rx="8"/>',
        # Header
        f'<text x="16" y="28" class="hl">$</text>',
        f'<text x="30" y="28" class="label">github-stats --user {USERNAME}</text>',
        # Stats rows
        f'<text x="16" y="56" class="dim">Repos</text>',
        f'<text x="200" y="56" class="num">{stats["public_repos"]}</text>',
        f'<text x="16" y="78" class="dim">Commits</text>',
        f'<text x="200" y="78" class="num">{stats["total_commits"]}</text>',
        f'<text x="16" y="100" class="dim">PRs merged</text>',
        f'<text x="200" y="100" class="num">{stats["prs_merged"]}</text>',
        f'<text x="16" y="122" class="dim">Issues closed</text>',
        f'<text x="200" y="122" class="num">{stats["issues_closed"]}</text>',
        f'<text x="16" y="144" class="dim">Repos contributed</text>',
        f'<text x="200" y="144" class="num">{stats["repos_contributed"]}</text>',
        f'<text x="16" y="166" class="dim">Stars gained</text>',
        f'<text x="200" y="166" class="num">{stats["total_stars"]}</text>',
        f'</svg>',
    ]
    return "\n".join(lines)


def generate_languages_svg():
    """Generate language breakdown SVG using GitHub API."""
    # Fetch repos with languages
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
          nodes {
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name color }
              }
            }
          }
        }
      }
    }
    """
    result = graphql(query, {"login": USERNAME})
    repos = result["data"]["user"]["repositories"]["nodes"]

    # Aggregate language bytes
    lang_data = {}
    for repo in repos:
        if repo["languages"] and repo["languages"]["edges"]:
            for edge in repo["languages"]["edges"]:
                lang = edge["node"]["name"]
                size = edge["size"]
                color = edge["node"]["color"]
                if lang not in lang_data:
                    lang_data[lang] = {"size": 0, "color": color}
                lang_data[lang]["size"] += size

    # Sort by size descending
    sorted_langs = sorted(lang_data.items(), key=lambda x: x[1]["size"], reverse=True)
    total = sum(l["size"] for _, l in sorted_langs)
    top = sorted_langs[:5]

    w, h = 400, 200
    bar_y = 50
    bar_h = 20
    gap = 28

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<defs><style>text{{font-family:"JetBrains Mono","Courier New",monospace;font-size:12px}} .num{{fill:{TEXT_PRIMARY};font-size:13px}} .pct{{fill:{TEXT_SECONDARY}}} .lbl{{fill:{TEXT_PRIMARY}}}</style></defs>',
        f'<rect width="{w}" height="{h}" fill="{BG}" rx="8"/>',
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" fill="none" stroke="{BORDER}" stroke-width="1" rx="8"/>',
        f'<text x="16" y="24" fill="{BLUE}" font-family="JetBrains Mono,monospace" font-size="13">$</text>',
        f'<text x="30" y="24" fill="{TEXT_PRIMARY}" font-family="JetBrains Mono,monospace" font-size="13">github-langs --user {USERNAME}</text>',
    ]

    for i, (name, data) in enumerate(top):
        pct = round(data["size"] / total * 100, 1) if total > 0 else 0
        y = bar_y + i * gap
        bar_w = int(pct * 3.2)  # scale: 320px max for 100%
        lines.append(f'<rect x="16" y="{y}" width="12" height="12" rx="2" fill="{data["color"]}"/>')
        lines.append(f'<text x="34" y="{y+10}" class="lbl">{name}</text>')
        lines.append(f'<text x="{w-80}" y="{y+10}" class="num">{pct}%</text>')
        lines.append(f'<rect x="16" y="{y+18}" width="{bar_w}" height="4" rx="2" fill="{data["color"]}" opacity="0.8"/>')
        lines.append(f'<rect x="16" y="{y+18}" width="320" height="4" rx="2" fill="{BORDER}" opacity="0.3"/>')

    lines.append(f'</svg>')
    return "\n".join(lines)


def main():
    if not TOKEN:
        print("No GitHub token found. Skipping stats generation.")
        return

    print(f"Fetching stats for {USERNAME}...")
    stats = fetch_user_public_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")

    overview_svg = generate_overview_svg(stats)
    lang_svg = generate_languages_svg()

    with open(OUTPUT_DIR / "overview.svg", "w") as f:
        f.write(overview_svg)
    with open(OUTPUT_DIR / "languages.svg", "w") as f:
        f.write(lang_svg)

    print(f"SVGs saved to {OUTPUT_DIR}/")
    print(f"  overview.svg  ({len(overview_svg)} bytes)")
    print(f"  languages.svg ({len(lang_svg)} bytes)")


if __name__ == "__main__":
    main()
