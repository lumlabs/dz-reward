#!/bin/bash
set -e


export PATH="$HOME/mocks:$PATH"

PYTHON_BIN="python3"
VENV_DIR=".venv"
EPOCH="$1"

if [ -z "$EPOCH" ]; then
  echo "Usage: $0 <epoch>"
  exit 1
fi


if ! command -v "$PYTHON_BIN" &> /dev/null; then
  echo "Python3 not found. Please install Python 3.8+."
  exit 1
fi


if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  $PYTHON_BIN -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"


if ! command -v uv &> /dev/null; then
  echo "Installing uv..."
  pip install uv
fi

if [ -f "pyproject.toml" ]; then
  echo "Syncing dependencies with uv..."
  uv sync
elif [ -f "requirements.txt" ]; then
  echo "Installing dependencies from requirements.txt..."
  pip install -r requirements.txt
else
  echo "No dependency file found — skipping uv sync."
fi

ADDRESS=$(doublezero address)
if [ -z "$ADDRESS" ]; then
  echo "Failed to get address from doublezero."
  exit 1
fi

echo "Validator Address: $ADDRESS"

PY_OUTPUT=$(python main.py "$EPOCH" "$ADDRESS")

echo "$PY_OUTPUT"
FUND_SOL=$(printf "%s\n" "$PY_OUTPUT" | grep -F '__FUND_SOL__:' | head -n1 | cut -d ':' -f2 | tr -d '[:space:]')

if [ -z "$FUND_SOL" ]; then
  echo "Could not determine fund amount."
  exit 1
fi

echo "You need to fund: ${FUND_SOL} SOL"

read -p "Do you want to proceed with funding? (y/n): " CONFIRM

if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Executing funding transaction..."
  doublezero-solana revenue-distribution validator-deposit "$ADDRESS" --fund "$FUND_SOL" -u mainnet-beta
else
  echo "Funding canceled."
fi
