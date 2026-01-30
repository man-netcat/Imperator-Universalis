# Imperator Universalis

This repository contains the **Imperator Universalis** mod.
The `tools/` directory includes helper utilities, most notably `imperator_converter.py`, which can generate mod files from installed game data.

## Quick Start

1. Open `tools/settings.json` and set the paths for:
   - `ir_game` — Imperator: Rome (Imperattor Rome/game)
   - `eu5_game` — Europa Universalis V (Europa Universalis V/game)
2. Run the converter:

```bash
cd tools
python3 imperator_converter.py
```

## Cloning (with Submodules)

Recommended method:

```bash
git clone --recurse-submodules https://github.com/man-netcat/Imperator-Universalis.git
cd Imperator-Universalis/tools
```

If already cloned without submodules:

```bash
git submodule update --init --recursive
```

## Requirements

- Python 3 available as python3
- The bundled pyradox package present at tools/pyradox/src

## Configuration

Edit tools/settings.json and set:

- ir_game: path to the Imperator: Rome `game` directory
- eu5_game: path to the Europa Universalis V `game` directory