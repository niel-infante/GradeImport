"""Combine each assessment's four version score sheets into one master sheet.

Each version file (VA-VD) lists every student, but a student is only
"Graded" in the version they took. We keep those rows and, for each
outcome the assessment covers, sum that outcome's question columns and
award 1 if the sum is >= the cutoff, else 0. Students with no graded
submission in any version get 0.

Usage: python combine_scores.py [LC1 CR1 LC2 ...]   (default: all)
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "Data"
ID_COLS = ["First Name", "Last Name", "SID", "Email", "Sections"]
MAX_SCORE = 2  # outcome scores add up across assessments, capped here

# Canvas assignment name for each outcome grade column.
CANVAS_ASSIGNMENTS = {
    "LO1": "LO 1: Right Triangle Trig",
    "LO2": "LO 2: Unit Circle",
    "CR1": "CR 1: Factoring",
}

# outcomes: grade column -> (question-number prefix, cutoff). A prefix of ""
# takes every question column in the file.
ASSESSMENTS = {
    "LC1": dict(
        folder=DATA / "LC_1_-_LO_1_Version_Set_Scores(2) 2",
        pattern="LC_1_-_V{v}_scores.xlsx",
        n_questions=4,
        outcomes={"LO1": ("", 0.75)},
    ),
    "CR1": dict(
        folder=DATA / "CR_1_Version_Set_Scores",
        pattern="CR_1_-_V{v}_scores.xlsx",
        n_questions=5,
        outcomes={"CR1": ("", 0.80)},
    ),
    "LC2": dict(
        folder=DATA / "LC_2_-_LO_1_2_Version_Set_Scores",
        pattern="LC_2_-_LO_1_2_-_V{v}_scores.csv",
        n_questions=14,
        outcomes={"LO1": ("1.", 0.75), "LO2": ("2.", 0.75)},
    ),
}


def read_sheet(path):
    return pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path)


def question_cols(columns, prefix=""):
    return [c for c in columns if c.endswith("pts)") and c.startswith(prefix)]


def combine(name, folder, pattern, n_questions, outcomes):
    frames = []
    for version in "ABCD":
        df = read_sheet(folder / pattern.format(v=version))
        assert len(question_cols(df.columns)) == n_questions, (version, question_cols(df.columns))
        df["Version"] = version
        frames.append(df)
    # Question wording can differ between versions (e.g. LC2 2.8 is cosine in A/C,
    # sine in B/D), so the combined frame has NaN where a version lacks a column.
    all_rows = pd.concat(frames, ignore_index=True)

    graded = all_rows[all_rows["Status"] == "Graded"].copy()
    dupes = graded["SID"][graded["SID"].duplicated()]
    assert dupes.empty, f"Students graded in more than one version: {dupes.tolist()}"

    out_cols = []
    for grade_col, (prefix, cutoff) in outcomes.items():
        cols = question_cols(all_rows.columns, prefix)
        sum_col = f"{grade_col} Sum"
        # Round so float noise (e.g. 0.2 * 4) doesn't fall just under the cutoff.
        graded[sum_col] = graded[cols].sum(axis=1).round(4)
        graded[grade_col] = (graded[sum_col] >= cutoff).astype(int)
        out_cols += [sum_col, grade_col]
    assert (graded[[c for c in out_cols if c.endswith(" Sum")]].sum(axis=1).round(4)
            == graded["Total Score"].round(4)).all(), "Outcome sums don't add up to Total Score"

    # One row per student (including those who never submitted).
    roster = all_rows[ID_COLS].drop_duplicates("SID")
    master = roster.merge(
        graded[["SID", "Version", *question_cols(all_rows.columns), *out_cols]], on="SID", how="left"
    )
    master["Version"] = master["Version"].fillna("Missing")
    for grade_col in outcomes:
        master[grade_col] = master[grade_col].fillna(0).astype(int)
    master = master.sort_values(["Sections", "Last Name", "First Name"])

    out_file = ROOT / f"{name}_master.xlsx"
    master.to_excel(out_file, index=False)

    print(f"== {name}: wrote {len(master)} students to {out_file.name}")
    for grade_col, (_, cutoff) in outcomes.items():
        counts = master[grade_col].value_counts()
        print(f"  {grade_col} (cutoff {cutoff}): {counts.get(1, 0)} x 1, {counts.get(0, 0)} x 0")
    missing = master[master["Version"] == "Missing"]
    if not missing.empty:
        print(f"  No submission (given 0): {len(missing)}")
        print(missing[["First Name", "Last Name", "SID", "Sections"]].to_string(index=False))
    print()
    return master


def final_grades(masters):
    """Add up each outcome across assessments, capped at MAX_SCORE.

    Outcomes are additive: 1 on LO1 in LC1 plus 1 on LO1 in LC2 gives 2.
    Canvas currently has no outcome scores entered, so this is the whole
    score. Once scores exist, the upload must add to the student's current
    Canvas score (still capped) rather than overwrite it.
    """
    final = None
    for name, master in masters.items():
        grades = master[["SID", *ASSESSMENTS[name]["outcomes"]]]
        grades = grades.rename(columns={o: f"{name} {o}" for o in ASSESSMENTS[name]["outcomes"]})
        if final is None:
            final = master[ID_COLS].merge(grades, on="SID")
        else:
            final = final.merge(grades, on="SID", how="outer")
    assert final[ID_COLS].notna().all().all(), "Rosters differ between assessments"

    for outcome, assignment in CANVAS_ASSIGNMENTS.items():
        sources = [c for c in final.columns if c.endswith(f" {outcome}")]
        if sources:
            final[assignment] = final[sources].fillna(0).sum(axis=1).clip(upper=MAX_SCORE).astype(int)

    final = final.sort_values(["Sections", "Last Name", "First Name"])
    out_file = ROOT / "final_grades.xlsx"
    final.to_excel(out_file, index=False)

    print(f"== Final: wrote {len(final)} students to {out_file.name}")
    for assignment in CANVAS_ASSIGNMENTS.values():
        if assignment in final:
            counts = final[assignment].value_counts().sort_index()
            print(f"  {assignment}: " + ", ".join(f"{n} x {s}" for s, n in counts.items()))
    return final


if __name__ == "__main__":
    names = sys.argv[1:] or list(ASSESSMENTS)
    masters = {name: combine(name, **ASSESSMENTS[name]) for name in names}
    final_grades(masters)
