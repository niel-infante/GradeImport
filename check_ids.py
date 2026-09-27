"""Read-only test: connect to Canvas and show how students are identified.

Lists the MATH1330 courses you teach, then a few students from each with
every ID Canvas gives us. If LC1_master.xlsx exists (run combine_scores.py
first), each student is also matched to our spreadsheet SID so we can see
which Canvas ID field the SID corresponds to. Nothing is changed in Canvas.

Usage: python check_ids.py [students_per_course]   (default 5)
"""
import sys
from pathlib import Path

import pandas as pd

from canvas_client import get_canvas

COURSE_FILTER = "MATH1330"
MASTER_FILE = Path(__file__).parent / "LC1_master.xlsx"
n_students = int(sys.argv[1]) if len(sys.argv) > 1 else 5

canvas = get_canvas()
me = canvas.get_current_user()
print(f"Connected as: {me.name} (Canvas user id {me.id})\n")

roster = None
if MASTER_FILE.exists():
    roster = pd.read_excel(MASTER_FILE)
    roster["SID"] = roster["SID"].astype(str)
    roster["Email"] = roster["Email"].str.lower()
else:
    print(f"({MASTER_FILE.name} not found; showing Canvas IDs without comparing.)\n")

courses = list(canvas.get_courses(enrollment_type="teacher", include=["sections"]))
matching = [c for c in courses if COURSE_FILTER in getattr(c, "name", "") + getattr(c, "course_code", "")]
if not matching:
    print(f"No courses matching {COURSE_FILTER!r}. Courses you teach:")
    for c in courses:
        print(f"  {c.id}: {getattr(c, 'name', '?')}")
    raise SystemExit

for course in matching:
    sections = ", ".join(s["name"] for s in getattr(course, "sections", []))
    print(f"== Course {course.id}: {course.name}")
    print(f"   Sections: {sections or '?'}")

    students = course.get_users(enrollment_type=["student"], include=["email"])
    for i, user in enumerate(students):
        if i >= n_students:
            break
        ids = {
            "canvas id": user.id,
            "sis_user_id": getattr(user, "sis_user_id", None),
            "login_id": getattr(user, "login_id", None),
            "email": getattr(user, "email", None),
        }
        print(f"   {user.sortable_name}")
        print("      " + "  ".join(f"{k}={v}" for k, v in ids.items()))

        if roster is not None:
            candidates = {str(v).lower() for v in ids.values() if v is not None}
            hit = roster[roster["SID"].isin(candidates) | roster["Email"].isin(candidates)]
            if hit.empty:
                print("      -> not found in our spreadsheet")
            else:
                row = hit.iloc[0]
                matched = [k for k, v in ids.items() if v is not None and str(v).lower() in (row["SID"], row["Email"])]
                print(f"      -> our SID {row['SID']} ({row['First Name']} {row['Last Name']}); matches on: {', '.join(matched)}")
    print()
