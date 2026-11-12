"""Turn raw chess.com game data (and games played against the desk bot) into the numbers the hub draws."""
import collections
import io
import json
import os
import re
import statistics

import chess
import chess.pgn

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
RAW_PATH = os.path.join(APP, "chesscom", "games_raw.json")
USERNAME = "samt43"

DRAWS = {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}
CLOCK = re.compile(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]")
ECO = re.compile(r'\[ECOUrl "https://www\.chess\.com/openings/([^"]+)"\]')
TIME_CLASSES = ("rapid", "blitz", "bullet")


def load_raw():
    try:
        with open(RAW_PATH, encoding="utf-8") as f:
            return [g for g in json.load(f) if g.get("rules") == "chess"]
    except Exception:
        return []


def outcome(result):
    return "win" if result == "win" else "draw" if result in DRAWS else "loss"


def parse_control(tc):
    """'600+5' -> (600, 5); daily controls ('1/86400') -> None."""
    m = re.fullmatch(r"(\d+)(?:\+(\d+))?", tc or "")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def clock_stats(pgn, color, control):
    """(avg seconds per move, my clock left at the end as a fraction of the start clock) or (None, None)."""
    if not control:
        return None, None
    base, inc = control
    clocks = [int(h) * 3600 + int(m) * 60 + float(s) for h, m, s in CLOCK.findall(pgn or "")]
    mine = clocks[0 if color == "white" else 1::2]
    if len(mine) < 3:
        return None, None
    spent, prev = [], base
    for c in mine:
        spent.append(max(0.0, prev + inc - c))
        prev = c
    return statistics.mean(spent), mine[-1] / base


def opening_name(pgn):
    m = ECO.search(pgn or "")
    if not m:
        return None
    words = []
    for w in m.group(1).split("-"):
        if re.match(r"^\d", w):
            break
        words.append(w)
    return " ".join(words[:3]) or None


FEATURES_PATH = os.path.join(APP, "chesscom", "features.json")
CHECK_KINDS = ["Q", "R", "B", "N", "P", "D"]  # D = discovered or double check
_KIND_OF = {chess.QUEEN: 0, chess.ROOK: 1, chess.BISHOP: 2, chess.KNIGHT: 3, chess.PAWN: 4}


def features(g):
    """Things only visible by replaying the moves: checks by piece, mates, castling, captures."""
    me_white = g["white"]["username"].lower() == USERNAME
    game = chess.pgn.read_game(io.StringIO(g.get("pgn") or ""))
    board = game.board()
    cm, co = [0] * 6, [0] * 6
    f = {"plies": 0, "fc": None, "mate": None, "cast_me": None, "cast_opp": None, "qearly": False,
         "caps_me": 0, "caps_opp": 0, "promo": 0}
    last_mine = None
    for i, move in enumerate(game.mainline_moves()):
        mine = (i % 2 == 0) == me_white
        number = i // 2 + 1
        piece = board.piece_at(move.from_square)
        if board.is_capture(move):
            f["caps_me" if mine else "caps_opp"] += 1
        if board.is_castling(move):
            key = "cast_me" if mine else "cast_opp"
            if f[key] is None:
                f[key] = number
        if mine and piece.piece_type == chess.QUEEN and number <= 5:
            f["qearly"] = True
        if mine and move.promotion:
            f["promo"] += 1
        board.push(move)
        f["plies"] = i + 1
        last_mine = mine
        if board.is_check():
            checkers = board.checkers()
            moved = board.piece_at(move.to_square)
            kind = 5 if len(checkers) > 1 or move.to_square not in checkers else _KIND_OF.get(moved.piece_type, 5)
            (cm if mine else co)[kind] += 1
            if f["fc"] is None:
                f["fc"] = "me" if mine else "opp"
            if board.is_checkmate():
                king = board.king(board.turn)
                back = chess.square_rank(king) in (0, 7) and kind in (0, 1) and \
                    chess.square_rank(move.to_square) == chess.square_rank(king)
                f["mate"] = {"by": "me" if mine else "opp", "piece": CHECK_KINDS[kind], "back": bool(back)}
    f["cm"], f["co"] = cm, co
    return f


