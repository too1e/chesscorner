"""Plain-language reasons for flagged moves.

The engine says *that* a move lost ground; this module looks at the board to say *why*, using simple
tactical checks: hung pieces, missed free captures, missed mates, forks, and a couple of opening habits.
All checks work from a position and a move, so explanations can be rebuilt at any time and nothing
extra has to be stored with a game.
"""
import chess

VALUE = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def _name(piece):
    return chess.piece_name(piece.piece_type)


def _sq(sq):
    return chess.square_name(sq)


def capture_gain(board, move):
    """Material (centipawns) the side to move nets by playing capture `move`, allowing one recapture."""
    victim = board.piece_at(move.to_square)
    gain = VALUE[victim.piece_type] if victim else 100  # en passant takes a pawn
    attacker = board.piece_at(move.from_square)
    after = board.copy(stack=False)
    after.push(move)
    if after.is_attacked_by(after.turn, move.to_square):  # the victim's side can recapture
        gain -= VALUE[attacker.piece_type]
    return gain


def best_capture(board):
    """(gain, move) of the most profitable capture for the side to move, or None."""
    best = None
    for m in board.legal_moves:
        if board.is_capture(m):
            g = capture_gain(board, m)
            if best is None or g > best[0]:
                best = (g, m)
    return best


def forks(board, move):
    """If `move` forks two valuable targets, return (piece, [target squares]); otherwise None."""
    b = board.copy(stack=False)
    b.push(move)
    mover = b.piece_at(move.to_square)
    if mover is None:
        return None
    enemy = b.turn
    targets = []
    for sq in b.attacks(move.to_square):
        t = b.piece_at(sq)
        if not t or t.color != enemy:
            continue
        if t.piece_type == chess.KING or (VALUE[t.piece_type] >= 300 and (
                VALUE[t.piece_type] > VALUE[mover.piece_type] or not b.is_attacked_by(enemy, sq))):
            targets.append(sq)
    if len(targets) < 2:
        return None
    for m in b.legal_moves:  # a fork the forking piece can simply be captured out of isn't a fork
        if m.to_square == move.to_square and capture_gain(b, m) > 0:
            return None
    return mover, targets


def _list(board, squares):
    names = [f"{_name(board.piece_at(s))} on {_sq(s)}" for s in squares[:3]]
    return " and ".join(names) if len(names) < 3 else f"{names[0]}, {names[1]} and {names[2]}"


def _hang(board, move):
    """After `move`, is something of the mover's left capturable at a profit? Returns details or None."""
    after = board.copy(stack=False)
    after.push(move)
    if after.is_game_over():
        return None
    cap = best_capture(after)
    if not cap:
        return None
    gain, m = cap
    taken = board.piece_at(move.to_square) if board.is_capture(move) else None
    won = VALUE[taken.piece_type] if taken else 0
    net = gain - won if m.to_square == move.to_square else gain  # a trade this move started isn't a blunder
    if net < 90:
        return None
    mover_color = board.turn
    return {"victim": after.piece_at(m.to_square) or chess.Piece(chess.PAWN, mover_color),
            "attacker": after.piece_at(m.from_square), "square": m.to_square,
            "free": not after.is_attacked_by(mover_color, m.to_square), "moved": m.to_square == move.to_square}


def _allows_mate(board, move):
    """SAN of a checkmating reply to `move`, or None."""
    after = board.copy(stack=False)
    after.push(move)
    for m in after.legal_moves:
        t = after.copy(stack=False)
        t.push(m)
        if t.is_checkmate():
            return after.san(m)
    return None


def warning(board, move):
    """Short heads-up shown before a move is played (the optional safety check), or ''."""
    mate = _allows_mate(board, move)
    if mate:
        return f"Careful: that allows checkmate ({mate})."
    h = _hang(board, move)
    if h:
        tail = "for free" if h["free"] else "and come out ahead"
        where = "moving it there" if h["moved"] else "leaving it there"
        return (f"Careful: {where} lets their {_name(h['attacker'])} take your {_name(h['victim'])} on "
                f"{_sq(h['square'])} {tail}.")
    return ""


def explain(board, move, best_uci, cls, mine=True):
    """One or two short sentences on why `move` (played from `board`) was a mistake, or '' if unsure.

    `mine` says whether the mover is the user ("Your queen") or the bot ("The bot's queen").
    """
    own, them = ("Your", "their") if mine else ("The bot's", "your")
    san_best = None
    best = None
    if best_uci:
        best = chess.Move.from_uci(best_uci)
        if best in board.legal_moves:
            san_best = board.san(best)
        else:
            best = None
    reasons = []
    mover_color = board.turn
    piece = board.piece_at(move.from_square)

    # 1. Missed checkmate
    if best:
        t = board.copy(stack=False)
        t.push(best)
        if t.is_checkmate():
            reasons.append(f"Missed checkmate: {san_best} ends the game.")

    after = board.copy(stack=False)
    after.push(move)

    # 2. Allowed checkmate, or pieces left capturable
    mate = _allows_mate(board, move)
    if mate:
        reasons.append(f"Allows checkmate: {mate}.")
    h = None if mate else _hang(board, move)
    if h:
        victim, attacker, square = h["victim"], h["attacker"], h["square"]
        tail = " for free" if h["free"] else " and win material even after a recapture"
        tip = " - check what a move attacks and what it leaves unprotected." if mine else "."
        if h["moved"]:
            reasons.append(f"Moving the {_name(victim)} to {_sq(square)} lets {them} {_name(attacker)} take it{tail}.")
        else:
            reasons.append(f"{own} {_name(victim)} on {_sq(square)} can be captured by {them} "
                           f"{_name(attacker)}{tail}{tip}")

    # 3. Allowed a fork
    if len(reasons) < 2 and not after.is_game_over():
        for m in after.legal_moves:
            f = forks(after, m)
            if f:
                reasons.append(f"Allows a fork: {after.san(m)} attacks {own.lower() if mine else own} {_list(after, f[1])} at once.")
                break

    # 4. Missed a free capture
    if len(reasons) < 2 and best and board.is_capture(best) and not board.is_capture(move):
        g = capture_gain(board, best)
        if g >= 90:
            victim = board.piece_at(best.to_square)
            what = _name(victim) if victim else "pawn"
            reasons.append(f"Missed winning {them} {what} on {_sq(best.to_square)} with {san_best}.")

    # 5. Missed a fork
    if len(reasons) < 2 and best:
        f = forks(board, best)
        if f:
            reasons.append(f"{san_best} would have forked {them} {_list(board, f[1])}.")

    # 6. Opening habits
    if len(reasons) < 2 and board.fullmove_number <= 8 and piece and piece.piece_type == chess.QUEEN:
        reasons.append("Bringing the queen out early lets them chase it with developing moves - develop knights and "
                       "bishops first.")

    if not reasons and san_best:
        reasons.append(f"{san_best} was stronger here.")
    return " ".join(reasons[:2])
