"""A small opening repertoire to drill, plus a report on where your real games leave it.

Each line is a list of (SAN move, note) from move 1. `color` is the side you play; the other side's moves are
played for you in a drill. Notes explain the idea of a move in a sentence. Everything is checked for legality
when the module loads, so a typo can't ship a broken line.
"""
import collections
import datetime
import re

import chess

import training

W, B = "white", "black"

LINES = [
    {"id": "b-ruy", "color": B, "name": "Ruy Lopez (vs 1.e4 e5 2.Nf3 Nc6 3.Bb5)", "moves": [
        ("e4", ""), ("e5", "Take a share of the centre and open lines for your bishop and queen."),
        ("Nf3", "White attacks e5."), ("Nc6", "Defends e5 and develops a piece toward the centre."),
        ("Bb5", "The Ruy Lopez: the bishop pressures the knight that defends e5."),
        ("a6", "Asks the bishop what it wants to do, and prepares ...b5."),
        ("Ba4", ""), ("Nf6", "Develops with an attack on White's e4 pawn."),
        ("O-O", ""), ("Be7", "Develops and gets ready to castle."),
        ("Re1", "Defends e4."), ("b5", "Kicks the bishop and gains space on the queenside."),
        ("Bb3", ""), ("d6", "Solidly protects e5 and frees your bishop."),
        ("c3", ""), ("O-O", "King safe - you're fully developed with a sound position.")]},
    {"id": "b-italian", "color": B, "name": "Italian Game (vs 3.Bc4)", "moves": [
        ("e4", ""), ("e5", "Fight for the centre."), ("Nf3", ""), ("Nc6", "Defends e5 and develops."),
        ("Bc4", "White eyes f7, your weakest square."), ("Bc5", "Mirror the setup: develop and eye f2."),
        ("c3", "Preparing d4."), ("Nf6", "Develops and attacks e4, so White can't take over the centre easily."),
        ("d3", ""), ("d6", "Supports e5 and opens the way for your c8 bishop."),
        ("O-O", ""), ("O-O", "Castle early: king safe, rook ready.")]},
    {"id": "b-alekhine", "color": B, "name": "Alekhine's Defence (vs 1.e4 Nf6)", "moves": [
        ("e4", ""), ("Nf6", "Invites White's pawn forward so you can attack it later."),
        ("e5", ""), ("Nd5", "Knight steps away with tempo; White's e5 pawn may become a target."),
        ("d4", ""), ("d6", "Challenges the advanced e5 pawn."), ("Nf3", ""),
        ("Bg4", "Develops with pressure on the knight that supports d4."),
        ("Be2", ""), ("e6", "Opens your f8 bishop; keep the position solid."),
        ("O-O", ""), ("Be7", "Develop and get ready to castle."),
        ("c4", "White kicks your knight."), ("Nb6", "Retreat; it eyes c4 and keeps pieces coordinated."),
        ("Nc3", ""), ("O-O", "Castle - fully developed.")]},
    {"id": "b-qgd", "color": B, "name": "Queen's Gambit Declined (vs 1.d4 d5 2.c4)", "moves": [
        ("d4", ""), ("d5", "Claim the centre directly."), ("c4", "The Queen's Gambit: White offers a pawn."),
        ("e6", "Decline it: protect d5 and open your bishop."), ("Nc3", ""),
        ("Nf6", "Develop and add pressure on d5."), ("Bg5", "Pins your knight against the queen."),
        ("Be7", "Unpins by getting ready to castle."), ("e3", ""),
        ("O-O", "King to safety."), ("Nf3", ""), ("Nbd7", "Develops the last minor piece and guards your centre.")]},
    {"id": "b-vs-london", "color": B, "name": "Against the London (vs 1.d4 d5 2.Bf4)", "moves": [
        ("d4", ""), ("d5", ""), ("Bf4", "White develops the bishop outside the pawn chain."),
        ("Nf6", "Develop toward the centre."), ("e3", ""), ("e6", "Solid - opens your light bishop's neighbour."),
        ("Nf3", ""), ("Bd6", "Challenges White's bishop; trade it if you can."),
        ("Bg3", ""), ("O-O", "Castle, then plan ...c5 to hit the centre."),
        ("Nbd2", ""), ("c5", "Strike at White's centre now that you're safe.")]},
    {"id": "w-italian", "color": W, "name": "Italian Game (as White)", "moves": [
        ("e4", "Take the centre and open lines for your queen and bishop."), ("e5", ""),
        ("Nf3", "Develop with an attack on e5."), ("Nc6", ""),
        ("Bc4", "Aim the bishop at f7."), ("Bc5", ""),
        ("c3", "Prepare d4 to build a strong centre."), ("Nf6", ""),
        ("d3", "Solid: protects e4 and opens the c1 bishop."), ("d6", ""),
        ("O-O", "Castle early."), ("O-O", ""), ("Re1", "Rook to the open e-file, supporting e4.")]},
    {"id": "w-london", "color": W, "name": "London System (as White)", "moves": [
        ("d4", "Claim the centre."), ("d5", ""), ("Bf4", "Develop the bishop BEFORE playing e3 - that's the London idea."),
        ("Nf6", ""), ("e3", "Solid support for d4 and the bishop."), ("e6", ""),
        ("Nf3", "Develop a knight."), ("Bd6", ""), ("Bg3", "Keep your bishop; trade only if it helps you."),
        ("O-O", ""), ("Nbd2", "Develop the second knight, ready for e4."), ("c5", ""),
        ("c3", "Strengthen d4."), ("Nc6", ""), ("Bd3", "Aim at the kingside.")]},
    {"id": "w-alapin", "color": W, "name": "Sicilian: Alapin (vs 1...c5)", "moves": [
        ("e4", ""), ("c5", "The Sicilian: Black fights for d4."), ("c3", "The Alapin: prepare d4 to get a big centre without theory."),
        ("Nf6", ""), ("e5", "Gain space and kick the knight."), ("Nd5", ""),
        ("d4", "Take the centre."), ("cxd4", ""), ("Nf3", "Develop and aim at d4."), ("Nc6", ""),
        ("cxd4", "Recapture and keep a strong centre."), ("d6", ""), ("Bc4", "Hit the knight on d5.")]},
]

