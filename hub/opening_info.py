"""Plain-English descriptions for the openings the hub lists. Matched by the longest name prefix, so
'Bishops Opening Berlin' uses its own entry while 'Bishops Opening 2...Nc6' falls back to 'Bishops Opening'."""

INFO = {
    "kings pawn opening": "Any game that starts 1.e4 and hasn't reached a more specific named line yet. White takes the centre and opens lines for the queen and bishop. It's a big bucket: lots of different games end up here.",
    "queens pawn opening": "Any game that starts 1.d4 before reaching a more specific line. White claims the centre with the d-pawn; games tend to be slower and more strategic than after 1.e4.",
    "alekhines defense": "1.e4 Nf6. Black invites White's pawns forward (2.e5 Nd5 3.d4 d6) to attack them later. Tricky for both sides; White can overextend, but the pawns also cramp Black if they're not challenged.",
    "four knights game": "1.e4 e5 2.Nf3 Nc6 3.Nc3 Nf6. Both sides develop both knights. Solid and symmetrical, usually calm and rich in plain principles: develop, castle, fight for the centre.",
    "nimzowitsch defense": "1.e4 Nc6. Black develops a knight first and challenges the centre later. Unusual, so opponents often don't know what to do, but White gets a free hand in the centre.",
    "englund gambit": "1.d4 e5. Black sacrifices a pawn for quick development and a few traps (like 2.dxe5 Nc6 3.Nf3 Qe7). Fun against careless opponents, but accurate play by White just wins a pawn.",
    "bishops opening berlin": "1.e4 e5 2.Bc4 Nf6. White develops the bishop before the knight, and Black answers by developing a knight with an attack on e4. White usually defends the pawn with 3.d3 or 3.Nc3, or plays 3.d4 to open the centre; moves like 3.Qf3 bring the queen out early and give Black time to develop.",
    "bishops opening": "1.e4 e5 2.Bc4. White develops the bishop first, eyeing f7, before choosing where the knights go. Flexible: it often becomes an Italian Game or a Vienna-style position.",
    "scotch game": "1.e4 e5 2.Nf3 Nc6 3.d4. White opens the centre at once. Open, tactical positions with quick development for both sides.",
    "scandinavian defense": "1.e4 d5. Black hits the centre immediately. After 2.exd5 Qxd5 the queen comes out early, so White gains time with 3.Nc3.",
    "pirc defense": "1.e4 d6 with ...Nf6 and ...g6. Black lets White build a big centre, then undermines it with the fianchettoed bishop. Flexible, but you need to know the plans.",
    "petrovs defense": "1.e4 e5 2.Nf3 Nf6. Black counter-attacks e4 rather than defending e5. Very solid. One trap to know: after 3.Nxe5, don't play ...Nxe4 - first 3...d6.",
    "philidor defense": "1.e4 e5 2.Nf3 d6. Black protects e5 solidly but passively; cramped but hard to crack. Often leads to quiet positions.",
    "italian game": "1.e4 e5 2.Nf3 Nc6 3.Bc4. Natural development with the bishop aimed at f7. A classic for learning opening principles.",
    "ruy lopez": "1.e4 e5 2.Nf3 Nc6 3.Bb5. White pressures the knight that guards e5. One of the oldest and richest openings; the main line of serious chess.",
    "sicilian defense": "1.e4 c5. Black fights for the centre asymmetrically. Sharp and double-edged; the most popular reply to 1.e4 among strong players.",
    "french defense": "1.e4 e6. Solid but cramped: Black plans ...d5 and counterplay against White's centre. The light-squared bishop can be a problem piece.",
    "caro-kann defense": "1.e4 c6. A solid reply that prepares ...d5 without blocking the bishop on c8. Safe and sound.",
    "london system": "1.d4 with Bf4, e3, Nf3. A system for White that works against almost anything, so there's very little theory to learn.",
    "vienna game": "1.e4 e5 2.Nc3. A flexible move that prepares f4 or Bc4. Leads to open, lively games.",
    "kings gambit": "1.e4 e5 2.f4. White offers a pawn for open lines against Black's king. Sharp and risky for both sides.",
    "danish gambit": "1.e4 e5 2.d4 exd4 3.c3. White sacrifices pawns for quick development and attacking chances. Black can just take them, so you must attack accurately.",
    "queens gambit": "1.d4 d5 2.c4. White offers a pawn to gain the centre; if Black takes it, White gets rapid development and the pawn back.",
    "indian defense": "1.d4 Nf6. Black controls the centre with pieces first instead of pawns. A family of flexible openings.",
    "dutch defense": "1.d4 f5. Black fights for the e4 square from the start. Aggressive, but it weakens the king's side.",
    "ponziani opening": "1.e4 e5 2.Nf3 Nc6 3.c3. White prepares d4 for a big centre, similar to structures from the Italian Game.",
    "center game": "1.e4 e5 2.d4 exd4 3.Qxd4. White takes the centre early with the queen, which can be chased away by ...Nc6.",
    "latvian gambit": "1.e4 e5 2.Nf3 f5. A risky counter-gambit that weakens Black's king. Sharp and trappy, but unsound if White plays well.",
    "hungarian defense": "1.e4 e5 2.Nf3 Nc6 3.Bc4 Be7. A quiet, solid reply to the Italian - a bit passive.",
    "elephant gambit": "1.e4 e5 2.Nf3 d5. Black sacrifices a pawn to challenge the centre. Playable at club level but not reliable against good play.",
    "owens defense": "1.e4 b6. Black prepares to fianchetto the bishop to hit e4 and the long diagonal. Unusual and slightly slow.",
    "modern defense": "1.e4 g6. Black develops the bishop on g7 and lets White build a centre, planning to attack it later.",
}


def describe(name):
    """Description for an opening group name ('Bishops Opening Berlin'), longest matching prefix wins."""
    key = (name or "").lower().replace("'", "")
    best = max((k for k in INFO if key.startswith(k)), key=len, default=None)
    return INFO.get(best, "")
