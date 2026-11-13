/* Missed-mate practice for the published site: a browser port of mates.mating_moves, server.mate_move and
server.position_info. Only the published copy loads this; the desktop app uses the Python versions.
*/
import { Chess } from "./vendor/chess.js";

const toMove = uci => ({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
const uciOf = m => m.from + m.to + (m.promotion || "");
// python-chess's is_game_over(): mate, stalemate or dead position (no claimable draws)
const gameOver = b => b.isCheckmate() || b.isStalemate() || b.isInsufficientMaterial();

function canMate(b, n) {
  for (const m of b.moves({ verbose: true })) {
    b.move(m);
    try {
      if (b.isCheckmate()) return true;
      if (n > 1 && !gameOver(b) && allRepliesLose(b, n - 1)) return true;
    } finally { b.undo(); }
  }
  return false;
}
function allRepliesLose(b, n) {
  for (const r of b.moves({ verbose: true })) {
    b.move(r);
    try { if (gameOver(b) || !canMate(b, n)) return false; } finally { b.undo(); }
  }
  return true;
}
// moves that force mate within n moves for the side to move, as UCI strings
export function matingMoves(b, n) {
  const out = [];
  for (const m of b.moves({ verbose: true })) {
    b.move(m);
    try {
      if (b.isCheckmate()) out.push(uciOf(m));
      else if (n > 1 && !gameOver(b)) {
        if (n >= 3 && !b.isCheck() && b.moves().length > 3) continue;
        if (allRepliesLose(b, n - 1)) out.push(uciOf(m));
      }
    } finally { b.undo(); }
  }
  return out;
}

export function positionInfo(fen, ucis) {
  const b = new Chess(fen), turn = () => (b.turn() === "w" ? "white" : "black");
  const info = (last, san) => ({ fen: b.fen(), turn: turn(), legal: b.moves({ verbose: true }).map(uciOf), last, san,
    over: gameOver(b), mate: b.isCheckmate(), check: b.isCheck() });
  const start = { turn: turn(), fullmove: +fen.split(" ")[5] }, out = [info(null, null)];
  for (const u of ucis) {
    let m;
    try { m = b.move(toMove(u)); } catch (e) { throw new Error(`illegal move ${u}`); }
    out.push(info(u, m.san));
  }
  return { start, positions: out };
}

// judge a move for a 'mate in n' position; if it's right, play the opponent's most stubborn reply
export function mateMove(fen, uci, n) {
  const b = new Chess(fen), good = matingMoves(b, n);
  if (!good.includes(uci)) return { ok: false, best: good.slice(0, 4).map(u => new Chess(fen).move(toMove(u)).san) };
  b.move(toMove(uci));
  if (b.isCheckmate()) return { ok: true, done: true, positions: positionInfo(fen, [uci]) };
  let best = null, bestLen = -1;
  for (const r of b.moves({ verbose: true })) {   // the reply that keeps the game going longest
    b.move(r);
    let k = n;
    if (b.isCheckmate()) k = 0;
    else for (let j = 1; j < n; j++) if (matingMoves(b, j).length) { k = j; break; }
    b.undo();
    if (k > bestLen) { best = r; bestLen = k; }
  }
  return { ok: true, done: false, reply: uciOf(best), n_left: Math.max(1, n - 1), positions: positionInfo(fen, [uci, uciOf(best)]) };
}

/* spaced repetition, as training.py: right on the first try moves a puzzle up a box, anything else resets it */
export const INTERVAL_DAYS = [0, 1, 2, 4, 7];
export const today = () => new Date().toLocaleDateString("en-CA");   // YYYY-MM-DD, local
export function record(st, correct) {
  st.tries++;
  if (correct) { st.solved++; st.box++; } else st.box = 0;
  if (st.box < INTERVAL_DAYS.length) { const d = new Date(today() + "T12:00:00"); d.setDate(d.getDate() + INTERVAL_DAYS[st.box]); st.due = d.toLocaleDateString("en-CA"); }
  return st;
}
