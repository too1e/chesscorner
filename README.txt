CHESS CORNER - dashboard + helper
==================================

First time on this computer
  1. Install Python 3.10 or newer from https://www.python.org/downloads/
  2. Unzip this folder somewhere normal (Documents is fine) - don't run it from inside the zip.
  3. Double-click "Start Chess Corner.command". The first run installs the "chess" library, so it needs internet.
  4. Your browser opens http://127.0.0.1:8777 - that's the dashboard.

Every day after that
  Double-click "Start Chess Corner.command" again (it does nothing if the helper is already running).
  If the page says it can't connect, the helper isn't running - same fix.

Notes
  * This is its own copy. Games, reviews and puzzle progress you add here don't merge back with the other computer.
  * "Sync chess.com" fetches new games (public data, no password). The username is set in hub/stats.py (USERNAME).
  * "Save offline copy" makes a single HTML file for phones.
  * Stockfish runs inside your browser (hub/engine) - nothing else to install.
  * On Linux (or without the launcher), run:  python3 hub/server.py  and open http://127.0.0.1:8777
