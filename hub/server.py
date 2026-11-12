"""Local server for the ChessCorner hub (http://127.0.0.1:8777).

Serves the web page and a small JSON API: stats from your chess.com games, a refresh button that fetches
new games from chess.com's public API, and game review (the page runs Stockfish in the browser and posts the
evaluations here; this file grades them, explains the mistakes and adds them to your practice puzzles).
Only listens on this computer.
"""
import collections
import datetime
import logging
import io
import json
import math
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import socket


def _already_running(port=8777):
    """The watchdog launches this every couple of minutes; if a helper already answers, exit before the heavy imports."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


if __name__ == "__main__" and _already_running():
    raise SystemExit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import chess  # noqa: E402
import chess.pgn  # noqa: E402

import analysis  # noqa: E402
import coach  # noqa: E402
import book  # noqa: E402
import opening_info  # noqa: E402
import openings  # noqa: E402
import stats  # noqa: E402
import training  # noqa: E402
import mates  # noqa: E402

PORT = 8777
LOG_PATH = os.path.join(HERE, "server.log")   # pythonw has no console, so this is the only record of why the helper stopped
REVIEWS_PATH = os.path.join(HERE, "reviews.json")
PUZZLES_PATH = os.path.join(APP, "puzzles.json")
GAMES_PATH = os.path.join(APP, "games.json")
LOCK = threading.Lock()
UA = {"User-Agent": "ChessCorner personal tool (stoole@redventures.com)"}


def raw_games():
    return stats.load_raw()


def find_game(uuid):
    return next((g for g in raw_games() if g.get("uuid") == uuid), None)


def user_color(g):
    return "white" if g["white"]["username"].lower() == stats.USERNAME else "black"


def game_detail(uuid):
    g = find_game(uuid)
    if not g:
        return None
    game = chess.pgn.read_game(io.StringIO(g["pgn"]))
    board = game.board()
    moves, sans, fens = [], [], []
    for m in game.mainline_moves():
        fens.append(board.fen())
        sans.append(board.san(m))
        moves.append(m.uci())
        board.push(m)
    return {"id": uuid, "color": user_color(g), "moves": moves, "san": sans, "fens": fens,
            "url": g.get("url"), "tc": g["time_class"], "result": g[user_color(g)]["result"]}


def reviewed():
    return analysis.load_json(REVIEWS_PATH, {})


def build_review(uuid, evals, batch=False):
    """Grade engine evaluations (white-POV centipawns + best move per position) for one game."""
    d = game_detail(uuid)
    if not d or len(evals) != len(d["moves"]):
        raise ValueError("evaluation count doesn't match the game")
    board = chess.Board()
    for m in d["moves"]:
        board.push_uci(m)
    final = analysis.terminal_score(board)
    positions = [(int(e["cp"]), e.get("best")) for e in evals] + [(final if final is not None else int(evals[-1]["cp"]), None)]
    result = analysis.grade(d["moves"], positions)
    mine_white = d["color"] == "white"
    flagged = []
    board = chess.Board()
    for i, uci in enumerate(d["moves"]):
        mv = result["moves"][i]
        mine = (i % 2 == 0) == mine_white
        if mv["cls"] in ("inaccuracy", "mistake", "blunder"):
            move = chess.Move.from_uci(uci)
            best_san = board.san(chess.Move.from_uci(mv["best"])) if mv["best"] else None
            try:
                why = coach.explain(board, move, mv["best"], mv["cls"], mine=mine)
            except Exception:
                why = ""
            flagged.append({"ply": i, "num": i // 2 + 1, "white": i % 2 == 0, "san": d["san"][i], "cls": mv["cls"],
                            "drop": mv["drop"], "best_san": best_san, "best": mv["best"], "why": why, "mine": mine})
        board.push(chess.Move.from_uci(uci))
    side = "white" if mine_white else "black"
    review = {"id": uuid, "color": d["color"], "me": result[side], "opp": result["black" if mine_white else "white"],
              "evals": [max(-1000, min(1000, p[0])) for p in positions], "flagged": flagged, "at": int(time.time()), "batch": bool(batch)}
    added = 0
    with LOCK:
        store = reviewed()
        store[uuid] = review
        analysis.save_json(REVIEWS_PATH, store)
        puzzles = analysis.load_json(PUZZLES_PATH, [])
        added = training.collect([{"id": "cc-" + uuid[:8], "side": side, "moves": d["moves"], "analysis": result}], puzzles)
        if added:
            analysis.save_json(PUZZLES_PATH, puzzles)
    review["new_puzzles"] = added
    if not batch:
        bump("reviews")   # bulk analysis for the charts shouldn't count as a review you chose to do
    return review


SYNC = {"t": 0.0, "ok": False}

# ---------- missed mates (scanned in the background, cached in hub/mates.json) ----------
MATE_PROGRESS_PATH = mates.PROGRESS_PATH
MATES = {"proc": None}


def mates_state():
    rows = stats.rows(raw_games())
    cache = mates.load_cache()
    total = sum(1 for r in rows if r["tc"] in ("rapid", "blitz", "bullet"))
    proc = MATES["proc"]
    if proc is not None and proc.poll() is not None:
        proc = MATES["proc"] = None
    if proc is None and total > len(cache["games"]):   # scan the rest in a separate process so the page stays fast
        import subprocess
        pyw = sys.executable
        MATES["proc"] = proc = subprocess.Popen([pyw, os.path.join(HERE, "mates.py")], cwd=HERE,
                                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    s = mates.summary(cache, rows)
    s["total"] = total
    s["scanning"] = proc is not None
    items = mates.puzzles(cache, rows, analysis.load_json(MATE_PROGRESS_PATH, {}))
    s["practice"] = {"total": len(items), "due": len(mates.due(items)),
                     "solved": sum(1 for p in items if p["box"] >= len(training.INTERVAL_DAYS))}
    return s


def mate_practice(limit):
    cache = mates.load_cache()
    items = mates.due(mates.puzzles(cache, stats.rows(raw_games()), analysis.load_json(MATE_PROGRESS_PATH, {})))[:limit]
    out = []
    for p in items:
        try:
            board = chess.Board(p["fen"])
            played = board.san(chess.Move.from_uci(p["played"]))
            out.append({"id": p["id"], "fen": p["fen"], "n": p["n"], "played": played, "box": p["box"],
                        "san": [board.san(chess.Move.from_uci(u)) for u in p["best"][:3]]})
        except Exception:
            continue
    return out


def mate_move(fen, uci, n):
    """Judge the move for a 'mate in n' position, and if it's right, play the opponent's most stubborn reply."""
    board = chess.Board(fen)
    good = mates.mating_moves(board, n)
    if uci not in good:
        return {"ok": False, "best": [board.san(chess.Move.from_uci(u)) for u in good[:4]]}
    board.push(chess.Move.from_uci(uci))
    if board.is_checkmate():
        return {"ok": True, "done": True, "positions": position_info(fen, [uci])}
    best, best_len = None, -1
    for r in list(board.legal_moves):   # the reply that keeps the game going longest
        board.push(r)
        k = 0 if board.is_checkmate() else next((j for j in range(1, n) if mates.mating_moves(board, j)), n)
        board.pop()
        if k > best_len:
            best, best_len = r, k
    return {"ok": True, "done": False, "reply": best.uci(), "n_left": max(1, n - 1), "positions": position_info(fen, [uci, best.uci()])}


def move_accuracy(tc=None):
    """Average accuracy of your moves by move number, from the games analysed here (win-chance lost per move)."""
    rows = {r["id"]: r for r in stats.rows(raw_games())}
    by, games = collections.defaultdict(list), 0
    for uid, rv in reviewed().items():
        row = rows.get(uid)
        if not row or (tc and row["tc"] != tc):
            continue
        evals, white, used = rv.get("evals") or [], rv.get("color") == "white", False
        for i in range(len(evals) - 1):
            if (i % 2 == 0) != white:
                continue
            before, after = evals[i], evals[i + 1]
            if not white:
                before, after = -before, -after
            drop = max(0.0, analysis.win_pct(before) - analysis.win_pct(after))
            by[i // 2 + 1].append(max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * drop) - 3.1669)))
            used = True
        games += used
    moves = [{"move": m, "acc": sum(v) / len(v), "n": len(v)} for m, v in sorted(by.items())]

    def phase(label, lo, hi):
        vals = [a for m, v in by.items() if lo <= m <= hi for a in v]
        return {"label": label, "acc": (sum(vals) / len(vals)) if vals else None, "n": len(vals)}
    return {"games": games, "moves": moves, "phases": [phase("Opening", 1, 10), phase("Middlegame", 11, 25), phase("Late game", 26, 999)]}


def refresh(months=3, timeout=30):
    """Fetch the latest `months` monthly archives from chess.com and merge in games we don't have yet."""
    with LOCK:
        have = {g.get("uuid"): g for g in json.load(open(stats.RAW_PATH, encoding="utf-8"))} if os.path.exists(stats.RAW_PATH) else {}
        req = urllib.request.Request(f"https://api.chess.com/pub/player/{stats.USERNAME}/games/archives", headers=UA)
        archives = json.load(urllib.request.urlopen(req, timeout=timeout))["archives"][-months:]
        added = 0
        for url in archives:
            data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout))
            for g in data.get("games", []):
                if g.get("uuid") not in have:
                    have[g["uuid"]] = g
                    added += 1
        if added:
            os.makedirs(os.path.dirname(stats.RAW_PATH), exist_ok=True)
            tmp = stats.RAW_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(list(have.values()), f)
            os.replace(tmp, stats.RAW_PATH)
        SYNC["t"], SYNC["ok"] = time.time(), True
    return added


