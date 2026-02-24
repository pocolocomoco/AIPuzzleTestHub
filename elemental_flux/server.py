"""
Elemental Flux - Web Server & API

Provides REST API for AI agent interaction and serves the HTML frontend.
Run with: python server.py [--port PORT]
"""

import json
import os
import argparse
from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS
from game_engine import ElementalFluxGame, DIFFICULTY_CONFIG

app = Flask(__name__)
CORS(app)

# In-memory game storage
games: dict[str, ElementalFluxGame] = {}


@app.route('/')
def index():
    """Serve the standalone HTML game."""
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    return send_file(html_path)


# ─── API Endpoints ───────────────────────────────────────────────────────────


@app.route('/api/info', methods=['GET'])
def api_info():
    """Get information about the game and available configurations."""
    return jsonify({
        'name': 'Elemental Flux',
        'description': (
            'A grid-based discovery puzzle. Each cell has a shape (node type) '
            'and a color (phase). Clicking a cell advances its phase and propagates '
            'to neighboring cells based on rules you must discover. '
            'Goal: make all cells the same target color.'
        ),
        'difficulties': {
            name: {
                'grid_size': cfg['grid_size'],
                'num_phases': cfg['num_phases'],
                'num_node_types': cfg['num_node_types'],
                'has_locked_cells': cfg['locked_cells'],
                'levels': cfg['levels'],
            }
            for name, cfg in DIFFICULTY_CONFIG.items()
        },
        'actions': {
            'click': {
                'description': 'Click a cell to advance its phase and trigger propagation',
                'parameters': {'row': 'int (0-indexed)', 'col': 'int (0-indexed)'},
            },
            'reset': {'description': 'Reset puzzle to initial state'},
            'next_level': {'description': 'Advance to next level (after solving)'},
        },
        'endpoints': {
            'POST /api/games': 'Create a new game',
            'GET /api/games/<id>': 'Get game state',
            'POST /api/games/<id>/click': 'Click a cell',
            'POST /api/games/<id>/reset': 'Reset puzzle',
            'POST /api/games/<id>/next_level': 'Go to next level',
        }
    })


@app.route('/api/games', methods=['POST'])
def create_game():
    """Create a new game session."""
    data = request.get_json(force=True, silent=True) or {}
    difficulty = data.get('difficulty', 'easy')
    level = data.get('level', 1)
    seed = data.get('seed', None)

    if difficulty not in DIFFICULTY_CONFIG:
        return jsonify({
            'error': f'Invalid difficulty. Choose from: {list(DIFFICULTY_CONFIG.keys())}'
        }), 400

    try:
        game = ElementalFluxGame(difficulty=difficulty, level=level, seed=seed)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    games[game.game_id] = game

    return jsonify({
        'game_id': game.game_id,
        'state': game.get_state(),
        'message': (
            f'New {difficulty} game created (level {level}). '
            f'Grid: {game.grid_size}x{game.grid_size}, '
            f'{game.num_phases} phases, {game.num_node_types} node types. '
            f'Click cells to discover the rules. Goal: make all cells phase 0 (Red).'
        )
    }), 201


@app.route('/api/games/<game_id>', methods=['GET'])
def get_game(game_id):
    """Get current game state."""
    game = games.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    return jsonify({'state': game.get_state()})


@app.route('/api/games/<game_id>/click', methods=['POST'])
def click_cell(game_id):
    """Click a cell at the given row and column."""
    game = games.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    data = request.get_json(force=True, silent=True) or {}
    row = data.get('row')
    col = data.get('col')

    if row is None or col is None:
        return jsonify({'error': 'Must provide row and col'}), 400

    try:
        row = int(row)
        col = int(col)
    except (TypeError, ValueError):
        return jsonify({'error': 'row and col must be integers'}), 400

    result = game.click(row, col)
    return jsonify(result)


@app.route('/api/games/<game_id>/reset', methods=['POST'])
def reset_game(game_id):
    """Reset puzzle to initial scrambled state."""
    game = games.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    state = game.reset()
    return jsonify({
        'state': state,
        'message': 'Puzzle reset to initial state.'
    })


@app.route('/api/games/<game_id>/next_level', methods=['POST'])
def next_level(game_id):
    """Advance to next level after solving current puzzle."""
    game = games.get(game_id)
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    if not game.solved:
        return jsonify({
            'error': 'Must solve current puzzle before advancing to next level.'
        }), 400

    result = game.next_level()
    if result is None:
        return jsonify({'error': 'Cannot advance level.'}), 400

    if result.get('complete'):
        return jsonify(result)

    return jsonify({
        'state': result,
        'message': f'Advanced to level {game.level}!'
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Elemental Flux Puzzle Server')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Elemental Flux Puzzle Server")
    print(f"  Open http://localhost:{args.port} to play in browser")
    print(f"  API docs at http://localhost:{args.port}/api/info")
    print(f"{'='*60}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)