_ID = {l["id"]: l for l in LINES}


def _strip(san):
    return san.rstrip("+#!?")


def build(line):
    """Replay a line, returning one dict per ply (SAN, UCI, FENs, who, note)."""
    board, out = chess.Board(), []
    for i, (san, note) in enumerate(line["moves"]):
        move = board.parse_san(san)  # raises if the line isn't legal
        who = "white" if i % 2 == 0 else "black"
        before = board.fen()
        shown = board.san(move)
        board.push(move)
        out.append({"ply": i, "san": shown, "uci": move.uci(), "fen_before": before, "fen_after": board.fen(),
                    "who": who, "mine": who == line["color"], "note": note})
    return out


BUILT = {l["id"]: build(l) for l in LINES}  # validates every line at import time


def line_summary(progress):
    out = []
    for l in LINES:
        p = progress.get(l["id"], {"box": 0, "due": None, "tries": 0, "solved": 0})
        out.append({"id": l["id"], "name": l["name"], "color": l["color"], "plies": len(l["moves"]),
                    "my_moves": sum(1 for x in BUILT[l["id"]] if x["mine"]), "box": p["box"], "tries": p["tries"],
                    "solved": p["solved"], "due": p["due"] is None or p["due"] <= training.today()})
    return out


def record(progress, line_id, correct):
    p = progress.setdefault(line_id, {"box": 0, "due": training.today(), "tries": 0, "solved": 0})
    training.record(p, correct)
    return p


def report(games):
    """Where real games stop following the repertoire. `games` = [{'color', 'san': [..]}]."""
    left = collections.Counter()      # (line, ply, my move, book move) -> count
    opp_left = collections.Counter()  # (line, ply, their move)
    followed, completed, considered = 0, 0, 0
    for g in games:
        san = [_strip(s) for s in g["san"]]
        best, best_len = None, -1
        for l in LINES:
            if l["color"] != g["color"]:
                continue
            ref = [_strip(m[0]) for m in l["moves"]]
            n = 0
            while n < len(ref) and n < len(san) and ref[n] == san[n]:
                n += 1
            if n > best_len:
                best, best_len = l, n
        if not best or best_len < 2:
            continue
        considered += 1
        ref = [_strip(m[0]) for m in best["moves"]]
        if best_len >= len(ref):
            completed += 1
            continue
        if best_len >= len(san):
            continue  # game ended inside the book
        mover = "white" if best_len % 2 == 0 else "black"
        if mover == g["color"]:
            left[(best["id"], best_len, san[best_len], ref[best_len])] += 1
        else:
            opp_left[(best["id"], best_len, san[best_len])] += 1
    rows = []
    for (lid, k, played, book), n in left.most_common(8):
        prefix = BUILT[lid][k]["fen_before"]
        moves = [x["san"] for x in BUILT[lid][:k]]
        rows.append({"line_id": lid, "line": _ID[lid]["name"], "after": _numbered(moves), "ply": k, "played": played, "book": book,
                     "count": n, "fen": prefix, "color": _ID[lid]["color"]})
    return {"games": considered, "completed": completed, "you_left": sum(left.values()),
            "opp_left": sum(opp_left.values()), "rows": rows}


def _numbered(moves):
    out = []
    for i, m in enumerate(moves):
        out.append(f"{i // 2 + 1}.{m}" if i % 2 == 0 else m)
    return " ".join(out)


if __name__ == "__main__":
    for l in LINES:
        print(l["id"], len(l["moves"]), "plies OK:", _numbered([x["san"] for x in BUILT[l["id"]]]))