def maybe_refresh(max_age=240):
    """Keep the game list fresh without the user pressing anything: pull the current month at most every few minutes."""
    if time.time() - SYNC["t"] < max_age:
        return 0
    SYNC["t"] = time.time()  # also throttles retries while offline
    try:
        return refresh(months=1, timeout=8)
    except Exception:
        SYNC["ok"] = False
        return 0


ACTIVITY_PATH = os.path.join(HERE, "activity.json")
ACT_LOCK = threading.Lock()
TIPS = {
    "Hanging pieces": "Before each move ask: after this, can they take anything for free - including what my moved piece was guarding?",
    "Missed free captures": "Scan every capture first. If their piece is undefended, or worth more than your attacker, take it.",
    "Forks": "Look for squares where one of your pieces would attack two targets - and check where their knight can jump next.",
    "Checkmate": "After your move, count their checks and captures. Keep your back rank covered, and look for your own mates.",
    "Early queen": "Develop knights and bishops first. The queen comes out once she has something to protect her.",
    "Positional": "These are quieter slips. The puzzle shows the better move; ask what it improves (a piece, the centre, your king).",
}


def bump(kind, n=1):
    """Count a bit of practice (puzzles, drills, reviews) against today, for the training plan and streak."""
    with ACT_LOCK:
        act = analysis.load_json(ACTIVITY_PATH, {})
        day = act.setdefault(training.today(), {})
        day[kind] = day.get(kind, 0) + n
        analysis.save_json(ACTIVITY_PATH, act)


