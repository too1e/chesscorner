"""Practice puzzles built from your own mistakes, with simple spaced repetition.

Every mistake or blunder you made in an analysed game becomes a puzzle: the position before your move,
with the engine's better move as the answer. Solving one moves it up a "box"; each box waits longer before
the puzzle comes back (1, 2, 4, 7 days); missing one sends it back to box 0. Past the last box it's retired.
"""
import datetime

import chess

import coach

INTERVAL_DAYS = [0, 1, 2, 4, 7]  # wait before a puzzle in box n is due again
FLAGGED = ("mistake", "blunder")


def today():
    return datetime.date.today().isoformat()


def collect(games, puzzles):
    """Add puzzles for every flagged user move in `games` not already stored. Returns how many were added."""
    have = {p["id"] for p in puzzles}
    added = 0
    for g in games:
        a = g.get("analysis")
        if not a:
            continue
        user_white = g["side"] == "white"
        board = chess.Board()
        for i, uci in enumerate(g["moves"]):
            move = chess.Move.from_uci(uci)
            mv = a["moves"][i] if i < len(a["moves"]) else None
            pid = f"{g['id']}:{i}"
            if mv and (i % 2 == 0) == user_white and mv["cls"] in FLAGGED and mv.get("best") and pid not in have:
                try:
                    why = coach.explain(board, move, mv["best"], mv["cls"], mine=True)
                except Exception:
                    why = ""
                puzzles.append({"id": pid, "fen": board.fen(), "solution": mv["best"], "played": uci,
                                "cls": mv["cls"], "why": why, "box": 0, "due": today(), "tries": 0, "solved": 0})
                have.add(pid)
                added += 1
            board.push(move)
    return added


def due(puzzles, on=None):
    """Puzzles to practice now, most overdue (and most-missed) first."""
    on = on or today()
    ready = [p for p in puzzles if p["box"] < len(INTERVAL_DAYS) and p["due"] <= on]
    return sorted(ready, key=lambda p: (p["due"], p["box"]))


def record(puzzle, correct, on=None):
    """Update a puzzle after an attempt: correct on the first try moves it up a box, anything else resets it."""
    on = on or today()
    puzzle["tries"] += 1
    if correct:
        puzzle["solved"] += 1
        puzzle["box"] += 1
    else:
        puzzle["box"] = 0
    if puzzle["box"] < len(INTERVAL_DAYS):
        puzzle["due"] = (datetime.date.fromisoformat(on) + datetime.timedelta(days=INTERVAL_DAYS[puzzle["box"]])).isoformat()


def stats(puzzles, on=None):
    on = on or today()
    return {"total": len(puzzles), "due": len(due(puzzles, on)),
            "retired": sum(1 for p in puzzles if p["box"] >= len(INTERVAL_DAYS))}
