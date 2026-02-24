"""
Elemental Flux - Core Game Engine

A grid-based discovery puzzle where clicking cells causes phase transformations
that propagate to neighbors based on the cell's node type (shape).
The player must discover the hidden propagation rules and transform all cells
to the target phase.
"""

import random
import uuid
from enum import IntEnum
from typing import List, Tuple, Optional, Dict, Any


class NodeType(IntEnum):
    """Node types determine how clicks propagate to neighboring cells."""
    TRIANGLE = 0   # Propagates vertically (above and below)
    CIRCLE = 1     # Propagates horizontally (left and right)
    SQUARE = 2     # Propagates diagonally
    DIAMOND = 3    # Propagates to all orthogonal neighbors


# Difficulty configurations
DIFFICULTY_CONFIG = {
    'easy': {
        'grid_size': 3,
        'num_phases': 2,
        'num_node_types': 2,
        'base_scramble': 5,
        'scramble_per_level': 2,
        'locked_cells': False,
        'levels': 5,
    },
    'medium': {
        'grid_size': 4,
        'num_phases': 3,
        'num_node_types': 3,
        'base_scramble': 10,
        'scramble_per_level': 3,
        'locked_cells': False,
        'levels': 5,
    },
    'hard': {
        'grid_size': 5,
        'num_phases': 4,
        'num_node_types': 4,
        'base_scramble': 20,
        'scramble_per_level': 4,
        'locked_cells': False,
        'levels': 5,
    },
    'very_hard': {
        'grid_size': 6,
        'num_phases': 4,
        'num_node_types': 4,
        'base_scramble': 35,
        'scramble_per_level': 5,
        'locked_cells': True,
        'levels': 5,
    },
}

PHASE_COLORS = ['#FF4455', '#4499FF', '#44DD55', '#FFCC33']
PHASE_NAMES = ['Red', 'Blue', 'Green', 'Yellow']
NODE_TYPE_NAMES = ['Triangle', 'Circle', 'Square', 'Diamond']
NODE_TYPE_SYMBOLS = ['\u25B2', '\u25CF', '\u25A0', '\u25C6']