def categorize(why):
    w = (why or "").lower()
    if "checkmate" in w:
        return "Checkmate"
    if "fork" in w:
        return "Forks"
    if "missed winning" in w:
        return "Missed free captures"
    if "can be captured" in w or "take it" in w:
        return "Hanging pieces"
    if "queen" in w and "early" in w:
        return "Early queen"
    return "Positional"


def training_summary():
    puzzles = analysis.load_json(PUZZLES_PATH, [])
    act = analysis.load_json(ACTIVITY_PATH, {})
    today = datetime.date.today()
    # reviews = games reviewed in this hub that day, plus games played that day that chess.com has an accuracy score for
    # (chess.com only attaches one once a review has been run, but it doesn't say when the review happened)
    cc_by_day, hub_by_day = collections.defaultdict(set), collections.defaultdict(set)
    for r in stats.rows(raw_games()):
        if r.get("acc"):
            cc_by_day[datetime.date.fromtimestamp(r["t"]).isoformat()].add(r["id"])
    for uid, rv in reviewed().items():
        if rv.get("batch"):
            continue
        hub_by_day[datetime.date.fromtimestamp(rv.get("at", 0)).isoformat()].add(uid)
    days = []
    for i in range(13, -1, -1):
        d = (today - datetime.timedelta(days=i)).isoformat()
        a = act.get(d, {})
        rev = len(cc_by_day[d] | hub_by_day[d])
        days.append({"d": d, "n": a.get("puzzles", 0) + a.get("drills", 0) + rev,
                     "puzzles": a.get("puzzles", 0), "drills": a.get("drills", 0), "reviews": rev})
    streak, i = 0, 0 if days[-1]["n"] else 1
    while i < len(days) and days[-1 - i]["n"]:
        streak += 1
        i += 1
    weak = collections.Counter(categorize(p.get("why")) for p in puzzles)
    progress = analysis.load_json(OPENING_PROGRESS_PATH, {})
    lines = [l for l in openings.line_summary(progress) if l["due"]]
    t0 = training.today()
    today_counts = dict(act.get(t0, {}))
    today_counts["reviews"] = days[-1]["reviews"]
    return {"today": today_counts, "days": days, "streak": streak,
            "today_reviews": {"chesscom": len(cc_by_day[t0]), "hub": len(hub_by_day[t0])}, "puzzles": training.stats(puzzles),
            "weak": [{"cat": c, "n": n, "tip": TIPS[c]} for c, n in weak.most_common()],
            "lines_due": [{"id": l["id"], "name": l["name"], "color": l["color"]} for l in lines],
            "reviews": len(reviewed())}


