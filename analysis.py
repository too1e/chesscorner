"""Game history storage and post-game analysis for ChessCorner.

Each position of a finished (or abandoned) game is searched with the built-in engine; the drop in
winning chances caused by each move gives its accuracy and a label (inaccuracy / mistake / blunder).
Average centipawn loss (ACPL) is mapped to an Elo-like number with a table measured from the bot itself
(see calibrate.py), so "your level" and "the bot's level" are on the same scale.
"""
import json
import math
import os

import chess

from miniengine import MATE

# (ACPL, Elo) pairs, ACPL ascending. Overridden by calibration.json when present.
DEFAULT_POINTS = [(20, 2000), (45, 1600), (80, 1200), (130, 900), (200, 600)]
CPL_CAP = 300   # a single awful move shouldn't dominate the average
EVAL_CLIP = 1000


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def win_pct(cp):
    """Winning chances (0-100) for a centipawn score, same curve family chess.com/lichess use."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def classify(win_drop):
    if win_drop <= 2:
        return "best"
    if win_drop <= 5:
        return "good"
    if win_drop <= 10:
        return "inaccuracy"
    if win_drop <= 20:
        return "mistake"
    return "blunder"


def terminal_score(board):
    """White-POV score for a finished position, or None if the game goes on."""
    if board.is_checkmate():
        return -MATE if board.turn == chess.WHITE else MATE
    if board.is_game_over():
        return 0
    return None


def analyse_game(moves, engine, cancel=None, progress=None, depth=4, budget=1.5):
    """Analyse a list of UCI moves. Returns the analysis dict, or None if cancelled."""
    board = chess.Board()
    positions = []  # (white-POV cp, best move uci) for the position before each move, plus the final one
    for i in range(len(moves) + 1):
        if cancel and cancel():
            return None
        t = terminal_score(board)
        if t is not None:
            positions.append((t, None))
        else:
            r = engine.analyse(board, max_depth=depth, budget=budget, cancel=cancel)
            if r is None:
                return None
            positions.append((r[0], r[1].uci() if r[1] else None))
        if i < len(moves):
            board.push_uci(moves[i])
        if progress:
            progress(i + 1, len(moves) + 1)

    return grade(moves, positions)


def grade(moves, positions):
    """Score a game from engine evaluations.

    `positions` has len(moves)+1 entries of (white-POV centipawns, best move uci or None): one for the
    position before each move and one for the final position. Works with any engine's numbers.
    """
    out = {"moves": [], "evals": [p[0] for p in positions]}
    for i, uci in enumerate(moves):
        white = i % 2 == 0
        before, after = (max(-EVAL_CLIP, min(EVAL_CLIP, positions[j][0])) for j in (i, i + 1))
        if not white:
            before, after = -before, -after
        cpl = max(0, before - after)
        drop = max(0.0, win_pct(before) - win_pct(after))
        acc = max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669))
        cls = classify(drop)
        best = positions[i][1]
        out["moves"].append({"cpl": cpl, "drop": round(drop, 1), "acc": round(acc, 1), "cls": cls,
                             "best": best if best and best != uci and cls in ("inaccuracy", "mistake", "blunder") else None})
    for name, parity in (("white", 0), ("black", 1)):
        mine = [m for i, m in enumerate(out["moves"]) if i % 2 == parity]
        if mine:
            out[name] = {"acpl": sum(min(m["cpl"], CPL_CAP) for m in mine) / len(mine),
                         "acc": sum(m["acc"] for m in mine) / len(mine),
                         "n": len(mine),
                         **{c: sum(1 for m in mine if m["cls"] == c) for c in ("inaccuracy", "mistake", "blunder")}}
    return out


def estimate_elo(acpl, points):
    """Map an ACPL to an Elo-like rating by interpolating the calibration table (clamped at its ends)."""
    pts = sorted(points)
    if acpl <= pts[0][0]:
        return pts[0][1]
    for (a0, e0), (a1, e1) in zip(pts, pts[1:]):
        if a0 <= acpl <= a1:
            return e0 + (e1 - e0) * (acpl - a0) / (a1 - a0)
    return pts[-1][1]


def side_stats(game, color):
    """Analysis block for one side of a game ('white'/'black'), or None if not analysed."""
    a = game.get("analysis")
    return a.get(color) if a else None
