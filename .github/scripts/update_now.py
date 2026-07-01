"""Update the 'Now' section in README with latest activity."""

import json
import os
import re
import urllib.request

TOKEN = os.environ.get("GITHUB_TOKEN", "")
USERNAME = "afrizalyogi"
README_PATH = os.environ.get("README_PATH", "README.md")

def graphql(query, variables=None):
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


def get_latest_activity():
    """Get latest repo activity for the user."""
    query = """
    query($login: String!) {
      user(login: $login) {
        repositories(first: 5, privacy: PUBLIC, ownerAffiliations: OWNER,
                     orderBy: {field: PUSHED_AT, direction: DESC}) {
          nodes {
            name
            description
            pushedAt
            stargazerCount
            primaryLanguage { name color }
          }
        }
      }
    }
    """
    result = graphql(query, {"login": USERNAME})
    repos = result["data"]["user"]["repositories"]["nodes"]
    return repos


def generate_now_text(repos):
    """Generate the 'Now' section text."""
    lines = []
    for repo in repos:
        if repo["description"] and len(repo["description"]) > 60:
            desc = repo["description"][:57] + "..."
        else:
            desc = repo["description"] or ""
        stars = f"★{repo['stargazerCount']}" if repo["stargazerCount"] > 0 else ""
        lang = repo["primaryLanguage"]["name"] if repo["primaryLanguage"] else ""
        entry = f"[{repo['name']}](https://github.com/{USERNAME}/{repo['name']})"
        if desc:
            entry += f" — {desc}"
        if lang or stars:
            extras = " · ".join(filter(None, [lang, stars]))
            entry += f" · `{extras}`"
        lines.append(entry)
    if not lines:
        lines.append("AY Labs · AI workflow automation · [labs.aycorp.id](https://labs.aycorp.id)")
    return "\n".join(lines)


def update_readme(new_content):
    """Replace content between <!-- now starts --> and <!-- now ends -->."""
    with open(README_PATH, "r") as f:
        readme = f.read()

    pattern = r"(<!-- now starts -->\n).*(\n<!-- now ends -->)"
    replacement = r"\1" + new_content + r"\2"

    if not re.search(pattern, readme, re.DOTALL):
        print("ERROR: Could not find <!-- now starts/fends --> markers in README")
        return False

    updated = re.sub(pattern, replacement, readme, flags=re.DOTALL)
    with open(README_PATH, "w") as f:
        f.write(updated)
    print(f"README updated — 'Now' section refreshed.")
    return True


def main():
    if not TOKEN:
        print("No GitHub token found. Skipping Now update.")
        return

    print(f"Fetching latest activity for {USERNAME}...")
    repos = get_latest_activity()
    now_text = generate_now_text(repos)
    print(f"Generated:\n{now_text}")
    update_readme(now_text)


if __name__ == "__main__":
    main()