def source_moves(pid):
    """The full move list of the game a puzzle came from, and the ply of the mistake (or (None, ply))."""
    try:
        gid, ply = pid.rsplit(":", 1)
        ply = int(ply)
    except Exception:
        return None, 0
    if gid.startswith("cc-"):
        g = next((x for x in raw_games() if (x.get("uuid") or "").startswith(gid[3:])), None)
        return (game_detail(g["uuid"])["moves"] if g else None), ply
    g = next((x for x in analysis.load_json(GAMES_PATH, []) if x["id"] == gid), None)
    return (g["moves"] if g else None), ply


def position_info(fen, ucis):
    """Positions after each move of `ucis` from `fen`, with legal moves, so the page can step and play without its own chess logic."""
    board = chess.Board(fen)
    start = {"turn": "white" if board.turn else "black", "fullmove": board.fullmove_number}

    def info(last, san):
        return {"fen": board.fen(), "turn": "white" if board.turn else "black", "legal": [m.uci() for m in board.legal_moves],
                "last": last, "san": san, "over": board.is_game_over(), "mate": board.is_checkmate(), "check": board.is_check()}
    out = [info(None, None)]
    for u in ucis:
        move = chess.Move.from_uci(u)
        if move not in board.legal_moves:
            raise ValueError(f"illegal move {u}")
        san = board.san(move)
        board.push(move)
        out.append(info(u, san))
    return {"start": start, "positions": out}


def due_puzzles(limit):
    puzzles = analysis.load_json(PUZZLES_PATH, [])
    out = []
    for p in training.due(puzzles)[:limit]:
        try:
            moves, ply = source_moves(p["id"])
            actual = moves[ply:ply + 5] if moves else []
            board = chess.Board(p["fen"])
            sol = chess.Move.from_uci(p["solution"])
            san_sol = board.san(sol)
            try:
                san_played = board.san(chess.Move.from_uci(p["played"]))
            except Exception:
                san_played = None
            board.push(sol)
            out.append({"id": p["id"], "fen": p["fen"], "fen_after": board.fen(), "solution": p["solution"], "san": san_sol,
                        "played": san_played, "why": p.get("why", ""), "cls": p.get("cls"), "box": p["box"],
                        "cat": categorize(p.get("why")), "actual": actual})
        except Exception:
            continue
    return out


OPENING_PROGRESS_PATH = os.path.join(HERE, "opening_progress.json")
_opening_sans = {}  # uuid -> first moves in SAN, parsed once


def first_sans(g):
    """First 24 plies of a game in SAN (cached)."""
    uuid = g.get("uuid")
    if uuid not in _opening_sans:
        try:
            game = chess.pgn.read_game(io.StringIO(g["pgn"]))
            board, sans = game.board(), []
            for m in game.mainline_moves():
                sans.append(board.san(m))
                board.push(m)
                if len(sans) >= 24:
                    break
            _opening_sans[uuid] = sans
        except Exception:
            _opening_sans[uuid] = []
    return _opening_sans[uuid]


