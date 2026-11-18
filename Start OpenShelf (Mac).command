#!/bin/bash
# Double-click on macOS to start OpenShelf
cd "$(dirname "$0")"
if command -v python3 >/dev/null; then python3 openshelf.py; else echo "Python 3 is not installed. Get it from https://www.python.org/downloads/"; read -r -p "Press Enter to close"; fi
