"""Shared Canvas connection. The API key is read from canvas_api_key.txt,
which lives next to this file and is git-ignored."""
import re
from pathlib import Path

from canvasapi import Canvas

BASE_URL = "https://mynu.instructure.com"
KEY_FILE = Path(__file__).parent / "canvas_api_key.txt"

# Only courses named like "26FA MATH1330-002 ..." are used. Change TERM each semester.
TERM = "26FA"
COURSE = "MATH1330"
COURSE_PATTERN = re.compile(rf"^{TERM}\s*{COURSE}-\d+", re.IGNORECASE)


def target_courses(canvas, **kwargs):
    """Return (this term's COURSE sections you teach, other COURSE courses that were skipped)."""
    use, skipped = [], []
    for course in canvas.get_courses(enrollment_type="teacher", **kwargs):
        names = [(getattr(course, f, None) or "").strip() for f in ("name", "course_code")]
        if any(COURSE_PATTERN.match(n) for n in names):
            use.append(course)
        elif any(COURSE.lower() in n.lower() for n in names):
            skipped.append(course)
    return use, skipped


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