def opening_games():
    """Each rated game's colour and first 24 plies, for the 'where do I leave the book' report."""
    return [{"color": user_color(g), "san": s} for g in raw_games() if (s := first_sans(g))]


def full_opening_name(pgn):
    m = stats.ECO.search(pgn or "")
    if not m:
        return None
    words = []
    for w in m.group(1).split("-"):
        if w[:1].isdigit():
            break
        words.append(w)
    return " ".join(words) or None


def opening_detail(name, color):
    """What an opening is: typical moves and position, your record in it, variants seen, and a description."""
    games = [g for g in raw_games() if stats.opening_name(g.get("pgn")) == name and (not color or user_color(g) == color)]
    if not games:
        return None
    # follow the most common continuation while a clear majority of games agree
    line, pool = [], games
    for ply in range(14):
        counts = collections.Counter(first_sans(g)[ply] for g in pool if len(first_sans(g)) > ply)
        if not counts:
            break
        move, n = counts.most_common(1)[0]
        if n < max(2, 0.4 * len(pool)) and ply >= 2:
            break
        line.append(move)
        pool = [g for g in pool if len(first_sans(g)) > ply and first_sans(g)[ply] == move]
    board = chess.Board()
    for san in line:
        board.push_san(san)
    numbered = " ".join(f"{i // 2 + 1}.{m}" if i % 2 == 0 else m for i, m in enumerate(line))
    outcomes = collections.Counter(stats.outcome(g[user_color(g)]["result"]) for g in games)
    variants = collections.Counter(full_opening_name(g.get("pgn")) for g in games)
    m = stats.ECO.search(games[-1]["pgn"])
    slug = m.group(1).split("-")
    cut = next((i for i, w in enumerate(slug) if w[:1].isdigit()), len(slug))
    return {"name": name, "color": color, "games": len(games), "line": numbered, "fen": board.fen(),
            "last": board.peek().uci() if board.move_stack else None,
            "record": {"win": outcomes["win"], "draw": outcomes["draw"], "loss": outcomes["loss"]},
            "variants": [{"name": k, "n": v} for k, v in variants.most_common(5) if k],
            "info": opening_info.describe(name), "url": "https://www.chess.com/openings/" + "-".join(slug[:cut])}


