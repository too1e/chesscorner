"""Small pure-Python chess engine with an Elo-style strength dial (about 600-2000).

Negamax alpha-beta + quiescence over material and piece-square tables. Strength is
shaped by search depth, move-choice noise and occasional random blunders.
"""
import math
import random
import time

import chess

MATE = 100000
VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}

# Piece-square tables, written from White's side with rank 8 on the first row.
PST = {
    chess.PAWN: [0, 0, 0, 0, 0, 0, 0, 0, 50, 50, 50, 50, 50, 50, 50, 50, 10, 10, 20, 30, 30, 20, 10, 10,
                 5, 5, 10, 25, 25, 10, 5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, -5, -10, 0, 0, -10, -5, 5,
                 5, 10, 10, -20, -20, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
    chess.KNIGHT: [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40,
                   -30, 0, 10, 15, 15, 10, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30,
                   -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30,
                   -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
    chess.BISHOP: [-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10,
                   -10, 0, 5, 10, 10, 5, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10,
                   -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10,
                   -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20],
    chess.ROOK: [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, 10, 10, 10, 10, 5, -5, 0, 0, 0, 0, 0, 0, -5,
                 -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5,
                 -5, 0, 0, 0, 0, 0, 0, -5, 0, 0, 0, 5, 5, 0, 0, 0],
    chess.QUEEN: [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10,
                  -10, 0, 5, 5, 5, 5, 0, -10, -5, 0, 5, 5, 5, 5, 0, -5,
                  0, 0, 5, 5, 5, 5, 0, -5, -10, 5, 5, 5, 5, 5, 0, -10,
                  -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
    chess.KING: [-30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
                 -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
                 -20, -30, -30, -40, -40, -30, -30, -20, -10, -20, -20, -20, -20, -20, -20, -10,
                 20, 20, 0, 0, 0, 0, 20, 20, 20, 30, 10, 0, 0, 10, 30, 20],
}

# (search depth, time budget in seconds, softmax temperature in centipawns, blunder probability)
LEVELS = [
    (600, 2, 1.0, 100, 0.20, 250),
    (800, 3, 1.5, 80, 0.12, 200),
    (1000, 3, 1.5, 60, 0.07, 150),
    (1200, 3, 2.0, 45, 0.03, 120),
    (1400, 4, 2.5, 30, 0.0, 0),
    (1600, 4, 3.0, 20, 0.0, 0),
    (1800, 5, 3.5, 10, 0.0, 0),
    (2000, 6, 5.0, 0, 0.0, 0),
]
# Columns: elo, search depth, time budget (s), softmax temperature (cp), mistake probability,
# mistake size cap (cp). A "mistake" is a random move among those that lose at most `cap` centipawns
# versus the best move, so low levels drop pawns and pieces but don't randomly throw away the queen.


def level_for(elo):
    """Linearly interpolate the strength parameters between the nearest table rows."""
    elo = max(LEVELS[0][0], min(LEVELS[-1][0], elo))
    for lo, hi in zip(LEVELS, LEVELS[1:]):
        if lo[0] <= elo <= hi[0]:
            t = (elo - lo[0]) / (hi[0] - lo[0])
            return (round(lo[1] + t * (hi[1] - lo[1])), lo[2] + t * (hi[2] - lo[2]),
                    lo[3] + t * (hi[3] - lo[3]), lo[4] + t * (hi[4] - lo[4]),
                    lo[5] + t * (hi[5] - lo[5]))
    return LEVELS[-1][1:]


class _Timeout(Exception):
    pass


class MiniEngine:
    def evaluate(self, board):
        """Static score in centipawns from the side to move's point of view."""
        score = 0
        for sq, piece in board.piece_map().items():
            idx = (7 - (sq >> 3)) * 8 + (sq & 7) if piece.color == chess.WHITE else (sq >> 3) * 8 + (sq & 7)
            v = VALUES[piece.piece_type] + PST[piece.piece_type][idx]
            score += v if piece.color == chess.WHITE else -v
        return score if board.turn == chess.WHITE else -score

    def order(self, board, moves):
        def key(m):
            s = 0
            if board.is_capture(m):
                victim = board.piece_type_at(m.to_square) or chess.PAWN  # en passant
                s += 10 * VALUES[victim] - VALUES[board.piece_type_at(m.from_square)] + 1000
            if m.promotion:
                s += 800
            return -s
        return sorted(moves, key=key)

    cancel = None

    def tick(self):
        self.nodes += 1
        if self.nodes & 255 == 0 and (time.time() > self.deadline or (self.cancel and self.cancel())):
            raise _Timeout

    def quiesce(self, board, alpha, beta, qdepth):
        self.tick()
        stand = self.evaluate(board)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        if qdepth <= 0:
            return stand
        for m in self.order(board, [m for m in board.legal_moves if board.is_capture(m) or m.promotion]):
            board.push(m)
            score = -self.quiesce(board, -beta, -alpha, qdepth - 1)
            board.pop()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def search(self, board, depth, alpha, beta, ply):
        self.tick()
        if board.is_insufficient_material():
            return 0
        if depth <= 0:
            return self.quiesce(board, alpha, beta, 4)
        moves = list(board.legal_moves)
        if not moves:
            return -MATE + ply if board.is_check() else 0
        best = -MATE
        for m in self.order(board, moves):
            board.push(m)
            score = -self.search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if score > best:
                best = score
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best

    def root_scores(self, board, depth):
        scores = {}
        for m in self.order(board, list(board.legal_moves)):
            board.push(m)
            scores[m] = -self.search(board, depth - 1, -MATE, MATE, 1)
            board.pop()
        return scores

    def search_root(self, board, depth):
        """Best (score, move) for the side to move, using a normal alpha-beta window."""
        alpha, best = -MATE, None
        for m in self.order(board, list(board.legal_moves)):
            board.push(m)
            score = -self.search(board, depth - 1, -MATE, -alpha, 1)
            board.pop()
            if best is None or score > alpha:
                alpha, best = score, m
        return alpha, best

    def analyse(self, board, max_depth=4, budget=3.0, cancel=None):
        """(score from White's point of view, best move), or None if `cancel()` turned true.

        Mate scores are +/-(MATE - plies). Unlike pick(), only the best line matters, so the root
        uses a normal alpha-beta window, which is several times faster than scoring every move.
        """
        pristine = board
        board = board.copy()  # a cut-off search leaves moves pushed on this copy, so never read it afterwards
        white_to_move = pristine.turn
        self.nodes, self.deadline, self.cancel = 0, time.time() + budget, cancel
        score = move = None
        for depth in range(1, max_depth + 1):
            try:
                score, move = self.search_root(board, depth)
            except _Timeout:
                break  # the search was cut off mid-line, so `board` still has moves pushed on it
            if abs(score) > MATE - 100:
                break
        self.cancel = None
        if cancel and cancel():
            return None
        if score is None:
            score = self.evaluate(pristine)
        return (score if white_to_move == chess.WHITE else -score), move

    def eval_white(self, board, max_depth=4, budget=3.0, cancel=None):
        result = self.analyse(board, max_depth, budget, cancel)
        return None if result is None else result[0]

    def pick(self, board, elo):
        max_depth, budget, temp, blunder, cap = level_for(elo)
        self.cancel = None
        board = board.copy()
        legal = list(board.legal_moves)
        if len(legal) == 1:
            return legal[0]
        self.nodes, self.deadline = 0, time.time() + budget
        scores = None
        for depth in range(1, max_depth + 1):
            try:
                scores = self.root_scores(board, depth)
            except _Timeout:
                break
            if any(s > MATE - 100 for s in scores.values()):
                break  # forced mate found
        if scores is None:  # ran out of time before depth 1 finished
            return random.choice(legal)
        best = max(scores.values())
        if blunder and random.random() < blunder and best < MATE - 100:
            ok = [m for m, s in scores.items() if s >= best - cap]
            return random.choice(ok)
        if temp <= 0:
            return random.choice([m for m, s in scores.items() if s == best])
        moves = list(scores)
        weights = [math.exp(max(-50, (scores[m] - best) / temp)) for m in moves]
        return random.choices(moves, weights=weights)[0]
