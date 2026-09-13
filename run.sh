#!/bin/bash
cd "$(dirname "$0")/backend" || { echo "Could not find backend folder"; exit 1; }
( sleep 2 && python3 -c "import webbrowser; webbrowser.open('http://localhost:8000')" ) &
python3 -m uvicorn app:app --reload