def bot_games():
    out = []
    for g in analysis.load_json(GAMES_PATH, []):
        if len(g["moves"]) < 2:
            continue
        r = g["result"]
        mine = "win" if (r == "1-0") == (g["side"] == "white") and r in ("1-0", "0-1") else \
            "draw" if r == "1/2-1/2" else "loss" if r in ("1-0", "0-1") else "unfinished"
        out.append({"id": g["id"], "side": g["side"], "elo": g["elo"], "plies": len(g["moves"]), "outcome": mine})
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, *a):
        pass

    def handle_error(self, request, client_address):
        logging.exception("request failed")

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/export" and self.host_ok():
            try:
                import snapshot
                body = snapshot.build(globals()).encode("utf-8")
            except Exception:
                logging.exception("export failed")
                return self.send_error(500, "export failed - see server.log")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f'attachment; filename="{snapshot.filename()}"')
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if not url.path.startswith("/api/"):
            if not self.host_ok():
                return self.send_error(403)
            return super().do_GET()
        if not self.host_ok():
            return self.send_json({"error": "bad host"}, 403)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/api/summary":
                s = stats.summary(bot_games())
                s["puzzles"] = training.stats(analysis.load_json(PUZZLES_PATH, []))
                return self.send_json(s)
            if url.path == "/api/rows":
                maybe_refresh()
                return self.send_json({"player": stats.USERNAME, "generated": int(time.time()), "synced": int(SYNC["t"]),
                                       "rows": stats.rows(raw_games())})
            if url.path == "/api/moveacc":
                return self.send_json(move_accuracy(q.get("tc", [""])[0] or None))
            if url.path == "/api/mates":
                return self.send_json(mates_state())
            if url.path == "/api/mates/practice":
                return self.send_json({"puzzles": mate_practice(int(q.get("limit", ["10"])[0]))})
            if url.path == "/api/training":
                return self.send_json(training_summary())
            if url.path == "/api/puzzles":
                return self.send_json({"puzzles": due_puzzles(int(q.get("limit", ["10"])[0]))})
            if url.path == "/api/games":
                return self.send_json(stats.game_list(set(reviewed()), int(q.get("limit", ["60"])[0])))
            if url.path == "/api/game":
                d = game_detail(q["id"][0])
                return self.send_json(d if d else {"error": "not found"}, 200 if d else 404)
            if url.path == "/api/opening/lines":
                return self.send_json(openings.line_summary(analysis.load_json(OPENING_PROGRESS_PATH, {})))
            if url.path == "/api/opening/line":
                lid = q["id"][0]
                if lid not in openings.BUILT:
                    return self.send_json({"error": "unknown line"}, 404)
                meta = next(l for l in openings.LINES if l["id"] == lid)
                return self.send_json({"id": lid, "name": meta["name"], "color": meta["color"], "plies": openings.BUILT[lid]})
            if url.path == "/api/opening/explore":
                d = opening_detail(q["name"][0], q.get("color", [""])[0])
                return self.send_json(d if d else {"error": "no games"}, 200 if d else 404)
            if url.path == "/api/opening/report":
                return self.send_json(openings.report(opening_games()))
            if url.path == "/api/review":
                r = reviewed().get(q["id"][0])
                return self.send_json(r if r else {"error": "not reviewed"}, 200 if r else 404)
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)
        self.send_json({"error": "unknown"}, 404)

    def do_POST(self):
        if not self.host_ok() or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send_json({"error": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length", 0))
        if n > 2_000_000:
            return self.send_json({"error": "too large"}, 413)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/refresh":
                return self.send_json({"added": refresh()})
            if self.path == "/api/analysis":
                return self.send_json(build_review(body["id"], body["evals"], bool(body.get("batch"))))
            if self.path == "/api/position":
                return self.send_json(position_info(body["fen"], list(body.get("moves", []))))
            if self.path == "/api/explore":
                bk = book.get()
                ucis = bk.uci_from_text(body["text"]) if "text" in body else list(body.get("moves", []))
                return self.send_json(bk.explore(ucis))
            if self.path == "/api/opening/record":
                if body["id"] not in openings.BUILT:
                    return self.send_json({"error": "unknown line"}, 404)
                with LOCK:
                    progress = analysis.load_json(OPENING_PROGRESS_PATH, {})
                    openings.record(progress, body["id"], bool(body["correct"]))
                    analysis.save_json(OPENING_PROGRESS_PATH, progress)
                bump("drills")
                return self.send_json({"ok": True})
            if self.path == "/api/mates/move":
                return self.send_json(mate_move(body["fen"], body["move"], int(body["n"])))
            if self.path == "/api/mates/record":
                with LOCK:
                    progress = analysis.load_json(MATE_PROGRESS_PATH, {})
                    mates.record(progress, body["id"], bool(body["correct"]))
                    analysis.save_json(MATE_PROGRESS_PATH, progress)
                bump("puzzles")
                return self.send_json({"ok": True})
            if self.path == "/api/puzzles/record":
                with LOCK:
                    puzzles = analysis.load_json(PUZZLES_PATH, [])
                    p = next((x for x in puzzles if x["id"] == body["id"]), None)
                    if not p:
                        return self.send_json({"error": "unknown puzzle"}, 404)
                    training.record(p, bool(body["correct"]))
                    analysis.save_json(PUZZLES_PATH, puzzles)
                bump("puzzles")
                if body["correct"]:
                    bump("puzzles_ok")
                return self.send_json({"ok": True})
        except Exception as e:
            return self.send_json({"error": str(e)}, 500)
        self.send_json({"error": "unknown"}, 404)


def main():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        return  # already running
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s")
    logging.info("helper started, pid %s", os.getpid())
    threading.Thread(target=book.get, daemon=True).start()  # load the opening book in the background (~7 s)

    def keep_fresh():
        while True:
            maybe_refresh()
            time.sleep(300)
    threading.Thread(target=keep_fresh, daemon=True).start()
    try:
        server.serve_forever()
    except BaseException as e:   # a normal Windows kill leaves no trace; anything else is logged here
        logging.exception("helper stopped: %r", e)
        raise
    finally:
        logging.info("helper exiting")


if __name__ == "__main__":
    main()
