"""Exporte des plateaux (générateur Python, référence) pour `traversal-cli`.

    cd backend && PYTHONPATH=. python ../engine-rs/scripts/export_boards.py 200 > ../engine-rs/boards.json
"""

import json
import sys

from app.engine import TERRAIN_MODES, generate_terrain

count = int(sys.argv[1]) if len(sys.argv) > 1 else 200
modes = TERRAIN_MODES[1:]
boards = [list(generate_terrain(modes[i % len(modes)], 10_000 + i)[2]) for i in range(count)]
json.dump(boards, sys.stdout, separators=(",", ":"))
