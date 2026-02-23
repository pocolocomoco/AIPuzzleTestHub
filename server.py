#!/usr/bin/env python3
"""
Pulse Grid — An interactive discovery puzzle for AI agents.

The agent must discover hidden rules by clicking cells and observing
how the grid changes. No instructions are provided.

Run:  python server.py [--port PORT]
Then open http://localhost:8080 in your browser.
"""

import http.server
import json
import random
import uuid
import os
import sys
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Game Logic
# ---------------------------------------------------------------------------

DIFFICULTY_CONFIG = {
    "easy":      {"grid_size": 3, "num_colors": 3, "scramble": (3, 5),  "levels": 5},
    "medium":    {"grid_size": 4, "num_colors": 4, "scramble": (6, 9),  "levels": 8},
    "hard":      {"grid_size": 5, "num_colors": 4, "scramble": (9, 14), "levels": 12},
    "very_hard": {"grid_size": 6, "num_colors": 5, "scramble": (13, 20), "levels": 20},
}

# Pulse patterns keyed by cell value.
# Each entry is a list of (dr, dc) offsets *in addition to* the clicked cell itself.
PULSE_PATTERNS = {
    0: [],                                                  # Self only
    1: [(-1, 0), (1, 0), (0, -1), (0, 1)],                 # Orthogonal (cross / plus)
    2: [(-1, -1), (-1, 1), (1, -1), (1, 1)],               # Diagonal   (X)
    3: [(-1, -1), (-1, 0), (-1, 1),                          # All 8 neighbours (block)
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)],
    4: [(-2, 0), (-1, 0), (1, 0), (2, 0),                   # Extended cross (distance-2)
        (0, -2), (0, -1), (0, 1), (0, 2)],
}


class PulseGridGame:
    """Single game session with level progression."""

    def __init__(self, difficulty="easy", seed=None):
        self.difficulty = difficulty
        self.level = 1
        self.total_score = 0
        self.rng = random.Random(seed)
        self._generate_level()

    # -- public API ----------------------------------------------------------

    def click(self, row, col):
        """Perform a click action. Returns updated state dict."""
        if self.solved:
            return self.get_state()
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        if not (0 <= row < cfg["grid_size"] and 0 <= col < cfg["grid_size"]):
            return self.get_state()

        self.last_affected = self._apply_click(row, col)
        self.moves += 1
        self._check_solved()
        return self.get_state()

    def reset_level(self):
        """Reset the current level to its initial state."""
        self.grid = [row[:] for row in self.initial_grid]
        self.moves = 0
        self.solved = False
        self.last_affected = []
        return self.get_state()

    def next_level(self):
        """Advance to the next level (only valid when solved)."""
        if not self.solved:
            return self.get_state()
        self.level += 1
        self._generate_level()
        return self.get_state()

    def new_game(self, difficulty=None):
        """Start a brand-new game, optionally changing difficulty."""
        if difficulty and difficulty in DIFFICULTY_CONFIG:
            self.difficulty = difficulty
        self.level = 1
        self.total_score = 0
        self._generate_level()
        return self.get_state()

    def get_state(self):
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        return {
            "grid": [row[:] for row in self.grid],
            "grid_size": cfg["grid_size"],
            "num_colors": cfg["num_colors"],
            "level": self.level,
            "max_levels": cfg["levels"],
            "total_score": self.total_score,
            "moves": self.moves,
            "par": self.par,
            "difficulty": self.difficulty,
            "goal_color": self.goal_color,
            "solved": self.solved,
            "game_complete": self.level > cfg["levels"] and self.solved,
            "last_affected": self.last_affected,
        }

    # -- internal ------------------------------------------------------------

    def _generate_level(self):
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        gs = cfg["grid_size"]
        nc = cfg["num_colors"]
        self.goal_color = 0
        self.grid = [[0] * gs for _ in range(gs)]

        lo, hi = cfg["scramble"]
        extra = min(self.level - 1, 8)
        num_scramble = self.rng.randint(lo + extra, hi + extra)
        self.par = num_scramble

        for _ in range(num_scramble):
            r = self.rng.randint(0, gs - 1)
            c = self.rng.randint(0, gs - 1)
            self._apply_click(r, c)

        # Ensure puzzle isn't already solved
        if all(self.grid[r][c] == self.goal_color for r in range(gs) for c in range(gs)):
            # Force at least one click
            r, c = self.rng.randint(0, gs - 1), self.rng.randint(0, gs - 1)
            self._apply_click(r, c)
            self.par += 1

        self.initial_grid = [row[:] for row in self.grid]
        self.moves = 0
        self.solved = False
        self.last_affected = []

    def _apply_click(self, row, col):
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        gs = cfg["grid_size"]
        nc = cfg["num_colors"]
        value = self.grid[row][col]
        pattern = PULSE_PATTERNS.get(value, [])
        affected = [(row, col)]
        for dr, dc in pattern:
            nr, nc2 = row + dr, col + dc
            if 0 <= nr < gs and 0 <= nc2 < gs:
                affected.append((nr, nc2))
        for r, c in affected:
            self.grid[r][c] = (self.grid[r][c] + 1) % nc
        return affected

    def _check_solved(self):
        cfg = DIFFICULTY_CONFIG[self.difficulty]
        gs = cfg["grid_size"]
        if all(self.grid[r][c] == self.goal_color for r in range(gs) for c in range(gs)):
            self.solved = True
            score = max(100 - max(0, self.moves - self.par) * 10, 10)
            self.total_score += score


