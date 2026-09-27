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
4. Put the exported score folders in `Data/`.

## Running

Activate the environment each time with `source .venv/bin/activate`.

- `python combine_scores.py` builds the `*_master.xlsx` files and `final_grades.xlsx` from the files in `Data/`.
- `python upload_grades.py` does a dry run. It matches students and assignments in Canvas and writes `upload_plan.xlsx` showing every grade it would post. Nothing changes in Canvas.
- `python upload_grades.py --upload` posts the grades, then reads them back from Canvas to confirm they were saved. It won't run if any of these assignments already has scores in Canvas.
- `python check_ids.py` is a read-only test. It connects to Canvas and lists a few students from each course with their Canvas IDs. If you've run `combine_scores.py` first, it also shows which Canvas ID matches the SID in the spreadsheets.
