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

Put each export in `Data/` exactly as downloaded. A `.zip` is fine, and so is a folder you've unzipped (a folder and its own zip count as one export). The script recognizes exports by name:

- `LC_<n>_-_LO_<a>_<b>_...` is Learning Check n, covering LO a, b, …, as 4 version files
- `CR_<n>_...` is CR n, as 4 version files
- `Bonus_LO<n>...` is a bonus for LO n, as a single file

**Keep every export in `Data/` for the whole term.** Totals are recomputed from all of them each time. If an old export is removed, those points drop out of the totals, though the upload never lowers a score already in Canvas.

If you download the same export twice (e.g. `... (1).zip`), the script stops and asks you to remove one.

## Running

Activate the environment each time with `source .venv/bin/activate`.

- `python combine_scores.py` builds a `*_master.xlsx` file for each export and `final_grades.xlsx` with every student's outcome totals. Each export adds 0 or 1 to each outcome it covers (1 if the score is 0.75 or more), and each outcome total is capped at 2.
- `python upload_grades.py` does a dry run. It matches students and assignments in Canvas and writes `upload_plan.xlsx` showing every grade it would post. Nothing changes in Canvas.
- `python upload_grades.py --upload` posts the grades, then reads them back from Canvas to confirm they were saved. Each outcome goes to the Canvas assignment whose name starts with it (LO1 goes to "LO 1: …"), and the assignment must be published. Assignments and exports with "practice" in the name are ignored. Scores are only ever raised. Ones already correct are skipped, and ones higher in Canvas than our total are left alone and listed as warnings.
- `python check_ids.py` is a read-only test. It connects to Canvas and lists a few students from each course with their Canvas IDs. If you've run `combine_scores.py` first, it also shows which Canvas ID matches the SID in the spreadsheets.
