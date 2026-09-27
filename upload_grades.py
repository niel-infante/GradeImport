"""Upload final_grades.xlsx to Canvas.

Dry run by default: matches every student and assignment, prints a summary,
and writes upload_plan.xlsx showing exactly what would be posted. Nothing is
changed in Canvas unless you add --upload.

Students are matched by SID = Canvas sis_user_id. Assignments are matched by
exact name (CANVAS_ASSIGNMENTS in combine_scores.py).

Outcome scores are additive across assessments, capped at 2, and
final_grades.xlsx already holds each student's full total. Grades already in
Canvas with the same value are skipped, so it is safe to rerun (e.g. after
gaining access to another section). Any different existing score blocks the
upload; adding to existing scores is not implemented yet.

Usage:
    python upload_grades.py            # dry run
    python upload_grades.py --upload   # post grades
"""
import sys
import time
from pathlib import Path

import pandas as pd

from canvas_client import get_canvas
from combine_scores import CANVAS_ASSIGNMENTS, MAX_SCORE

ROOT = Path(__file__).parent
GRADES_FILE = ROOT / "final_grades.xlsx"
PLAN_FILE = ROOT / "upload_plan.xlsx"
COURSE_FILTER = "MATH1330"


def norm_id(value):
    """SIDs can lose leading zeros in Excel/CSV, so compare without them."""
    if value is None or pd.isna(value):
        return None
    return str(value).strip().lstrip("0")


def build_plan(canvas, grades, assignment_names):
    """Match spreadsheet rows to Canvas students and assignments.

    Returns (plan DataFrame, assignment objects by (course id, assignment id),
    blocking errors, warnings).
    """
    errors, warnings, rows, assignment_objs = [], [], [], {}

    courses = [
        c for c in canvas.get_courses(enrollment_type="teacher", enrollment_state="active")
        if COURSE_FILTER in getattr(c, "name", "") + getattr(c, "course_code", "")
    ]
    if not courses:
        return pd.DataFrame(), {}, [f"No active courses matching {COURSE_FILTER!r}"], []

    grades = grades.assign(key=grades["SID"].map(norm_id)).set_index("key")
    matched_keys = set()

    for course in courses:
        print(f"Course {course.id}: {course.name}")

        by_name = {}
        for a in course.get_assignments():
            if a.name in assignment_names:
                by_name.setdefault(a.name, []).append(a)
        course_assignments = []
        for name in assignment_names:
            found = by_name.get(name, [])
            if len(found) != 1:
                errors.append(f"{course.name}: expected 1 assignment named {name!r}, found {len(found)}")
                continue
            course_assignments.append(found[0])
            assignment_objs[(course.id, found[0].id)] = found[0]
            print(f"  {name}: assignment {found[0].id}, {found[0].points_possible} pts possible")

        students = {}
        for user in course.get_users(enrollment_type=["student"]):
            key = norm_id(getattr(user, "sis_user_id", None))
            if key in grades.index:
                students[key] = user
            else:
                warnings.append(f"{course.name}: {user.sortable_name} (sis_user_id "
                                f"{getattr(user, 'sis_user_id', None)}) is not in {GRADES_FILE.name}; skipped")
        dupes = matched_keys & students.keys()
        for key in dupes:
            errors.append(f"SID {grades.loc[key, 'SID']} is enrolled in more than one {COURSE_FILTER} course")
        matched_keys |= students.keys()
        print(f"  {len(students)} students matched")

        for a in course_assignments:
            current = {s.user_id: s.score for s in a.get_submissions()}
            for key, user in students.items():
                row = grades.loc[key]
                rows.append({
                    "Course": course.name,
                    "Last Name": row["Last Name"],
                    "First Name": row["First Name"],
                    "SID": row["SID"],
                    "Canvas user id": user.id,
                    "Assignment": a.name,
                    "Current score": current.get(user.id),
                    "New score": int(row[a.name]),
                    "course_id": course.id,
                    "assignment_id": a.id,
                })

    # Students we can't see in Canvas: dropped, or in a section this account can't access yet.
    unmatched = grades.loc[sorted(set(grades.index) - matched_keys)]
    for section, group in unmatched.groupby("Sections"):
        names = ", ".join(f"{r['First Name']} {r['Last Name']}" for _, r in group.iterrows())
        warnings.append(f"{len(group)} students from {section} not found in Canvas; skipped: {names}")

    plan = pd.DataFrame(rows)
    if not plan.empty:
        same = plan["Current score"] == plan["New score"]
        plan["Action"] = "upload"
        plan.loc[same, "Action"] = "already in Canvas"
        conflict = plan[plan["Current score"].notna() & ~same]
        if not conflict.empty:
            plan.loc[conflict.index, "Action"] = "CONFLICT"
            errors.append(f"{len(conflict)} grades already have a different score in Canvas (Action = "
                          f"CONFLICT in {PLAN_FILE.name}). Adding to existing scores is not implemented yet.")
        over = plan[plan["New score"] > MAX_SCORE]
        if not over.empty:
            errors.append(f"{len(over)} scores are above the cap of {MAX_SCORE}")
    return plan, assignment_objs, errors, warnings


