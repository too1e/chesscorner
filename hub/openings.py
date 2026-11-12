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
    # as White against the replies you meet most after 1.e4 / 1.d4
    {"id": "w-scandi", "color": W, "name": "Scandinavian (vs 1...d5)", "moves": [
        ("e4", ""), ("d5", "The Scandinavian: Black hits e4 straight away."), ("exd5", "Take it - Black has to spend a move getting the pawn back."),
        ("Qxd5", ""), ("Nc3", "Develop with tempo: the queen is attacked."), ("Qa5", ""),
        ("d4", "Grab the centre while the queen is offside."), ("Nf6", ""), ("Nf3", "Develop toward the centre."), ("c6", ""),
        ("Bc4", "Active bishop, aiming at f7."), ("Bf5", ""), ("Bd2", "Develop and quietly break the pin on c3."), ("e6", ""),
        ("O-O", "Castle - you're ahead in development.")]},
    {"id": "w-caro", "color": W, "name": "Caro-Kann: Advance (vs 1...c6)", "moves": [
        ("e4", ""), ("c6", "The Caro-Kann: Black prepares ...d5."), ("d4", "Take the full centre."), ("d5", ""),
        ("e5", "The Advance: gain space and cramp Black's kingside."), ("Bf5", ""), ("Nf3", "Develop and support e5."), ("e6", ""),
        ("Be2", "Simple development, ready to castle."), ("Nd7", ""), ("O-O", "King safe."), ("Ne7", ""),
        ("Nbd2", "Develop the last knight; it can go to b3 or h4 later.")]},
    {"id": "w-french", "color": W, "name": "French: Advance (vs 1...e6)", "moves": [
        ("e4", ""), ("e6", "The French: Black prepares ...d5."), ("d4", "Take the centre."), ("d5", ""),
        ("e5", "Advance: gain space; Black's light bishop is now hemmed in."), ("c5", ""),
        ("c3", "Back up d4 so you keep your pawn chain."), ("Nc6", ""), ("Nf3", "Another defender of d4."), ("Qb6", ""),
        ("Be2", "Develop and get ready to castle."), ("cxd4", ""), ("cxd4", "Recapture with the pawn to keep the chain."), ("Nh6", ""),
        ("Nc3", "Develop; the knight can jump to b5 or a4.")]},
    {"id": "w-pirc", "color": W, "name": "Pirc / Modern (vs 1...d6)", "moves": [
        ("e4", ""), ("d6", "The Pirc: Black lets you build a centre and plans to attack it."), ("d4", "Take it."), ("Nf6", ""),
        ("Nc3", "Defend e4 and develop."), ("g6", ""), ("Be3", "The 150 Attack setup: bishop and queen aim at h6."), ("Bg7", ""),
        ("Qd2", "Prepare Bh6 to trade off Black's best bishop."), ("O-O", ""), ("f3", "Rock-solid e4; ready for g4 and h4."), ("c6", ""),
        ("Nge2", "Develop without blocking the f-pawn.")]},
    {"id": "w-englund", "color": W, "name": "Englund Gambit (vs 1.d4 e5)", "moves": [
        ("d4", ""), ("e5", "The Englund Gambit: a pawn offer full of traps."), ("dxe5", "Take the pawn."), ("Nc6", ""),
        ("Nf3", "Protect e5 and develop."), ("Qe7", ""), ("Bf4", "Defend e5 again."), ("Qb4+", ""),
        ("Bd2", "Block the check (not Qd2??)."), ("Qxb2", ""), ("Nc3", "Let the b-pawn go: you're far ahead in development."), ("Bb4", ""),
        ("Rb1", "Chase the queen."), ("Qa3", ""), ("Nd5", "Hits b4 and c7 - Black's queen and bishop are in trouble.")]},
    {"id": "w-4knights", "color": W, "name": "Four Knights (as White)", "moves": [
        ("e4", ""), ("e5", ""), ("Nf3", "Attack e5."), ("Nc6", ""), ("Nc3", "Defend e4 and develop."), ("Nf6", ""),
        ("Bb5", "Pressure the knight that guards e5."), ("Bb4", ""), ("O-O", "Castle early."), ("O-O", ""),
        ("d3", "Solid; opens the c1 bishop."), ("d6", ""), ("Bg5", "Pin the f6 knight to the queen.")]},
    {"id": "w-vs-nc6", "color": W, "name": "Nimzowitsch (vs 1...Nc6)", "moves": [
        ("e4", ""), ("Nc6", "The Nimzowitsch Defence: unusual, but sound."), ("Nf3", "Calm development - don't overreach."), ("d6", ""),
        ("d4", "Take the centre."), ("Nf6", ""), ("Nc3", "Protect e4."), ("Bg4", ""),
        ("Be2", "Unpin and prepare to castle."), ("e6", ""), ("O-O", "King safe."), ("Be7", ""),
        ("h3", "Ask the bishop: keep it or trade it."), ("Bh5", ""), ("Be3", "Finish developing; you have the bigger centre.")]},
    {"id": "w-2knights", "color": W, "name": "Italian vs Two Knights (3...Nf6)", "moves": [
        ("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("Bc4", "Aim at f7."), ("Nf6", "The Two Knights: Black hits e4."),
        ("d3", "Calmly protect e4 - no need for wild Ng5 lines."), ("Be7", ""), ("O-O", "Castle."), ("O-O", ""),
        ("Re1", "Rook behind e4."), ("d6", ""), ("c3", "Prepare d4 and a retreat square for the bishop.")]},
    # as Black: more of what you play and meet
    {"id": "b-alekhine-c4", "color": B, "name": "Alekhine's: Exchange (vs 3.c4)", "moves": [
        ("e4", ""), ("Nf6", "Tempt the e-pawn forward."), ("e5", ""), ("Nd5", ""),
        ("c4", "White chases the knight."), ("Nb6", "Retreat; the knight eyes c4 and d5."), ("d4", ""),
        ("d6", "Hit the pawn chain at once."), ("exd6", ""), ("cxd6", "Recapture toward the centre; the c-file opens for you."),
        ("Nc3", ""), ("g6", "Fianchetto: the bishop will pressure d4."), ("Be3", ""), ("Bg7", ""), ("Rc1", ""),
        ("O-O", "Castle; next ...Nc6 hits d4.")]},
    {"id": "b-alekhine-nc3", "color": B, "name": "Alekhine's vs 2.Nc3", "moves": [
        ("e4", ""), ("Nf6", ""), ("Nc3", "White avoids e5 for now."), ("d5", "Take a share of the centre."),
        ("e5", ""), ("Nfd7", "Retreat; you'll attack the e5 chain with ...c5."), ("d4", ""),
        ("e6", "A French-style structure."), ("f4", ""), ("c5", "Strike the base of the chain."), ("Nf3", ""),
        ("Nc6", "Pile up on d4.")]},
    {"id": "b-scotch", "color": B, "name": "Scotch Game (vs 3.d4)", "moves": [
        ("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("d4", "The Scotch: White opens the centre."),
        ("exd4", "Take - you can't hold e5 anyway."), ("Nxd4", ""), ("Bc5", "Develop with pressure on the d4 knight."),
        ("Be3", ""), ("Qf6", "Add a second attacker on d4."), ("c3", ""), ("Nge7", "Develop without blocking the queen."),
        ("Bc4", ""), ("O-O", "Castle; ...d5 or ...Ne5 come next.")]},
    {"id": "b-4knights", "color": B, "name": "Four Knights (as Black)", "moves": [
        ("e4", ""), ("e5", ""), ("Nf3", ""), ("Nc6", ""), ("Nc3", ""), ("Nf6", "Mirror White's development."),
        ("Bb5", ""), ("Bb4", "Copy the idea: pressure the c3 knight."), ("O-O", ""), ("O-O", "King safe."),
        ("d3", ""), ("d6", "Solid; free the c8 bishop."), ("Bg5", ""), ("Bxc3", "Give up the bishop to double White's pawns."),
        ("bxc3", ""), ("Qe7", "Unpin with ...Nd8-e6 to follow.")]},
    {"id": "b-bishops", "color": B, "name": "Bishop's Opening (vs 2.Bc4)", "moves": [
        ("e4", ""), ("e5", ""), ("Bc4", "White aims at f7 early."), ("Nf6", "Counter-attack e4 right away."),
        ("d3", ""), ("Bc5", "Active bishop, aiming at f2."), ("Nf3", ""), ("d6", "Support e5."),
        ("c3", ""), ("O-O", "Castle before anything sharp happens.")]},
    {"id": "b-petrov", "color": B, "name": "Petrov's Defence (2...Nf6)", "moves": [
        ("e4", ""), ("e5", ""), ("Nf3", ""), ("Nf6", "The Petrov: counter-attack instead of defending e5."),
        ("Nxe5", ""), ("d6", "Kick the knight FIRST - 3...Nxe4?? loses to Qe2."), ("Nf3", ""),
        ("Nxe4", "Now take back the pawn."), ("d4", ""), ("d5", "Support your centralised knight."),
        ("Bd3", ""), ("Nc6", "Develop and pressure d4."), ("O-O", ""), ("Be7", "Get ready to castle.")]},
    {"id": "b-vs-nf3", "color": B, "name": "Against 1.Nf3 / g3 setups", "moves": [
        ("Nf3", ""), ("d5", "Claim the centre."), ("g3", "White plans a fianchetto."), ("Nf6", ""),
        ("Bg2", ""), ("e6", "Solid; opens your dark bishop."), ("O-O", ""), ("Be7", ""), ("d3", ""),
        ("O-O", "King safe."), ("Nbd2", ""), ("c5", "Grab space before White plays e4.")]},
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
