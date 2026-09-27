"""Shared Canvas connection. The API key is read from canvas_api_key.txt,
which lives next to this file and is git-ignored."""
from pathlib import Path

from canvasapi import Canvas

BASE_URL = "https://mynu.instructure.com"
KEY_FILE = Path(__file__).parent / "canvas_api_key.txt"


def get_canvas():
    if not KEY_FILE.exists():
        raise SystemExit(
            f"Missing {KEY_FILE.name}. Create it in {KEY_FILE.parent} containing only your Canvas API key.\n"
            "(Canvas -> Account -> Settings -> Approved Integrations -> + New Access Token)"
        )
    key = KEY_FILE.read_text().strip()
    if not key:
        raise SystemExit(f"{KEY_FILE.name} is empty.")
    return Canvas(BASE_URL, key)
