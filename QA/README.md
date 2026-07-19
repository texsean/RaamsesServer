# QA - Raamses Quality Assurance

This folder contains unit tests, emulators, and console tools used for testing the Raamses system.

## Contents

- `tests/` — Unit tests for messages, console, and verifier
- `emulator/` — Verifier emulator (Python version)
- `console/` — Raamses Terminal Console (htop-style + CYD + E-Paper modes)

## Usage

Run tests:
```bash
cd QA
python -m pytest tests/
```

Run the terminal console:
```bash
python console/terminal_console.py full
python console/terminal_console.py cyd
python console/terminal_console.py epaper
```