class ElementalFluxGame:
    """Core game engine for Elemental Flux puzzle."""

    def __init__(self, difficulty: str = 'easy', level: int = 1, seed: int = None):
        if difficulty not in DIFFICULTY_CONFIG:
            raise ValueError(f"Invalid difficulty: {difficulty}. Choose from: {list(DIFFICULTY_CONFIG.keys())}")
        if level < 1:
            raise ValueError("Level must be >= 1")

        self.game_id = str(uuid.uuid4())[:8]
        self.difficulty = difficulty
        self.level = level
        self.config = DIFFICULTY_CONFIG[difficulty]
        self.grid_size = self.config['grid_size']
        self.num_phases = self.config['num_phases']
        self.num_node_types = self.config['num_node_types']
        self.has_locked_cells = self.config['locked_cells']
        self.max_levels = self.config['levels']

        # Scramble increases with level
        self.scramble_moves = (
            self.config['base_scramble'] + (level - 1) * self.config['scramble_per_level']
        )

        # Seed for reproducibility
        self._seed = seed if seed is not None else random.randint(0, 2**31)
        self._rng = random.Random(self._seed)

        self.target_phase = 0
        self.moves = 0
        self.solved = False
        self.history: List[Tuple[int, int]] = []

        # Score tracking across levels
        self.level_scores: List[Dict] = []
        self.total_score = 0

        self._generate_puzzle()

    def _generate_puzzle(self):
        """Generate a new puzzle by scrambling from solved state."""
        n = self.grid_size

        # Assign random node types (fixed for the puzzle)
        self.node_types = [
            [self._rng.randint(0, self.num_node_types - 1) for _ in range(n)]
            for _ in range(n)
        ]

        # Start with solved state
        self.grid = [[self.target_phase] * n for _ in range(n)]

        # Assign locked cells for very_hard
        self.locked = [[False] * n for _ in range(n)]
        if self.has_locked_cells:
            num_locked = max(1, n * n // 6)
            positions = [(r, c) for r in range(n) for c in range(n)]
            self._rng.shuffle(positions)
            for i in range(num_locked):
                self.locked[positions[i][0]][positions[i][1]] = True

        # Scramble by applying random clicks (only non-locked cells)
        clickable = [
            (r, c) for r in range(n) for c in range(n)
            if not self.locked[r][c]
        ]
        for _ in range(self.scramble_moves):
            r, c = self._rng.choice(clickable)
            self._apply_click(r, c)

        # Ensure puzzle isn't already solved after scrambling
        attempts = 0
        while self._check_solved() and attempts < 100:
            r, c = self._rng.choice(clickable)
            self._apply_click(r, c)
            attempts += 1

        # Store initial state for reset
        self.initial_grid = [row[:] for row in self.grid]
        self.moves = 0
        self.history = []
        self.solved = False

    def _get_affected_cells(self, row: int, col: int) -> List[Tuple[int, int]]:
        """Get cells affected when clicking (row, col), based on node type."""
        n = self.grid_size
        node_type = self.node_types[row][col]
        affected = [(row, col)]

        if node_type == NodeType.TRIANGLE:
            # Vertical propagation
            if row > 0:
                affected.append((row - 1, col))
            if row < n - 1:
                affected.append((row + 1, col))

        elif node_type == NodeType.CIRCLE:
            # Horizontal propagation
            if col > 0:
                affected.append((row, col - 1))
            if col < n - 1:
                affected.append((row, col + 1))

        elif node_type == NodeType.SQUARE:
            # Diagonal propagation
            for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nr, nc = row + dr, col + dc
                if 0 <= nr < n and 0 <= nc < n:
                    affected.append((nr, nc))

        elif node_type == NodeType.DIAMOND:
            # All orthogonal neighbors
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = row + dr, col + dc
                if 0 <= nr < n and 0 <= nc < n:
                    affected.append((nr, nc))

        return affected

    def _apply_click(self, row: int, col: int) -> List[Dict[str, int]]:
        """Apply click and return list of cell changes."""
        affected = self._get_affected_cells(row, col)
        changes = []
        for r, c in affected:
            old_phase = self.grid[r][c]
            new_phase = (old_phase + 1) % self.num_phases
            self.grid[r][c] = new_phase
            changes.append({
                'row': r, 'col': c,
                'old_phase': old_phase, 'new_phase': new_phase
            })
        return changes

    def _check_solved(self) -> bool:
        """Check if all cells match the target phase."""
        return all(
            self.grid[r][c] == self.target_phase
            for r in range(self.grid_size)
            for c in range(self.grid_size)
        )

    def click(self, row: int, col: int) -> Dict[str, Any]:
        """Player clicks cell (row, col). Returns result dict."""
        if self.solved:
            return {
                'success': False,
                'message': 'Puzzle already solved! Start next level or new game.',
                'changes': [],
                'state': self.get_state()
            }

        if not (0 <= row < self.grid_size and 0 <= col < self.grid_size):
            return {
                'success': False,
                'message': f'Invalid position ({row}, {col}). Grid is {self.grid_size}x{self.grid_size}.',
                'changes': [],
                'state': self.get_state()
            }

        if self.has_locked_cells and self.locked[row][col]:
            return {
                'success': False,
                'message': 'This cell is locked and cannot be clicked directly.',
                'changes': [],
                'state': self.get_state()
            }

        # Apply the click
        changes = self._apply_click(row, col)
        self.moves += 1
        self.history.append((row, col))

        # Check win condition
        self.solved = self._check_solved()

        result = {
            'success': True,
            'changes': changes,
            'clicked': {'row': row, 'col': col, 'node_type': self.node_types[row][col]},
            'moves': self.moves,
            'solved': self.solved,
            'state': self.get_state()
        }

        if self.solved:
            score = self._calculate_score()
            result['message'] = f'Puzzle solved in {self.moves} moves! Score: {score}'
            result['score'] = score
            self.level_scores.append({
                'level': self.level,
                'moves': self.moves,
                'score': score
            })
            self.total_score += score
        else:
            result['message'] = f'Clicked ({row}, {col}). {len(changes)} cells changed.'

        return result

    def _calculate_score(self) -> int:
        """Score based on move efficiency. Fewer moves = higher score."""
        optimal_estimate = self.scramble_moves
        if self.moves <= optimal_estimate:
            return 1000
        ratio = optimal_estimate / self.moves
        return max(100, int(1000 * ratio))

    def get_state(self) -> Dict[str, Any]:
        """Get complete game state for API/display."""
        return {
            'game_id': self.game_id,
            'grid': [row[:] for row in self.grid],
            'node_types': [row[:] for row in self.node_types],
            'locked': [row[:] for row in self.locked] if self.has_locked_cells else None,
            'grid_size': self.grid_size,
            'num_phases': self.num_phases,
            'num_node_types': self.num_node_types,
            'target_phase': self.target_phase,
            'moves': self.moves,
            'solved': self.solved,
            'difficulty': self.difficulty,
            'level': self.level,
            'max_levels': self.max_levels,
            'score': self._calculate_score() if self.solved else None,
            'total_score': self.total_score,
            'level_scores': self.level_scores,
            'phase_colors': PHASE_COLORS[:self.num_phases],
            'phase_names': PHASE_NAMES[:self.num_phases],
            'node_type_names': NODE_TYPE_NAMES[:self.num_node_types],
        }

    def reset(self) -> Dict[str, Any]:
        """Reset puzzle to initial scrambled state."""
        self.grid = [row[:] for row in self.initial_grid]
        self.moves = 0
        self.history = []
        self.solved = False
        return self.get_state()

    def next_level(self) -> Optional[Dict[str, Any]]:
        """Advance to next level. Returns new state or None if all levels complete."""
        if not self.solved:
            return None

        if self.level >= self.max_levels:
            return {
                'complete': True,
                'message': f'All {self.max_levels} levels complete! Total score: {self.total_score}',
                'total_score': self.total_score,
                'level_scores': self.level_scores
            }

        self.level += 1
        self.scramble_moves = (
            self.config['base_scramble'] + (self.level - 1) * self.config['scramble_per_level']
        )
        self._seed = self._rng.randint(0, 2**31)
        self._rng = random.Random(self._seed)
        self._generate_puzzle()

        return self.get_state()
