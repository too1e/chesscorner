"""Opening book lookup built from the lichess 'chess-openings' dataset (CC0), stored in data/*.tsv.

Given the moves played so far it names the position (or the last named position you passed through), and lists
the book moves that can follow plus the full book lines from here. Positions are matched by EPD, so different
move orders reaching the same position are recognised.
"""
import collections
import csv
import os
import re
import threading

import chess

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TOKEN = re.compile(r"\d+\.(\.\.)?|\.\.\.")


class Book:
    def __init__(self):
        self.entries = []                                  # {"eco","name","sans","epds"}
        self.named = {}                                    # epd after the entry's last move -> entry index
        self.through = collections.defaultdict(list)       # epd before a move -> [(entry index, ply)]
        for letter in "abcde":
            path = os.path.join(DATA, letter + ".tsv")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    self._add(row["eco"], row["name"], row["pgn"])

    def _add(self, eco, name, pgn):
        board, sans, epds = chess.Board(), [], [chess.Board().epd()]
        try:
            for tok in TOKEN.sub(" ", pgn).split():
                move = board.parse_san(tok)
                sans.append(board.san(move))
                board.push(move)
                epds.append(board.epd())
        except ValueError:
            return
        idx = len(self.entries)
        self.entries.append({"eco": eco, "name": name, "sans": sans, "epds": epds})
        self.named.setdefault(epds[-1], idx)
        for ply in range(len(sans)):
            self.through[epds[ply]].append((idx, ply))

    @staticmethod
    def numbered(board, sans):
        """'3.Bb5 a6' style text for `sans` played from `board`'s position."""
        out, n, white = [], board.fullmove_number, board.turn == chess.WHITE
        for i, s in enumerate(sans):
            if white:
                out.append(f"{n}.{s}")
            else:
                out.append(f"{n}…{s}" if i == 0 else s)
                n += 1
            white = not white
        return " ".join(out)

    def explore(self, ucis):
        """Describe the position reached by `ucis` (raises ValueError on an illegal move)."""
        board, epds, sans = chess.Board(), [chess.Board().epd()], []
        for u in ucis:
            move = chess.Move.from_uci(u)
            if move not in board.legal_moves:
                raise ValueError(f"illegal move {u}")
            sans.append(board.san(move))
            board.push(move)
            epds.append(board.epd())
        here = epds[-1]
        current = self.entries[self.named[here]] if here in self.named else None
        last, last_ply = None, None
        for ply in range(len(epds) - 1, -1, -1):
            if epds[ply] in self.named:
                last, last_ply = self.entries[self.named[epds[ply]]], ply
                break
        in_book = here in self.through or here in self.named
        left_at = None
        if not in_book:
            for ply, e in enumerate(epds):
                if e not in self.through and e not in self.named:
                    left_at = ply
                    break

        groups = collections.defaultdict(list)
        lines = []
        for idx, ply in self.through.get(here, []):
            e = self.entries[idx]
            groups[e["sans"][ply]].append(e)
            lines.append((len(e["sans"]) - ply, idx, ply))
        nxt = []
        for san, es in groups.items():
            es.sort(key=lambda e: len(e["sans"]))
            names = []
            for e in es:
                if e["name"] not in names:
                    names.append(e["name"])
                if len(names) == 3:
                    break
            nxt.append({"san": san, "uci": board.parse_san(san).uci(), "count": len(es), "names": names})
        nxt.sort(key=lambda m: -m["count"])
        lines.sort()
        out_lines, seen = [], set()
        for _, idx, ply in lines:
            e = self.entries[idx]
            key = (e["name"], tuple(e["sans"][ply:]))
            if key in seen:
                continue
            seen.add(key)
            tmp = board.copy()
            path = []
            for s in e["sans"][ply:]:
                m = tmp.parse_san(s)
                path.append(m.uci())
                tmp.push(m)
            out_lines.append({"eco": e["eco"], "name": e["name"], "moves": self.numbered(board, e["sans"][ply:]),
                              "uci": path})
            if len(out_lines) >= 14:
                break
        return {"fen": board.fen(), "turn": "white" if board.turn else "black", "san": sans, "moves": list(ucis),
                "legal": [m.uci() for m in board.legal_moves], "in_book": in_book, "left_at": left_at,
                "current": {"eco": current["eco"], "name": current["name"]} if current else None,
                "last_named": {"eco": last["eco"], "name": last["name"], "ply": last_ply} if last else None,
                "next": nxt, "lines": out_lines, "game_over": board.is_game_over(), "check": board.is_check(),
                "last": ucis[-1] if ucis else None}

    def uci_from_text(self, text):
        """'1.e4 e5 2.Nf3' (or any SAN list) -> UCI move list; raises ValueError naming the bad token."""
        board, out = chess.Board(), []
        for tok in TOKEN.sub(" ", text).replace("e.p.", "").split():
            if tok in ("1-0", "0-1", "1/2-1/2", "*"):
                break
            try:
                move = board.parse_san(tok)
            except ValueError:
                raise ValueError(f"couldn't read the move “{tok}”")
            out.append(move.uci())
            board.push(move)
        return out


_BOOK = None
_LOCK = threading.Lock()


def get():
    global _BOOK
    with _LOCK:  # the server warms this up in a thread, so a request must wait rather than load a second copy
        if _BOOK is None:
            _BOOK = Book()
        return _BOOK
