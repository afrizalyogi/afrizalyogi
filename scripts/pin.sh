#!/usr/bin/env bash
# Point README images at the current commit SHA so every update gets a brand-new URL
# (GitHub's raw/camo caches key on the URL; a SHA URL can never be stale).
set -euo pipefail
sha=$(git rev-parse HEAD)
base="https://raw.githubusercontent.com/${GITHUB_REPOSITORY:-afrizalyogi/afrizalyogi}/$sha"
sed -i -E "s#src=\"(\./|https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/)(assets/[^\"?]+)(\?v=[0-9]+)?\"#src=\"$base/\2\"#g" README.md
git add README.md
git diff --cached --quiet || git commit -q -m "chore: pin README images to $sha"