# ---------------------------------------------------------------------------
# Session Store
# ---------------------------------------------------------------------------

sessions: dict[str, PulseGridGame] = {}


def get_or_create_session(sid=None, difficulty="easy"):
    if sid and sid in sessions:
        return sid, sessions[sid]
    new_id = uuid.uuid4().hex[:12]
    sessions[new_id] = PulseGridGame(difficulty=difficulty)
    return new_id, sessions[new_id]


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))


class RequestHandler(http.server.BaseHTTPRequestHandler):
    """Handles both static file serving and the JSON API."""

    def log_message(self, fmt, *args):
        # Quieter logging
        sys.stderr.write(f"[server] {fmt % args}\n")

    # -- routing -------------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._serve_file("index.html", "text/html")
        elif path == "/api/state":
            self._handle_get_state(parsed)
        elif path == "/api/info":
            self._json_response({"difficulties": list(DIFFICULTY_CONFIG.keys()),
                                 "configs": DIFFICULTY_CONFIG,
                                 "pulse_patterns": {str(k): v for k, v in PULSE_PATTERNS.items()}})
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        if path == "/api/new_game":
            self._handle_new_game(body)
        elif path == "/api/click":
            self._handle_click(body)
        elif path == "/api/reset":
            self._handle_reset(body)
        elif path == "/api/next_level":
            self._handle_next_level(body)
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -- API handlers --------------------------------------------------------

    def _handle_get_state(self, parsed):
        qs = parse_qs(parsed.query)
        sid = qs.get("session_id", [None])[0]
        if not sid or sid not in sessions:
            self._json_response({"error": "invalid session_id"}, 400)
            return
        game = sessions[sid]
        self._json_response({"session_id": sid, **game.get_state()})

    def _handle_new_game(self, body):
        difficulty = body.get("difficulty", "easy")
        if difficulty not in DIFFICULTY_CONFIG:
            self._json_response({"error": f"invalid difficulty, choose from {list(DIFFICULTY_CONFIG.keys())}"}, 400)
            return
        sid = body.get("session_id")
        if sid and sid in sessions:
            game = sessions[sid]
            state = game.new_game(difficulty)
            self._json_response({"session_id": sid, **state})
        else:
            sid, game = get_or_create_session(difficulty=difficulty)
            self._json_response({"session_id": sid, **game.get_state()})

    def _handle_click(self, body):
        sid = body.get("session_id")
        if not sid or sid not in sessions:
            self._json_response({"error": "invalid session_id"}, 400)
            return
        row = body.get("row")
        col = body.get("col")
        if row is None or col is None:
            self._json_response({"error": "row and col required"}, 400)
            return
        game = sessions[sid]
        state = game.click(int(row), int(col))
        self._json_response({"session_id": sid, **state})

    def _handle_reset(self, body):
        sid = body.get("session_id")
        if not sid or sid not in sessions:
            self._json_response({"error": "invalid session_id"}, 400)
            return
        state = sessions[sid].reset_level()
        self._json_response({"session_id": sid, **state})

    def _handle_next_level(self, body):
        sid = body.get("session_id")
        if not sid or sid not in sessions:
            self._json_response({"error": "invalid session_id"}, 400)
            return
        state = sessions[sid].next_level()
        self._json_response({"session_id": sid, **state})

    # -- helpers -------------------------------------------------------------

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _json_response(self, data, code=200):
        payload = json.dumps(data).encode()
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _serve_file(self, filename, content_type):
        filepath = os.path.join(STATIC_DIR, filename)
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = 8080
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])

    server = http.server.HTTPServer(("0.0.0.0", port), RequestHandler)
    print(f"Pulse Grid server running on http://localhost:{port}")
    print("API endpoints:")
    print(f"  POST /api/new_game   — Start a new game (body: {{\"difficulty\": \"easy\"}})")
    print(f"  GET  /api/state      — Get current state (?session_id=...)")
    print(f"  POST /api/click      — Click a cell (body: {{\"session_id\": ..., \"row\": r, \"col\": c}})")
    print(f"  POST /api/reset      — Reset current level")
    print(f"  POST /api/next_level — Advance to next level")
    print(f"  GET  /api/info       — Game configuration info")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