def upload(plan, assignment_objs):
    for (course_id, assignment_id), group in plan.groupby(["course_id", "assignment_id"]):
        assignment = assignment_objs[(course_id, assignment_id)]
        grade_data = {int(r["Canvas user id"]): {"posted_grade": str(r["New score"])} for _, r in group.iterrows()}
        print(f"  {group['Course'].iloc[0]} / {assignment.name}: posting {len(grade_data)} grades...", end=" ", flush=True)
        progress = assignment.submissions_bulk_update(grade_data=grade_data)
        while progress.workflow_state in ("queued", "running"):
            time.sleep(2)
            progress = progress.query()
        print(progress.workflow_state)
        if progress.workflow_state != "completed":
            raise SystemExit(f"Canvas reported {progress.workflow_state}: {getattr(progress, 'message', '')}")


def verify(plan, assignment_objs):
    """Re-read scores from Canvas and compare with what we posted."""
    bad = 0
    for (course_id, assignment_id), group in plan.groupby(["course_id", "assignment_id"]):
        scores = {s.user_id: s.score for s in assignment_objs[(course_id, assignment_id)].get_submissions()}
        for _, r in group.iterrows():
            if scores.get(int(r["Canvas user id"])) != r["New score"]:
                bad += 1
                print(f"  MISMATCH {r['First Name']} {r['Last Name']} / {r['Assignment']}: "
                      f"expected {r['New score']}, Canvas has {scores.get(int(r['Canvas user id']))}")
    return bad


def main():
    do_upload = "--upload" in sys.argv[1:]
    grades = pd.read_excel(GRADES_FILE)
    assignment_names = [n for n in CANVAS_ASSIGNMENTS.values() if n in grades.columns]

    canvas = get_canvas()
    print(f"Connected as {canvas.get_current_user().name}\n")
    plan, assignment_objs, errors, warnings = build_plan(canvas, grades, assignment_names)

    to_upload = plan
    if not plan.empty:
        plan.drop(columns=["course_id", "assignment_id"]).to_excel(PLAN_FILE, index=False)
        print(f"\nPlan written to {PLAN_FILE.name}: {len(plan)} grades")
        print(plan["Action"].value_counts().to_string())
        to_upload = plan[plan["Action"] == "upload"]
        if not to_upload.empty:
            print("\nNew scores to upload:")
            print(to_upload.groupby(["Assignment", "New score"]).size().unstack(fill_value=0).to_string())

    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        raise SystemExit("\nNot uploading: fix the errors above first.")
    if to_upload.empty:
        print("\nNothing new to upload.")
        return
    if not do_upload:
        print("\nDry run only. Check upload_plan.xlsx, then run with --upload to post these grades.")
        return

    print("\nUploading...")
    upload(to_upload, assignment_objs)
    print("\nVerifying...")
    bad = verify(plan, assignment_objs)
    print(f"Done: {len(plan) - bad} of {len(plan)} grades confirmed in Canvas.")


if __name__ == "__main__":
    main()
