#!/usr/bin/env python3
"""Playable README chess: visitors play White through GitHub issues, a bot plays Black.

Commands:
  python scripts/chess_game.py render                 # (re)draw board + README section
  python scripts/chess_game.py issue --reply FILE     # handle the issue in $ISSUE_TITLE / $ISSUE_USER
  python scripts/chess_game.py new                    # start a fresh game

Issue titles understood:
  chess|move|e2e4     chess|move|e7e8q     chess|new
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

import chess
import chess.engine

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "chess" / "state.json"
BOARD_SVG = ROOT / "assets" / "chess-board.svg"
README = ROOT / "README.md"
START, END = "<!-- CHESS:START -->", "<!-- CHESS:END -->"

REPO = os.environ.get("GITHUB_REPOSITORY", "afrizalyogi/afrizalyogi")

BG, BORDER, PANEL = "#0d1117", "#1e2a36", "#0f161f"
TEXT, MUTED, ACCENT, DANGER = "#e6edf3", "#8b949e", "#3ddc97", "#ff6b6b"
FONT = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"
GLYPH = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
NAMES = {chess.PAWN: "Pawn", chess.KNIGHT: "Knight", chess.BISHOP: "Bishop",
         chess.ROOK: "Rook", chess.QUEEN: "Queen", chess.KING: "King"}
ICON = {chess.PAWN: "♙", chess.KNIGHT: "♘", chess.BISHOP: "♗",
        chess.ROOK: "♖", chess.QUEEN: "♕", chess.KING: "♔"}


# ---------- state ----------
def fresh(prev: dict | None = None) -> dict:
    prev = prev or {}
    return {
        "game": prev.get("game", 0) + 1,
        "fen": chess.STARTING_FEN,
        "moves": [],            # UCI moves of the current game
        "log": [],              # recent turns: {user, move, reply, at}
        "players": prev.get("players", {}),
        "score": prev.get("score", {"visitors": 0, "bot": 0, "draws": 0}),
        "result": None,
    }


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return fresh()


def save(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2) + "\n")


def board_of(s: dict) -> chess.Board:
    b = chess.Board()
    for m in s["moves"]:
        b.push_uci(m)
    return b


# ---------- bot ----------
def bot_move(board: chess.Board) -> chess.Move:
    path = shutil.which("stockfish") or ("/usr/games/stockfish" if Path("/usr/games/stockfish").exists() else None)
    if path:
        try:
            with chess.engine.SimpleEngine.popen_uci(path) as eng:
                eng.configure({"Skill Level": int(os.environ.get("CHESS_BOT_LEVEL", "4"))})
                return eng.play(board, chess.engine.Limit(time=0.3)).move
        except Exception as exc:
            print(f"engine failed, using fallback: {exc}", file=sys.stderr)
    # fallback: mate > best capture > check > random
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
    moves = list(board.legal_moves)
    for m in moves:
        board.push(m)
        mate = board.is_checkmate()
        board.pop()
        if mate:
            return m
    caps = [m for m in moves if board.is_capture(m)]
    if caps:
        def gain(m):
            victim = board.piece_at(m.to_square)
            return values[victim.piece_type] if victim else 1
        return max(caps, key=gain)
    checks = [m for m in moves if board.gives_check(m)]
    return random.choice(checks or moves)


def finish(s: dict, board: chess.Board) -> None:
    if not board.is_game_over():
        return
    res = board.result()
    s["result"] = res
    key = {"1-0": "visitors", "0-1": "bot"}.get(res, "draws")
    s["score"][key] += 1


# ---------- rendering ----------
def outcome_text(board: chess.Board, s: dict) -> str:
    if not s["result"]:
        return "Check! " if board.is_check() else ""
    o = board.outcome()
    if o and o.winner is chess.WHITE:
        return "Checkmate. The visitors win!"
    if o and o.winner is chess.BLACK:
        return "Checkmate. The bot wins."
    return "Draw."


def render_svg(s: dict, board: chess.Board) -> str:
    cell, bx, by = 48, 40, 64
    W, H = 860, by + 8 * cell + 40
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Chess board">',
        f'<style>text{{font-family:{FONT}}} @keyframes blink{{50%{{opacity:.25}}}} .live{{animation:blink 1.6s ease-in-out infinite}}</style>',
        f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="{BG}" stroke="{BORDER}" stroke-width="1.5"/>',
        '<circle cx="24" cy="22" r="5.5" fill="#ff5f57"/><circle cx="42" cy="22" r="5.5" fill="#febc2e"/><circle cx="60" cy="22" r="5.5" fill="#28c840"/>',
        f'<text x="82" y="26.5" fill="{MUTED}" font-size="12">chess.play · game #{s["game"]}</text>',
        f'<text x="{W-30}" y="26.5" fill="{ACCENT}" font-size="12" text-anchor="end"><tspan class="live">●</tspan> open to everyone</text>',
        f'<line x1="1" y1="42" x2="{W-1}" y2="42" stroke="{BORDER}"/>',
    ]
    last = board.peek() if board.move_stack else None
    check_sq = board.king(board.turn) if board.is_check() else None
    for rank in range(8):
        for file in range(8):
            sq = chess.square(file, 7 - rank)
            x, y = bx + file * cell, by + rank * cell
            fill = "#24333f" if (rank + file) % 2 == 0 else "#1b2733"
            out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{fill}"/>')
            if last and sq in (last.from_square, last.to_square):
                out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{ACCENT}" opacity=".22"/>')
            if sq == check_sq:
                out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{DANGER}" opacity=".4"/>')
            p = board.piece_at(sq)
            if p:
                color = TEXT if p.color == chess.WHITE else ACCENT
                out.append(
                    f'<text x="{x + cell / 2}" y="{y + cell / 2 + 12}" fill="{color}" font-size="34" text-anchor="middle">{GLYPH[p.symbol().lower()]}&#xFE0E;</text>'
                )
    for i, f in enumerate("abcdefgh"):
        out.append(f'<text x="{bx + i * cell + cell / 2}" y="{by + 8 * cell + 17}" fill="{MUTED}" font-size="11" text-anchor="middle">{f}</text>')
        out.append(f'<text x="{bx - 13}" y="{by + i * cell + cell / 2 + 4}" fill="{MUTED}" font-size="11" text-anchor="middle">{8 - i}</text>')

    # side panel
    px = 470
    status = outcome_text(board, s)
    if s["result"]:
        head, sub = status, "Start a new game from the README."
    else:
        head = f"{status}Your move: White"
        sub = f"Move {board.fullmove_number} · you play White, the bot plays Black"
    out.append(f'<text x="{px}" y="86" fill="{TEXT}" font-size="20" font-weight="700">{escape(head)}</text>')
    out.append(f'<text x="{px}" y="108" fill="{MUTED}" font-size="12">{escape(sub)}</text>')

    out.append(f'<text x="{px}" y="148" fill="{ACCENT}" font-size="12">&gt; recent_moves</text>')
    log = s["log"][-6:][::-1]
    if not log:
        out.append(f'<text x="{px}" y="174" fill="{MUTED}" font-size="13">No moves yet. Be the first!</text>')
    for i, e in enumerate(log):
        y = 174 + i * 24
        reply = f" → {e['reply']}" if e.get("reply") else ""
        out.append(
            f'<text x="{px}" y="{y}" font-size="13"><tspan fill="{TEXT}">{escape(e["move"])}</tspan>'
            f'<tspan fill="{ACCENT}">{escape(reply)}</tspan><tspan fill="{MUTED}" dx="10">@{escape(e["user"])}</tspan></text>'
        )
    sc = s["score"]
    out.append(f'<text x="{px}" y="{by + 8 * cell - 40}" fill="{ACCENT}" font-size="12">&gt; scoreboard</text>')
    out.append(
        f'<text x="{px}" y="{by + 8 * cell - 14}" font-size="14"><tspan fill="{TEXT}" font-weight="700">{sc["visitors"]}</tspan>'
        f'<tspan fill="{MUTED}"> visitors  </tspan><tspan fill="{TEXT}" font-weight="700">{sc["bot"]}</tspan>'
        f'<tspan fill="{MUTED}"> bot  </tspan><tspan fill="{TEXT}" font-weight="700">{sc["draws"]}</tspan><tspan fill="{MUTED}"> draws</tspan></text>'
    )
    out.append("</svg>")
    return "\n".join(out)


def issue_link(title: str, label: str) -> str:
    body = "Just press Submit new issue. The board updates in about a minute."
    return f"[{label}](https://github.com/{REPO}/issues/new?title={quote(title)}&body={quote(body)})"


def render_section(s: dict, board: chess.Board) -> str:
    lines = [
        START,
        "",
        "### ♟️ Play chess with me",
        "",
        f'<p align="center"><img src="./assets/chess-board.svg" alt="Current chess position" width="100%" /></p>',
        "",
    ]
    if s["result"]:
        lines += [f"**{outcome_text(board, s)}** {issue_link('chess|new', '♻️ Start a new game')}", ""]
    else:
        lines += [
            "**It's your turn (White).** Click a move below, then press **Submit new issue**. "
            "The bot answers in about a minute and this board updates itself.",
            "",
            "| Piece | Move to |",
            "| :-- | :-- |",
        ]
        by_from: dict[int, list[chess.Move]] = {}
        for m in board.legal_moves:
            by_from.setdefault(m.from_square, []).append(m)
        order = sorted(by_from, key=lambda sq: (-board.piece_type_at(sq), chess.square_file(sq), chess.square_rank(sq)))
        for sq in order:
            pt = board.piece_type_at(sq)
            links = []
            for m in sorted(by_from[sq], key=lambda m: (m.to_square, m.promotion or 0)):
                label = chess.square_name(m.to_square)
                if m.promotion:
                    label += "=" + chess.piece_symbol(m.promotion).upper()
                if board.is_castling(m):
                    label = "O-O" if chess.square_file(m.to_square) == 6 else "O-O-O"
                links.append(issue_link(f"chess|move|{m.uci()}", label))
            lines.append(f"| {ICON[pt]} {NAMES[pt]} {chess.square_name(sq)} | {' · '.join(links)} |")
        lines.append("")
    top = sorted(s["players"].items(), key=lambda kv: -kv[1])[:5]
    if top:
        lines += ["**Top players:** " + " · ".join(f"[@{u}](https://github.com/{u}) ({n})" for u, n in top), ""]
    lines += [END]
    return "\n".join(lines)


def render(s: dict) -> None:
    board = board_of(s)
    BOARD_SVG.parent.mkdir(parents=True, exist_ok=True)
    BOARD_SVG.write_text(render_svg(s, board), encoding="utf-8")
    text = README.read_text(encoding="utf-8")
    section = render_section(s, board)
    if START in text and END in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: section, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + section + "\n"
    README.write_text(text, encoding="utf-8")


# ---------- issue handling ----------
def handle(title: str, user: str) -> str:
    user = re.sub(r"[^A-Za-z0-9-]", "", user)[:39] or "someone"
    s = load()
    back = f"[Back to the board](https://github.com/{REPO})"
    parts = title.strip().split("|")
    if len(parts) < 2 or parts[0] != "chess":
        return "🤔 I couldn't read that. Pick a move from the board on the profile."

    if parts[1] == "new":
        if not s["result"] and s["moves"]:
            return f"⏳ Game #{s['game']} is still running. Finish it first! {back}"
        s = fresh(s)
        s["rev"] = s.get("rev", 0) + 1
        save(s)
        render(s)
        return f"♻️ Game #{s['game']} started. You play White. {back}"

    if parts[1] != "move" or len(parts) != 3:
        return "🤔 I couldn't read that. Pick a move from the board on the profile."
    if s["result"]:
        return f"🏁 This game is already over ({s['result']}). Start a new game from the profile. {back}"

    board = board_of(s)
    try:
        move = chess.Move.from_uci(parts[2].strip().lower())
    except ValueError:
        move = None
    if move is None or move not in board.legal_moves:
        return (f"❌ `{escape(parts[2])}` isn't legal in the current position. Someone may have moved "
                f"just before you. Pick a move from the updated board. {back}")

    san = board.san(move)
    board.push(move)
    s["moves"].append(move.uci())
    reply_san = ""
    if not board.is_game_over():
        reply = bot_move(board)
        reply_san = board.san(reply)
        board.push(reply)
        s["moves"].append(reply.uci())
    finish(s, board)
    s["fen"] = board.fen()
    s["log"] = (s["log"] + [{"user": user, "move": san, "reply": reply_san,
                             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}])[-20:]
    s["players"][user] = s["players"].get(user, 0) + 1
    s["rev"] = s.get("rev", 0) + 1
    save(s)
    render(s)

    msg = f"✅ You played **{san}**."
    if reply_san:
        msg += f" The bot replied **{reply_san}**."
    end = outcome_text(board, s)
    if s["result"]:
        msg += f"\n\n🏁 {end}"
    return f"{msg}\n\n{back}"


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "render"
    if cmd == "render":
        s = load()
        save(s)
        render(s)
    elif cmd == "new":
        s = fresh(load())
        save(s)
        render(s)
    elif cmd == "issue":
        reply = handle(os.environ.get("ISSUE_TITLE", ""), os.environ.get("ISSUE_USER", ""))
        if "--reply" in sys.argv:
            Path(sys.argv[sys.argv.index("--reply") + 1]).write_text(reply + "\n", encoding="utf-8")
        print(reply)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
