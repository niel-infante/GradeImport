# GradeImport

These scripts turn exported score spreadsheets into Learning Outcome and CR grades and upload them to Canvas. Student data and the API key stay on your machine and are never committed to git.

## Uploading grades

1. **Get the latest code.** In this folder, run:
   ```bash
   git pull
   ```
2. **Activate the Python environment,** if this machine uses one:
   ```bash
   source .venv/bin/activate
   ```
   The home Mac has the packages installed system-wide, so it skips this step. To check any machine, run `python -c "import canvasapi"`. If there's no error, you're set.
3. **Add the new exports to `Data/`,** exactly as downloaded. Leave all earlier exports there too (see [The Data folder](#the-data-folder)).
4. **Check Canvas:** every outcome being uploaded needs a published assignment in each course (see [Canvas assignments](#canvas-assignments)).
5. **Do a dry run.** This changes nothing in Canvas:
   ```bash
   python upload_grades.py
   ```
   It rebuilds the grades from everything in `Data/`, prints the outcomes it will upload, and writes `upload_plan.xlsx` with one row per student per assignment. Check that:
   - every outcome you expect is listed under "Outcomes to upload"
   - there are no `ERROR` lines
   - any `WARNING` lines make sense (see [Troubleshooting](#troubleshooting))
6. **Upload:**
   ```bash
   python upload_grades.py --upload
   ```
   It posts the grades, then reads them back from Canvas. It should finish with "N of N uploaded grades confirmed in Canvas."

It's always safe to run the upload again, for example after getting access to another section. Grades already in Canvas are skipped.

## How grades are calculated

- Each export adds **0 or 1** to each outcome it covers. A score of **0.75 or more** (out of 1) earns 1.
- A student with no submission gets 0 from that export.
- An outcome's total is the sum across all exports that cover it, **capped at 2**. For example, LO 1 from LC 1, LC 2 and Bonus_LO1 can add up to at most 2.
- Totals are recomputed from every export in `Data/` each time.

When uploading, the script compares each total with what's already in Canvas:

| Canvas has | What happens | `Action` in `upload_plan.xlsx` |
|---|---|---|
| No score | Our total is uploaded | `new` |
| A lower score | Raised to our total | `raise` |
| The same score | Skipped | `already in Canvas` |
| A higher score | Left alone and listed as a warning | `Canvas higher (skipped)` |

The script never lowers a score in Canvas.

## The Data folder

Put each export in `Data/` exactly as downloaded. An export can be a `.zip`, a folder you've unzipped, or (for bonus exports) a single `.xlsx` or `.csv` file. A folder and its own zip, such as `CR_1_Version_Set_Scores` and `CR_1_Version_Set_Scores.zip`, count as one export.

**Keep every export in `Data/` for the whole term.** If an old export is removed, its points drop out of the totals. The upload won't lower anything already in Canvas, but those students will show up as "Canvas higher" warnings.

### Export names

The script works out what an export is from the start of its name. Anything after that start is ignored, so download suffixes like `(2) 2` don't matter. Matching ignores capitalization and spaces at either end of the name, and a space or hyphen is accepted where the table shows an underscore. So `cr 3 Version_Set_Scores.zip` is read as CR 3.

| Kind | Name must start with | Covers | Examples |
|---|---|---|---|
| Learning Check | `LC_<n>_-_LO_<a>_` or `LC_<n>_-_LO_<a>_<b>_…_` | LO a (and b, …) | `LC_1_-_LO_1_Version_Set_Scores`<br>`LC_2_-_LO_1_2_Version_Set_Scores.zip` |
| CR | `CR_<n>_` | CR n | `CR_1_Version_Set_Scores.zip` |
| Bonus | `Bonus_LO<n>` or `Bonus_LO_<n>` | LO n | `Bonus_LO1.zip`<br>`Bonus_LO3_scores.xlsx` |

Notes:

- **The number must be followed by a separator (`_`, space, `-` or `.`) or the end of the name.** `LC_2_-_LO_1_2_Version_Set_Scores` covers LO 1 and LO 2. `CR_3.zip` is CR 3, but `CR_3notes.zip` isn't recognized.
- **A Learning Check can come as one export per LO,** e.g. `LC_4_-_LO_5_Version_Set_Scores.zip` and `LC_4_-_LO_6_Version_Set_Scores.zip`. Keep them all; each counts toward its own LO.
- **Ignored, and listed under "Ignored" when the script runs:**
  - anything with `practice` in the name (any capitalization)
  - any other name that doesn't match the table

  Each ignored name is shown in quotes, so stray spaces or odd characters are visible.

### Files inside an export

- **Learning Checks and CRs** contain one file per test version. Each file name ends in `_V<letter>_scores.xlsx` or `_V<letter>_scores.csv`, e.g. `LC_2_-_LO_1_2_-_VA_scores.csv` through `..._VD_scores.csv`. There should be 4 (A–D); the script warns if there aren't. Any other file in the export, such as `..._Version_Set_Scores.xlsx`, is ignored.
- **Bonus exports** contain exactly one spreadsheet, with any name.
- **Zip contents:** subfolders are fine. Mac clutter (`__MACOSX`, `._…`), Excel lock files (`~$…`) and blank rows are ignored.

### Columns the script reads

| Column | Required? | Used for |
|---|---|---|
| `First Name`, `Last Name`, `SID`, `Email`, `Sections` | Always | Identifying the student. `SID` must match the student's SIS ID in Canvas. Rows with no `SID` are skipped. |
| `Status` | Optional | `Graded` counts as a submission and `Missing` doesn't. Without this column, a student with any score counts as submitted. |
| `Total Score` | See below | The score for an export that covers one outcome. Must be out of 1 (if there's a `Max Points` column, it must be 1). |
| Question columns, with names ending in `(… pts)` | See below | Added up when there's no `Total Score`, or split by outcome when an export covers several. |

How each outcome's score is worked out:

- **Exports covering one outcome:** the script uses `Total Score`. If there's no `Total Score` column, it adds up the question columns, which must total 1 point.
- **Exports covering several outcomes:** the script never uses `Total Score`. Questions must be numbered by group, e.g. `1.1: Value of a (0.2 pts)` and `2.3: TF 2 (0.1 pts)`. Group 1 is the first LO in the export name, group 2 the second, and so on. Each group must total 1 point, and the number of groups must match the number of LOs in the name.

## Canvas assignments

- **Names:** each outcome is uploaded to the assignment whose name starts with `LO <n>:` or `CR <n>:`, e.g. `LO 1: Right Triangle Trig` or `CR 3: Logs`.
- **One per outcome:** each course needs exactly one such assignment for each outcome, not counting any with `practice` in the name, which are ignored.
- **Published:** the assignment must be published, or the upload stops.
- **At least 2 points:** it should be worth at least 2 points, since that's the cap.
- **Courses:** only courses named like `26FA MATH1330-002` are used. Other terms and sandboxes are skipped and listed as "Skipping …". Change `TERM` in `canvas_client.py` each semester.

## Troubleshooting

| Message | What it means / what to do |
|---|---|
| An outcome is missing from "Outcomes to upload" | Its export wasn't found. Check the "Ignored" list and the export's name (see [Export names](#export-names)). |
| `Ignored (name not recognised or contains 'practice')` | These items in `Data/` aren't used. Fine for practice exports and stray files; otherwise fix the name. |
| `More than one export for …` | The same export is in `Data/` twice (e.g. `… (1).zip`), or two exports for one Learning Check cover the same LO. Remove the extra one. |
| `no student rows in any file` | The export is empty. Download it again, or move it out of `Data/`. |
| `WARNING: … has 3 versions …, expected 4` | A version file is missing from the export. Check the download. |
| Other messages naming an export and a file | The file's columns don't match what's expected (see [Columns the script reads](#columns-the-script-reads)). The message names the file and the problem. |
| `ERROR: … expected 1 assignment named 'CR 3: ...', found 0` | Create the assignment in that course, or fix its name. If it says found 2, rename or remove one (or put `practice` in the practice one's name). |
| `ERROR: … is not published` | Publish the assignment in Canvas, then run again. |
| `WARNING: N grades are higher in Canvas than our total` | Usually a score changed by hand in Canvas, or an export missing from `Data/`. Filter `upload_plan.xlsx` to `Canvas higher (skipped)` to see which. Canvas **Gradebook → History** shows who changed a grade. |
| `WARNING: N students from … not found in Canvas` | Students who dropped, or a section you can't access yet. Their grades upload on a later run once they're visible. |
| `Missing canvas_api_key.txt` / `Invalid access token` | See [One-time setup](#one-time-setup). The key file must be plain text, and the token must come from `mynu.instructure.com`. |

## Other commands

- **`python combine_scores.py`** builds a `*_master.xlsx` file for each export and `final_grades.xlsx` with every student's totals, without connecting to Canvas. The upload runs this itself, so you only need it to check exports or totals on their own.
- **`python check_ids.py`** is read-only. It lists a few students from each course with their Canvas IDs, to confirm the SIDs in the spreadsheets match Canvas.

## One-time setup

1. **Install the Python packages,** either in a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   or system-wide, with `pip install -r requirements.txt`.
2. **Create a Canvas API token.** In Canvas (`mynu.instructure.com`), go to **Account → Settings → Approved Integrations → + New Access Token**.
3. **Save the token** in a file named `canvas_api_key.txt` in this folder, containing only the token. If you use TextEdit, choose **Format → Make Plain Text** before saving. This file is git-ignored, so it's never committed.
