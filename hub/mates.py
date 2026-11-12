"""Missed mates: every position in your games where you could force checkmate in 1, 2 or 3, and whether you did.

Exact for mate in 1 and 2. For mate in 3 the first move must be a check, or leave the opponent at most 3 replies
(this keeps the search fast and covers nearly every mate a human would see).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.dirname(HERE)):   # run as a script, the helper's folders aren't on the path yet
    if _p not in sys.path:
        sys.path.insert(0, _p)

import chess  # noqa: E402

import analysis  # noqa: E402
import training  # noqa: E402

CACHE_PATH = os.path.join(HERE, "mates.json")
PROGRESS_PATH = os.path.join(HERE, "mate_progress.json")
VERSION = 1
MAX_N = 3


def _can_mate(b, n):
    """Side to move can force mate within n of its own moves."""
    for m in list(b.legal_moves):
        b.push(m)
        try:
            if b.is_checkmate():
                return True
            if n > 1 and not b.is_game_over() and _all_replies_lose(b, n - 1):
                return True
        finally:
            b.pop()
    return False


def _all_replies_lose(b, n):
    """Opponent to move; every legal reply still lets us mate within n."""
    for r in list(b.legal_moves):
        b.push(r)
        try:
            if b.is_game_over() or not _can_mate(b, n):
                return False
        finally:
            b.pop()
    return True


def mating_moves(b, n):
    """Moves that force mate within n moves (side to move wins). Returns UCI strings."""
    out = []
    for m in list(b.legal_moves):
        gives_check = b.gives_check(m)
        b.push(m)
        try:
            if b.is_checkmate():
                out.append(m.uci())
            elif n > 1 and not b.is_game_over():
                if n >= 3 and not gives_check and b.legal_moves.count() > 3:
                    continue
                if _all_replies_lose(b, n - 1):
                    out.append(m.uci())
        finally:
            b.pop()
    return out


def shortest_mate(b):
    """(n, [first moves]) for the quickest forced mate up to MAX_N, else (None, [])."""
    for n in range(1, MAX_N + 1):
        mv = mating_moves(b, n)
        if mv:
            return n, mv
    return None, []


def scan_game(moves, user_white):
    """Every position where the user could force mate, with whether they took it."""
    board, out = chess.Board(), []
    for i, uci in enumerate(moves):
        mine = (i % 2 == 0) == user_white
        if mine and not board.is_game_over():
            n, good = shortest_mate(board)
            if n:
                out.append({"ply": i, "n": n, "fen": board.fen(), "best": good, "played": uci, "taken": uci in good})
        board.push(chess.Move.from_uci(uci))
    return out


def load_cache():
    c = analysis.load_json(CACHE_PATH, {})
    if c.get("version") != VERSION:
        return {"version": VERSION, "games": {}}
    return c


def scan_missing(games, cache, budget=None):
    """`games` = [(uuid, moves, user_white)]. Scans the ones not cached, within `budget` seconds. Returns how many remain."""
    t0, todo = time.time(), [g for g in games if g[0] not in cache["games"]]
    for k, (uid, moves, white) in enumerate(todo):
        if budget and time.time() - t0 > budget:
            analysis.save_json(CACHE_PATH, cache)
            return len(todo) - k
        cache["games"][uid] = scan_game(moves, white)
    if todo:
        analysis.save_json(CACHE_PATH, cache)
    return 0


def summary(cache, rows):
    """Chances / taken / missed for each mate length, and how the games with a miss ended."""
    by_id = {r["id"]: r for r in rows}
    per = {n: {"n": n, "chances": 0, "taken": 0, "missed": 0, "games": 0, "games_missed": 0} for n in range(1, MAX_N + 1)}
    outcome = {n: {"win": 0, "loss": 0, "draw": 0} for n in range(1, MAX_N + 1)}
    outcome_any = {"win": 0, "loss": 0, "draw": 0}
    seen_games = set()
    for uid, opps in cache["games"].items():
        row = by_id.get(uid)
        if not row:
            continue
        res = row.get("outcome") if row.get("outcome") in ("win", "loss", "draw") else "draw"
        for n in range(1, MAX_N + 1):
            mine = [o for o in opps if o["n"] == n]
            if not mine:
                continue
            per[n]["chances"] += len(mine)
            per[n]["taken"] += sum(o["taken"] for o in mine)
            per[n]["missed"] += sum(not o["taken"] for o in mine)
            per[n]["games"] += 1
            if any(not o["taken"] for o in mine):
                per[n]["games_missed"] += 1
                outcome[n][res] += 1
        if any(not o["taken"] for o in opps):
            outcome_any[res] += 1
        if opps:
            seen_games.add(uid)
    for p in per.values():
        p["rate"] = (p["taken"] / p["chances"]) if p["chances"] else None
    return {"per": list(per.values()), "outcome": {str(n): v for n, v in outcome.items()}, "outcome_any": outcome_any,
            "scanned": len(cache["games"]), "games_with_chance": len(seen_games)}


def puzzles(cache, rows, progress):
    """Missed mates as practice items, with spaced-repetition state."""
    by_id = {r["id"]: r for r in rows}
    out = []
    for uid, opps in cache["games"].items():
        row = by_id.get(uid)
        for o in opps:
            if o["taken"]:
                continue
            pid = f"{uid}:{o['ply']}"
            st = progress.get(pid, {"box": 0, "due": training.today(), "tries": 0, "solved": 0})
            out.append({"id": pid, "fen": o["fen"], "n": o["n"], "best": o["best"], "played": o["played"], "t": (row or {}).get("t", 0), **st})
    return out


def due(items, on=None):
    on = on or training.today()
    ready = [p for p in items if p["box"] < len(training.INTERVAL_DAYS) and p["due"] <= on]
    return sorted(ready, key=lambda p: (p["n"], p["due"], -p["t"]))


def record(progress, pid, correct):
    st = progress.setdefault(pid, {"box": 0, "due": training.today(), "tries": 0, "solved": 0})
    training.record(st, correct)


def all_games():
    """[(uuid, moves, user_white)] for every rated game, newest first."""
    import io

    import chess.pgn

    import stats
    out = []
    for g in sorted(stats.load_raw(), key=lambda x: x.get("end_time", 0), reverse=True):
        if g.get("time_class") not in ("rapid", "blitz", "bullet") or not g.get("pgn"):
            continue
        try:
            game = chess.pgn.read_game(io.StringIO(g["pgn"]))
            out.append((g["uuid"], [m.uci() for m in game.mainline_moves()], g["white"]["username"].lower() == stats.USERNAME))
        except Exception:
            continue
    return out


def main():
    """Scan every game not in the cache (run as its own process so the web helper stays quick)."""
    games = all_games()
    cache = load_cache()
    todo = [g for g in games if g[0] not in cache["games"]]
    for k, (uid, moves, white) in enumerate(todo):
        cache["games"][uid] = scan_game(moves, white)
        if k % 3 == 2 or k == len(todo) - 1:
            analysis.save_json(CACHE_PATH, cache)


if __name__ == "__main__":
    main()
