/* Game review for the published site, where the Python helper isn't running.

A browser port of server.build_review, analysis.grade and coach.explain: Stockfish evaluations in, the same
review object out. Only the published copy loads this; the desktop app keeps using the Python versions.
*/
import { Chess } from "./vendor/chess.js";

const MATE = 100000, EVAL_CLIP = 1000, CPL_CAP = 300;
const VALUE = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };
const NAME = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };
// python-chess's square order (a1, b1, … h8), so lists of squares come out in the same order as the helper's
const SQUARES = [];
for (let r = 1; r <= 8; r++) for (const f of "abcdefgh") SQUARES.push(f + r);

/* ---------- board helpers (python-chess equivalents) ---------- */
const copy = b => new Chess(b.fen());
const legal = b => b.moves({ verbose: true });
const isCapture = m => m.flags.includes("c") || m.flags.includes("e");
const uciOf = m => m.from + m.to + (m.promotion || "");
const toMove = uci => ({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
const push = (b, m) => { b.move({ from: m.from, to: m.to, promotion: m.promotion }); return b; };
const other = c => (c === "w" ? "b" : "w");
// python-chess's is_game_over(): mate, stalemate or dead position (no claimable draws)
const gameOver = b => b.isCheckmate() || b.isStalemate() || b.isInsufficientMaterial();
// squares the piece on `sq` attacks
const attacks = (b, sq) => { const p = b.get(sq); return p ? SQUARES.filter(t => t !== sq && b.attackers(t, p.color).includes(sq)) : []; };

/* ---------- replay ---------- */
export function replay(moves) {
  const b = new Chess(), fens = [], san = [];
  for (const u of moves) { fens.push(b.fen()); san.push(push(b, toMove(u)) && b.history().slice(-1)[0]); }
  return { fens, san, board: b };
}

/* ---------- grading (analysis.py) ---------- */
const winPct = cp => 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
const clip = v => Math.max(-EVAL_CLIP, Math.min(EVAL_CLIP, v));
const round1 = x => Math.round(x * 10) / 10;

function harmonicMean(accs) {
  const vals = accs.map(a => Math.max(1, a));
  return vals.length ? vals.length / vals.reduce((s, a) => s + 1 / a, 0) : null;
}
function gameAccuracy(accs, weights) {
  if (!accs.length) return null;
  const weighted = accs.reduce((s, a, i) => s + a * weights[i], 0) / weights.reduce((s, w) => s + w, 0);
  return (weighted + harmonicMean(accs)) / 2;
}
function volatilityWeights(evals) {
  const wins = evals.map(e => winPct(clip(e))), half = Math.max(1, Math.min(4, Math.floor(wins.length / 20))), out = [];
  for (let i = 0; i < wins.length - 1; i++) {
    const w = wins.slice(Math.max(0, i - half), i + half + 2), m = w.reduce((s, x) => s + x, 0) / w.length;
    out.push(Math.max(0.5, Math.min(12, Math.sqrt(w.reduce((s, x) => s + (x - m) ** 2, 0) / w.length))));
  }
  return out;
}
const classify = d => d <= 2 ? "best" : d <= 5 ? "good" : d <= 10 ? "inaccuracy" : d <= 20 ? "mistake" : "blunder";

export function grade(moves, positions) {
  const out = { moves: [], evals: positions.map(p => p[0]) };
  moves.forEach((uci, i) => {
    let before = clip(positions[i][0]), after = clip(positions[i + 1][0]);
    if (i % 2) { before = -before; after = -after; }
    const cpl = Math.max(0, before - after), drop = Math.max(0, winPct(before) - winPct(after));
    const acc = Math.max(0, Math.min(100, 103.1668 * Math.exp(-0.04354 * drop) - 3.1669)), cls = classify(drop), best = positions[i][1];
    out.moves.push({ cpl, drop: round1(drop), acc: round1(acc), cls,
      best: best && best !== uci && ["inaccuracy", "mistake", "blunder"].includes(cls) ? best : null });
  });
  const vol = volatilityWeights(out.evals);
  [["white", 0], ["black", 1]].forEach(([name, parity]) => {
    const mine = out.moves.filter((m, i) => i % 2 === parity);
    if (!mine.length) return;
    const count = c => mine.filter(m => m.cls === c).length;
    out[name] = { acpl: mine.reduce((s, m) => s + Math.min(m.cpl, CPL_CAP), 0) / mine.length,
      acc: gameAccuracy(mine.map(m => m.acc), vol.filter((w, i) => i % 2 === parity)), n: mine.length,
      inaccuracy: count("inaccuracy"), mistake: count("mistake"), blunder: count("blunder") };
  });
  return out;
}

/* ---------- explanations (coach.py) ---------- */
function captureGain(board, m) {
  const victim = board.get(m.to), attacker = board.get(m.from);
  let gain = victim ? VALUE[victim.type] : 100;   // en passant takes a pawn
  const after = push(copy(board), m);
  if (after.isAttacked(m.to, after.turn())) gain -= VALUE[attacker.type];
  return gain;
}
function bestCapture(board) {
  let best = null;
  for (const m of legal(board)) if (isCapture(m)) { const g = captureGain(board, m); if (!best || g > best[0]) best = [g, m]; }
  return best;
}
function forks(board, move) {
  const b = push(copy(board), move), mover = b.get(move.to);
  if (!mover) return null;
  const enemy = b.turn(), targets = [];
  for (const sq of attacks(b, move.to)) {
    const t = b.get(sq);
    if (!t || t.color !== enemy) continue;
    if (t.type === "k" || (VALUE[t.type] >= 300 && (VALUE[t.type] > VALUE[mover.type] || !b.isAttacked(sq, enemy)))) targets.push(sq);
  }
  if (targets.length < 2) return null;
  for (const m of legal(b)) if (m.to === move.to && captureGain(b, m) > 0) return null;   // the forker can just be taken
  return [mover, targets];
}
function list(board, squares) {
  const names = squares.slice(0, 3).map(s => `${NAME[board.get(s).type]} on ${s}`);
  return names.length < 3 ? names.join(" and ") : `${names[0]}, ${names[1]} and ${names[2]}`;
}
function hang(board, move) {
  const after = push(copy(board), move);
  if (gameOver(after)) return null;
  const cap = bestCapture(after);
  if (!cap) return null;
  const [gain, m] = cap, taken = isCapture(move) ? board.get(move.to) : null, won = taken ? VALUE[taken.type] : 0;
  const net = m.to === move.to ? gain - won : gain;   // a trade this move started isn't a blunder
  if (net < 90) return null;
  const moverColor = board.turn();
  return { victim: after.get(m.to) || { type: "p", color: moverColor }, attacker: after.get(m.from), square: m.to,
    free: !after.isAttacked(m.to, moverColor), moved: m.to === move.to };
}
function allowsMate(board, move) {
  const after = push(copy(board), move);
  for (const m of legal(after)) if (push(copy(after), m).isCheckmate()) return m.san;
  return null;
}

export function explain(board, move, bestUci, cls, mine = true, otherName = "Your opponent's") {
  const [own, them] = mine ? ["Your", "their"] : [otherName, "your"], reasons = [];
  let best = null, sanBest = null;
  if (bestUci) { best = legal(board).find(m => uciOf(m) === bestUci) || null; if (best) sanBest = best.san; }
  const piece = board.get(move.from);

  if (best && push(copy(board), best).isCheckmate()) reasons.push(`Missed checkmate: ${sanBest} ends the game.`);

  const after = push(copy(board), move), mate = allowsMate(board, move);
  if (mate) reasons.push(`Allows checkmate: ${mate}.`);
  const h = mate ? null : hang(board, move);
  if (h) {
    const tail = h.free ? " for free" : " and win material even after a recapture", tip = mine ? " - check what a move attacks and what it leaves unprotected." : ".";
    if (h.moved) reasons.push(`Moving the ${NAME[h.victim.type]} to ${h.square} lets ${them} ${NAME[h.attacker.type]} take it${tail}.`);
    else reasons.push(`${own} ${NAME[h.victim.type]} on ${h.square} can be captured by ${them} ${NAME[h.attacker.type]}${tail}${tip}`);
  }

  if (reasons.length < 2 && !gameOver(after)) {
    for (const m of legal(after)) {
      const f = forks(after, m);
      if (f) { reasons.push(`Allows a fork: ${m.san} attacks ${own[0].toLowerCase() + own.slice(1)} ${list(after, f[1])} at once.`); break; }
    }
  }

  if (reasons.length < 2 && best && isCapture(best) && !isCapture(move)) {
    if (captureGain(board, best) >= 90) { const v = board.get(best.to); reasons.push(`Missed winning ${them} ${v ? NAME[v.type] : "pawn"} on ${best.to} with ${sanBest}.`); }
  }

  if (reasons.length < 2 && best) { const f = forks(board, best); if (f) reasons.push(`${sanBest} would have forked ${them} ${list(board, f[1])}.`); }

  const fullmove = +board.fen().split(" ")[5];
  if (reasons.length < 2 && fullmove <= 8 && piece && piece.type === "q")
    reasons.push("Bringing the queen out early lets them chase it with developing moves - develop knights and bishops first.");

  if (!reasons.length && sanBest) reasons.push(`${sanBest} was stronger here.`);
  return reasons.slice(0, 2).join(" ");
}

/* ---------- the review (server.build_review) ---------- */
// `game` is {id, color, moves, san}; `evals` is one {cp (white POV), best} per position before each move
export function buildReview(game, evals) {
  const { moves, color } = game;
  if (evals.length !== moves.length) throw new Error("evaluation count doesn't match the game");
  const end = replay(moves).board;
  const final = end.isCheckmate() ? (end.turn() === "w" ? -MATE : MATE) : gameOver(end) ? 0 : null;
  const positions = evals.map(e => [Math.trunc(e.cp), e.best || null]).concat([[final ?? Math.trunc(evals[evals.length - 1].cp), null]]);
  const result = grade(moves, positions), mineWhite = color === "white", flagged = [], board = new Chess();
  moves.forEach((uci, i) => {
    const mv = result.moves[i], mine = (i % 2 === 0) === mineWhite, move = legal(board).find(m => uciOf(m) === uci);
    if (["inaccuracy", "mistake", "blunder"].includes(mv.cls)) {
      const bm = mv.best && legal(board).find(m => uciOf(m) === mv.best);
      let why = "";
      try { why = explain(board, move, mv.best, mv.cls, mine, "Your opponent's"); } catch (e) { /* an explanation is a nicety */ }
      flagged.push({ ply: i, num: Math.floor(i / 2) + 1, white: i % 2 === 0, san: move.san, cls: mv.cls, drop: mv.drop,
        best_san: bm ? bm.san : null, best: mv.best, why, mine });
    }
    push(board, move);
  });
  const side = mineWhite ? "white" : "black";
  return { id: game.id, color, me: result[side], opp: result[mineWhite ? "black" : "white"],
    evals: positions.map(p => clip(p[0])), flagged, at: Math.floor(Date.now() / 1000), batch: false, new_puzzles: 0 };
}
