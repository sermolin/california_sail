#!/usr/bin/env bash
set -e

if [ ! -d ".venv" ]; then
  echo "No .venv found. Run ./setup.sh first." >&2
  exit 1
fi

.venv/bin/streamlit run app/app.py
