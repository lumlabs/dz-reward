#!/bin/bash
set -e

PYTHON_BIN="python3"
VENV_DIR=".venv"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
AUTO_MODE=""
DRY_RUN=""
COMMAND="fund"

while [[ $# -gt 0 ]]; do
  case $1 in
    --auto|-a)
      AUTO_MODE="--auto"
      shift
      ;;
    --dry-run|-n)
      DRY_RUN="--dry-run"
      shift
      ;;
    --help|-h)
      echo "DZ-Reward: Validator Debt Management Tool"
      echo ""
      echo "Usage: $0 [command] [options]"
      echo ""
      echo "Commands:"
      echo "  check     Verify configuration and dependencies"
      echo "  status    Check validator debt status"
      echo "  fund      Check and fund outstanding debt (default)"
      echo "  history   Show payment history"
      echo "  version   Show version information"
      echo ""
      echo "Options:"
      echo "  --auto, -a      Non-interactive mode (skip confirmation)"
      echo "  --dry-run, -n   Show what would be done without executing"
      echo "  --help, -h      Show this help message"
      echo ""
      echo "Examples:"
      echo "  $0 check"
      echo "  $0 status"
      echo "  $0 fund --auto"
      echo "  $0 fund --dry-run"
      exit 0
      ;;
    status|fund|history|check|version)
      COMMAND="$1"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [check|status|fund|history|version] [--auto] [--dry-run] [--help]"
      exit 1
      ;;
  esac
done

# Check Python
if ! command -v "$PYTHON_BIN" &> /dev/null; then
  echo "Python3 not found. Please install Python 3.12+."
  exit 1
fi

# Setup virtual environment
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  $PYTHON_BIN -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Install dependencies
if ! command -v uv &> /dev/null; then
  echo "Installing uv..."
  pip install uv
fi

if [ -f "pyproject.toml" ]; then
  echo "Syncing dependencies with uv..."
  uv sync
fi

# Setup Solana keypair symlink if DZ_KEYPAIR_PATH is set
if [ -n "$DZ_KEYPAIR_PATH" ]; then
  mkdir -p ~/.config/solana
  if [ ! -L ~/.config/solana/id.json ]; then
    ln -s "$DZ_KEYPAIR_PATH" ~/.config/solana/id.json
    echo "Created symlink: ~/.config/solana/id.json -> $DZ_KEYPAIR_PATH"
  fi
fi

# Run the main script
cd "$SCRIPT_DIR"
$PYTHON_BIN main.py "$COMMAND" $AUTO_MODE $DRY_RUN
