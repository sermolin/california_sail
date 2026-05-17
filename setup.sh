#!/usr/bin/env bash
set -e

# Requires Python 3.9 or later
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Please install Python 3.9+." >&2
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQUIRED_MAJOR=3
REQUIRED_MINOR=9

if python3 -c "import sys; exit(0 if sys.version_info >= ($REQUIRED_MAJOR, $REQUIRED_MINOR) else 1)"; then
  echo "Python $PYTHON_VERSION detected."
else
  echo "ERROR: Python $REQUIRED_MAJOR.$REQUIRED_MINOR or higher is required (found $PYTHON_VERSION)." >&2
  exit 1
fi

echo "Creating virtual environment in .venv/ ..."
python3 -m venv .venv

echo "Activating and installing dependencies ..."
.venv/bin/pip install --upgrade pip --quiet
.venv/bin/pip install -r requirements.txt

# Copy example env file if no .env exists yet
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit it if needed."
fi

echo ""
echo "Setup complete. Run the app with:"
echo "  source .venv/bin/activate"
echo "  streamlit run app/app.py"
echo ""
echo "Or just use the run.sh shortcut:"
echo "  ./run.sh"
