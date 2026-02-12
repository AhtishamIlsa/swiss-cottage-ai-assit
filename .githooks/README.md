# Git Hooks

This directory contains Git hooks that prevent committing unwanted files.

## Pre-commit Hook

The `pre-commit` hook automatically blocks commits that include:
- Python cache files (`__pycache__/`, `*.pyc`, `*.pyo`, `*.pyd`)
- Temporary files (`*.tmp`)
- Log files (`*.log`)
- Environment files (`.env`, `.env.local`, etc.)
- Virtual environments (`venv/`, `.venv/`)
- Vector store directories
- Large model files

## Setup

The hooks are automatically configured when you run:

```bash
./setup-git-hooks.sh
```

Or manually configure Git to use this directory:

```bash
git config core.hooksPath .githooks
```

## How It Works

When you try to commit files that match the blocked patterns, the hook will:
1. Detect the blocked files
2. Display an error message with the list of blocked files
3. Prevent the commit from proceeding
4. Provide instructions on how to unstage the files

This ensures that cache files and other unwanted files cannot be accidentally committed by anyone on the team.
