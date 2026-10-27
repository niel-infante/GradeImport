# GradeImport

These scripts combine exported score spreadsheets into outcome grades and upload them to Canvas. Student data and the API key stay on your machine and are never committed to git.

## One-time setup

1. Install the Python packages:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Create a Canvas API token. In Canvas, go to **Account → Settings → Approved Integrations → + New Access Token**.
3. Save the token in a file named `canvas_api_key.txt` in this folder. The file should contain only the token.
4. Put the exported score files in `Data/` (see below).

## The Data folder

Put each export in `Data/` exactly as downloaded. An export can be a `.zip`, a folder you've unzipped, or (for bonus exports) a single `.xlsx` or `.csv` file. A folder and its own zip, such as `CR_1_Version_Set_Scores` and `CR_1_Version_Set_Scores.zip`, count as one export.

**Keep every export in `Data/` for the whole term.** Totals are recomputed from all of them each time. If an old export is removed, those points drop out of the totals, though the upload never lowers a score already in Canvas.

## Expected file names

### Export names (the items in `Data/`)

The script works out what an export is from the start of its name. Anything after that start is ignored, so download suffixes like `(2) 2` don't matter. Matching ignores capitalization and spaces at either end of the name, and a space or hyphen is accepted where the table shows an underscore. So `cr 3 Version_Set_Scores.zip` is read as CR 3.

| Kind | Name must start with | Covers | Examples |
|---|---|---|---|
| Learning Check | `LC_<n>_-_LO_<a>_` or `LC_<n>_-_LO_<a>_<b>_…_` | LO a (and b, …) | `LC_1_-_LO_1_Version_Set_Scores`<br>`LC_2_-_LO_1_2_Version_Set_Scores.zip` |
| CR | `CR_<n>_` | CR n | `CR_1_Version_Set_Scores.zip` |
| Bonus | `Bonus_LO<n>` or `Bonus_LO_<n>` | LO n | `Bonus_LO1.zip`<br>`Bonus_LO3_scores.xlsx` |

Notes:

- **The number must be followed by a separator (`_`, space, `-` or `.`) or the end of the name.** `LC_2_-_LO_1_2_Version_Set_Scores` covers LO 1 and LO 2. `CR_3.zip` is CR 3, but `CR_3notes.zip` isn't recognized.
- **A Learning Check can come as one export per LO,** e.g. `LC_4_-_LO_5_Version_Set_Scores.zip` and `LC_4_-_LO_6_Version_Set_Scores.zip`. Keep them all; each counts toward its own LO.
- **These are ignored, and listed as "Ignored" when the script runs.** Each ignored name is shown in quotes, so stray spaces or odd characters are visible.
  - anything with `practice` in the name (any capitalization)
  - any other name that doesn't match the table
- **These stop the script and name the files involved:**
  - the same export downloaded twice, e.g. `... (1).zip`
  - two exports for the same Learning Check that cover the same LO

### Files inside an export

- **Learning Checks and CRs** contain one file per test version. Each file name ends in `_V<letter>_scores.xlsx` or `_V<letter>_scores.csv`, e.g. `LC_2_-_LO_1_2_-_VA_scores.csv` through `..._VD_scores.csv`. There should be 4 (A–D); the script warns if there aren't. Any other file in the export, such as `..._Version_Set_Scores.xlsx`, is ignored.
- **Bonus exports** contain exactly one spreadsheet, with any name.
- **Zip contents:** subfolders are fine. Mac clutter (`__MACOSX`, `._…`) and Excel lock files (`~$…`) are ignored.

### Columns the script reads

| Column | Required? | Used for |
|---|---|---|
| `First Name`, `Last Name`, `SID`, `Email`, `Sections` | Always | Identifying the student. `SID` must match the student's SIS ID in Canvas. |
| `Status` | Optional | `Graded` counts as a submission and `Missing` doesn't. Without this column, a student with any score counts as submitted. |
| `Total Score` | See below | The score for an export that covers one outcome. Must be out of 1 (if there's a `Max Points` column, it must be 1). |
| Question columns, with names ending in `(… pts)` | See below | Added up when there's no `Total Score`, or split by outcome when an export covers several. |

How the score for each outcome is worked out:

- **Exports covering one outcome:** the script uses `Total Score`. If there's no `Total Score` column, it adds up the question columns, which must total 1 point.
- **Exports covering several outcomes:** the script never uses `Total Score`. Questions must be numbered by group, e.g. `1.1: Value of a (0.2 pts)` and `2.3: TF 2 (0.1 pts)`. Group 1 is the first LO in the export name, group 2 the second, and so on. Each group must total 1 point, and the number of groups must match the number of LOs in the name.

A score of 0.75 or more for an outcome earns 1 point toward that outcome.

### Canvas assignment names

Each outcome is uploaded to the assignment whose name starts with `LO <n>:` or `CR <n>:`, e.g. `LO 1: Right Triangle Trig` or `CR 1: Factoring`. Each course needs exactly one such assignment per outcome, it must be published, and it should be worth at least 2 points. Assignments with `practice` in the name are ignored. Only courses named like `26FA MATH1330-002` are used; change `TERM` in `canvas_client.py` each semester.

## Running

First, run 
`git pull`

This gets the most up-to-date code.



Activate the environment each time with `source .venv/bin/activate`.

Not needed if we installed to the system env, which we did on the home mac. Don't remember the school mac.

- `python combine_scores.py` builds a `*_master.xlsx` file for each export and `final_grades.xlsx` with every student's outcome totals. Each export adds 0 or 1 to each outcome it covers (1 if the score is 0.75 or more), and each outcome total is capped at 2.
- `python upload_grades.py` does a dry run. It matches students and assignments in Canvas and writes `upload_plan.xlsx` showing every grade it would post. Nothing changes in Canvas.
- `python upload_grades.py --upload` posts the grades, then reads them back from Canvas to confirm they were saved. Each outcome goes to the Canvas assignment whose name starts with it (LO1 goes to "LO 1: …"), and the assignment must be published. Assignments and exports with "practice" in the name are ignored. Scores are only ever raised. Ones already correct are skipped, and ones higher in Canvas than our total are left alone and listed as warnings.
- `python check_ids.py` is a read-only test. It connects to Canvas and lists a few students from each course with their Canvas IDs. If you've run `combine_scores.py` first, it also shows which Canvas ID matches the SID in the spreadsheets.