def _load_features():
    try:
        with open(FEATURES_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def rows(games):
    out, cache, dirty = [], _load_features(), False
    for g in games:
        color = "white" if g["white"]["username"].lower() == USERNAME else "black"
        me, opp = g[color], g["black" if color == "white" else "white"]
        control = parse_control(g.get("time_control"))
        avg, left = clock_stats(g.get("pgn"), color, control)
        uuid = g.get("uuid")
        if uuid not in cache:
            try:
                cache[uuid] = features(g)
            except Exception:
                cache[uuid] = {}
            dirty = True
        out.append({"id": uuid, "url": g.get("url"), "t": g["end_time"], "tc": g["time_class"],
                    "color": color, "rating": me["rating"], "opp": opp["rating"], "result": me["result"],
                    "outcome": outcome(me["result"]), "opp_result": opp["result"], "acc": (g.get("accuracies") or {}).get(color),
                    "avg_sec": avg, "clock_left": left, "opening": opening_name(g.get("pgn")),
                    "control": g.get("time_control"), **cache[uuid]})
    if dirty:
        try:
            tmp = FEATURES_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
            os.replace(tmp, FEATURES_PATH)
        except Exception:
            pass
    out.sort(key=lambda r: r["t"])
    return out


def wld(rs):
    n = len(rs)
    c = collections.Counter(r["outcome"] for r in rs)
    return {"n": n, "win": c["win"], "draw": c["draw"], "loss": c["loss"]}


def summary(bot_games=None):
    rs = rows(load_raw())
    out = {"player": USERNAME, "n_games": len(rs), "first": rs[0]["t"] if rs else None, "last": rs[-1]["t"] if rs else None}
    out["ratings"] = {tc: [[r["t"], r["rating"]] for r in rs if r["tc"] == tc] for tc in TIME_CLASSES}
    out["wld"] = {tc: wld([r for r in rs if r["tc"] == tc]) for tc in TIME_CLASSES}
    out["by_color"] = {c: wld([r for r in rs if r["color"] == c]) for c in ("white", "black")}
    out["loss_reasons"] = {tc: dict(collections.Counter(r["result"] for r in rs if r["tc"] == tc and r["outcome"] == "loss"))
                           for tc in TIME_CLASSES}
    out["accuracy"] = {tc: [[r["t"], r["acc"]] for r in rs if r["tc"] == tc and r["acc"]] for tc in TIME_CLASSES}
    time_habits = {}
    for tc in TIME_CLASSES:
        sub = [r for r in rs if r["tc"] == tc]
        avgs = [r["avg_sec"] for r in sub if r["avg_sec"] is not None]
        left = [r["clock_left"] for r in sub if r["clock_left"] is not None and r["result"] != "timeout"]
        losses = [r for r in sub if r["outcome"] == "loss"]
        time_habits[tc] = {"games": len(sub), "avg_sec": statistics.mean(avgs) if avgs else None,
                           "median_left": statistics.median(left) if left else None,
                           "timeout_losses": sum(1 for r in losses if r["result"] == "timeout"), "losses": len(losses)}
    out["time"] = time_habits
    openings = {}
    for color in ("white", "black"):
        by = collections.defaultdict(list)
        for r in rs:
            if r["color"] == color and r["opening"]:
                by[r["opening"]].append(r)
        top = sorted(by.items(), key=lambda kv: -len(kv[1]))[:14]
        openings[color] = [{"name": k, "n": len(v), "win_pct": round(100 * sum(r["outcome"] == "win" for r in v) / len(v))}
                           for k, v in top]
    out["openings"] = openings
    out["latest"] = {tc: out["ratings"][tc][-1][1] if out["ratings"][tc] else None for tc in TIME_CLASSES}
    out["best"] = {tc: max((p[1] for p in out["ratings"][tc]), default=None) for tc in TIME_CLASSES}
    out["bot"] = bot_games or []
    return out


def game_list(reviewed_ids, limit=60):
    rs = rows(load_raw())
    rs = [r for r in rs if r["tc"] in TIME_CLASSES and r["id"]][-limit:][::-1]
    for r in rs:
        r["reviewed"] = r["id"] in reviewed_ids
    return rs
