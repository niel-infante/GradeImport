"""Upload final_grades.xlsx to Canvas.

Runs combine_scores.py first, so final_grades.xlsx always reflects what is
currently in Data/.

Dry run by default: matches every student and assignment, prints a summary,
and writes upload_plan.xlsx showing exactly what would be posted. Nothing is
changed in Canvas unless you add --upload.

Students are matched by SID = Canvas sis_user_id. Each outcome column in
final_grades.xlsx (LO1, CR2, ...) is matched to the Canvas assignment whose
name starts with it, e.g. LO1 -> "LO 1: Right Triangle Trig". Assignments
with "practice" in the name are ignored.

final_grades.xlsx holds each student's full total, recomputed from every
export, so uploads only ever raise scores:
  - no score in Canvas, or lower than ours -> upload ours
  - same as ours                           -> skip (safe to rerun)
  - higher than ours                       -> skip and report (never lowered)

Usage:
    python upload_grades.py            # dry run
    python upload_grades.py --upload   # post grades
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd

from canvas_client import COURSE, TERM, get_canvas, target_courses
from combine_scores import MAX_SCORE
from combine_scores import main as combine_all

ROOT = Path(__file__).parent
GRADES_FILE = ROOT / "final_grades.xlsx"
PLAN_FILE = ROOT / "upload_plan.xlsx"
OUTCOME_COLUMN = re.compile(r"^([A-Z]+)(\d+)$")
ACTIONS_TO_UPLOAD = ("new", "raise")


def norm_id(value):
    """SIDs can lose leading zeros in Excel/CSV, so compare without them."""
    if value is None or pd.isna(value):
        return None
    return str(value).strip().lstrip("0")


def find_assignment(assignments, outcome):
    """The one assignment named like "LO 1: ..." for outcome "LO1", or an error message."""
    kind, number = OUTCOME_COLUMN.match(outcome).groups()
    pattern = re.compile(rf"^{kind}\s*{number}\s*:", re.IGNORECASE)
    found = [a for a in assignments if pattern.match(a.name.strip()) and "practice" not in a.name.lower()]
    if len(found) != 1:
        names = f": {', '.join(a.name for a in found)}" if found else ""
        return None, f"expected 1 assignment named '{kind} {number}: ...', found {len(found)}{names}"
    if not getattr(found[0], "published", True):
        return None, f"assignment {found[0].name!r} is not published; publish it in Canvas first"
    return found[0], None


def build_plan(canvas, grades, outcomes):
    """Match spreadsheet rows to Canvas students and assignments.

    Returns (plan DataFrame, assignment objects by (course id, assignment id),
    blocking errors, warnings).
    """
    errors, warnings, rows, assignment_objs = [], [], [], {}

    courses, skipped = target_courses(canvas, enrollment_state="active")
    for course in skipped:
        print(f"Skipping {course.name} (not {TERM} {COURSE}-xxx)")
    if not courses:
        return pd.DataFrame(), {}, [f"No active courses named like '{TERM} {COURSE}-xxx'"], []

    grades = grades.assign(key=grades["SID"].map(norm_id)).set_index("key")
    matched_keys = set()

    for course in courses:
        print(f"Course {course.id}: {course.name}")

        all_assignments = list(course.get_assignments())
        course_assignments = []
        for outcome in outcomes:
            assignment, problem = find_assignment(all_assignments, outcome)
            if problem:
                errors.append(f"{course.name}: {outcome}: {problem}")
                continue
            course_assignments.append((outcome, assignment))
            assignment_objs[(course.id, assignment.id)] = assignment
            print(f"  {outcome} -> {assignment.name}: assignment {assignment.id}, "
                  f"{assignment.points_possible} pts possible")

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
            errors.append(f"SID {grades.loc[key, 'SID']} is enrolled in more than one {TERM} {COURSE} course")
        matched_keys |= students.keys()
        print(f"  {len(students)} students matched")

        for outcome, a in course_assignments:
            current = {s.user_id: s.score for s in a.get_submissions()}
            for key, user in students.items():
                row = grades.loc[key]
                rows.append({
                    "Course": course.name,
                    "Last Name": row["Last Name"],
                    "First Name": row["First Name"],
                    "SID": row["SID"],
                    "Canvas user id": user.id,
                    "Outcome": outcome,
                    "Assignment": a.name,
                    "Current score": current.get(user.id),
                    "New score": int(row[outcome]),
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
        current, new = plan["Current score"], plan["New score"]
        plan["Action"] = "new"
        plan.loc[current < new, "Action"] = "raise"
        plan.loc[current == new, "Action"] = "already in Canvas"
        higher = current > new
        plan.loc[higher, "Action"] = "Canvas higher (skipped)"
        if higher.any():
            warnings.append(f"{higher.sum()} grades are higher in Canvas than our total and were left alone "
                            f"(Action = 'Canvas higher (skipped)' in {PLAN_FILE.name}). Usually a hand-entered "
                            f"score, or an export missing from Data/.")
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
    # Always rebuild final_grades.xlsx first, so an export added to Data/ since
    # the last combine can't be silently left out.
    print("Combining scores from Data/ ...\n")
    combine_all()
    grades = pd.read_excel(GRADES_FILE)
    outcomes = [c for c in grades.columns if OUTCOME_COLUMN.match(c)]
    print(f"\nOutcomes to upload: {', '.join(outcomes)}\n")

    canvas = get_canvas()
    print(f"Connected as {canvas.get_current_user().name}\n")
    plan, assignment_objs, errors, warnings = build_plan(canvas, grades, outcomes)

    to_upload = plan
    if not plan.empty:
        plan.drop(columns=["course_id", "assignment_id"]).to_excel(PLAN_FILE, index=False)
        print(f"\nPlan written to {PLAN_FILE.name}: {len(plan)} grades")
        print(plan["Action"].value_counts().to_string())
        to_upload = plan[plan["Action"].isin(ACTIONS_TO_UPLOAD)]
        if not to_upload.empty:
            print("\nScores to upload:")
            print(to_upload.groupby(["Outcome", "New score"]).size().unstack(fill_value=0).to_string())

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
    bad = verify(to_upload, assignment_objs)
    print(f"Done: {len(to_upload) - bad} of {len(to_upload)} uploaded grades confirmed in Canvas.")


if __name__ == "__main__":
    main()
