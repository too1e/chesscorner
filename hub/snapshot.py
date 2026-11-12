"""Builds a single self-contained HTML copy of the dashboard (data, pieces, styles and scripts all inside the file)
that works offline on any device. The helper-only parts (Stockfish, the opening explorer, the puzzle trainer) are left out.
"""
import base64
import datetime
import json
import os
import time

import chess

HERE = os.path.dirname(os.path.abspath(__file__))


def _b64(path):
    with open(path, "rb") as f:
        return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()


def build(S):
    """`S` is the helper's module namespace (globals() of server.py) so this file can reuse its helpers."""
    stats, openings, book, training, analysis = S["stats"], S["openings"], S["book"], S["training"], S["analysis"]
    bk = book.get()
    raw = S["raw_games"]()
    rows = stats.rows(raw)
    reviews = S["reviewed"]()
    summary = stats.summary(S["bot_games"]())
    summary["puzzles"] = training.stats(analysis.load_json(S["PUZZLES_PATH"], []))

    games = {}
    for g in raw:
        if g.get("time_class") not in ("rapid", "blitz", "bullet"):
            continue
        uuid = g.get("uuid")
        try:
            d = S["game_detail"](uuid)
        except Exception:
            continue
        if not d or not d["moves"]:
            continue
        board, pf, chk = chess.Board(), [chess.Board().board_fen()], []
        for i, u in enumerate(d["moves"]):
            board.push_uci(u)
            pf.append(board.board_fen())
            if board.is_check():
                chk.append(i + 1)
        ex = bk.explore(d["moves"])
        open_ply = max(0, ex["left_at"] - 1) if ex["left_at"] is not None else (ex["last_named"]["ply"] if ex["last_named"] else min(8, len(d["moves"])))
        pre = bk.explore(d["moves"][:open_ply])
        name = (pre["current"] or pre["last_named"] or {}).get("name")
        games[uuid] = {"color": d["color"], "moves": d["moves"], "san": d["san"], "pf": pf, "chk": chk, "url": d["url"], "tc": d["tc"],
                       "result": d["result"], "mate": board.is_checkmate(), "over": board.is_game_over(), "openPly": open_ply, "openName": name,
                       "left_at": ex["left_at"], "last_named": ex["last_named"], "current": ex["current"]}

    progress = analysis.load_json(S["OPENING_PROGRESS_PATH"], {})
    line_meta = {l["id"]: l for l in openings.LINES}
    opening_explore = {}
    for r in rows:
        if r.get("opening") and r.get("color"):
            key = f"{r['opening']}|{r['color']}"
            if key not in opening_explore:
                d = S["opening_detail"](r["opening"], r["color"])
                if d:
                    opening_explore[key] = d

    snapshot = {
        "generated": int(time.time()), "player": stats.USERNAME, "rows": rows, "summary": summary,
        "games_list": stats.game_list(set(reviews), limit=2000), "games": games, "reviews": reviews,
        "moveacc": {f"{tc}|{col}": S["move_accuracy"](tc or None, col or None) for tc in ("", "rapid", "blitz", "bullet") for col in ("", "white", "black")},
        "opening_lines": openings.line_summary(progress),
        "opening_line": {lid: {"id": lid, "name": line_meta[lid]["name"], "color": line_meta[lid]["color"], "plies": plies} for lid, plies in openings.BUILT.items()},
        "opening_report": openings.report(S["opening_games"]()),
        "opening_explore": opening_explore,
        "mates": S["mates_state"](),
        "pieces": {f[:-4]: _b64(os.path.join(HERE, "pieces", f)) for f in os.listdir(os.path.join(HERE, "pieces")) if f.endswith(".svg")},
    }
    blob = json.dumps(snapshot, separators=(",", ":")).replace("</", "<\\/")
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        html = f.read()
    marker = "<script>\n\"use strict\";"
    if marker not in html:
        marker = "<script>"
    i = html.index(marker)
    return html[:i] + "<script>window.__SNAPSHOT__=" + blob + ";</script>\n" + html[i:]


def filename():
    return "chess-corner-" + datetime.date.today().isoformat() + ".html"
