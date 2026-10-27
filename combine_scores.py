"""Turn every score export in Data/ into outcome grades.

Exports are found by name (anything with "practice" in its name is ignored).
Each one can be a folder, a .zip, or (for bonus exports) a single spreadsheet:
    LC_<n>_-_LO_<a>[_<b>...]_...   Learning Check n, covering LO a, b, ...
                                   (an LC may also come as one export per LO)
    CR_<n>_...                     CR n
    Bonus_LO<n>...                 bonus for LO n

LC and CR exports hold one file per test version (..._VA_scores.xlsx, VB, ...).
Each lists every student, but a student is only "Graded" in the version they
took. Bonus exports are a single file.

For each export and each outcome it covers, a student earns 1 if their score
for that outcome is >= CUTOFF, else 0 (no submission = 0). The score is:
  - export covers one outcome: the Total Score column, or if there isn't one,
    the question columns added up
  - export covers several: question columns grouped by number, so 1.x is the
    first LO in the name, 2.x the second, ... (Total Score is never used)
Outcome totals add up across all exports, capped at MAX_SCORE. Every export
ever given must stay in Data/, because totals are recomputed from all of them.

Writes <export>_master.xlsx for each export and final_grades.xlsx with totals.

Usage: python combine_scores.py
"""
import io
import re
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DATA = ROOT / "Data"
ID_COLS = ["First Name", "Last Name", "SID", "Email", "Sections"]
CUTOFF = 0.75
MAX_SCORE = 2  # outcome scores add up across exports, capped here
EXPECTED_VERSIONS = 4

# Export name -> (export id, outcomes it covers). Matching ignores case, and
# accepts spaces or hyphens where the downloads have underscores.
SEP = r"[_\s-]"
END = r"(?=[_\s.-]|$)"
NAME_PATTERNS = [
    (re.compile(rf"^LC{SEP}*(\d+){SEP}+LO{SEP}*(\d+(?:[_\s]\d+)*){END}", re.IGNORECASE),
     lambda m: (f"LC{m[1]}", [f"LO{n}" for n in re.split(r"[_\s]", m[2])])),
    (re.compile(rf"^CR{SEP}*(\d+){END}", re.IGNORECASE), lambda m: (f"CR{m[1]}", [f"CR{m[1]}"])),
    (re.compile(rf"^Bonus{SEP}*LO{SEP}*(\d+){END}", re.IGNORECASE),
     lambda m: (f"Bonus_LO{m[1]}", [f"LO{m[1]}"])),
]
VERSION_FILE = re.compile(r"_V([A-Z])_scores\.(?:xlsx|csv)$", re.IGNORECASE)
QUESTION_GROUP = re.compile(r"^(\d+)\.\d+")
QUESTION_POINTS = re.compile(r"\(([\d.]+) pts\)$")


def is_zip(path):
    return path.is_file() and path.name.strip().lower().endswith(".zip")


def natural_key(text):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def find_exports(data_dir):
    """Return {export id: (outcomes, source path)} for everything in data_dir."""
    found, ignored = {}, []
    for path in sorted(data_dir.iterdir()):
        name = path.name.strip()  # stray spaces in a downloaded name are invisible in Finder
        if name.startswith((".", "~$")):
            continue
        if (not (path.is_dir() or Path(name).suffix.lower() in (".zip", ".xlsx", ".csv"))
                or "practice" in name.lower()):
            ignored.append(path.name)
            continue
        for pattern, parse in NAME_PATTERNS:
            match = pattern.match(name)
            if match:
                export_id, outcomes = parse(match)
                # Keyed by outcomes too: one LC can come as a separate file per LO.
                found.setdefault((export_id, tuple(outcomes)), []).append(path)
                break
        else:
            ignored.append(path.name)

    by_id = {}
    for (export_id, outcomes), sources in found.items():
        # A folder unzipped next to its own .zip is the same export.
        folders = {s.name.strip() for s in sources if s.is_dir()}
        sources = [s for s in sources if not (is_zip(s) and s.name.strip()[:-4].strip() in folders)]
        if len(sources) > 1:
            raise SystemExit(f"More than one export for {export_id} ({', '.join(outcomes)}) in "
                             f"{data_dir.name}/ (remove all but one): {', '.join(s.name for s in sources)}")
        by_id.setdefault(export_id, []).append((list(outcomes), sources[0]))

    exports = {}
    for export_id, parts in by_id.items():
        if len(parts) == 1:
            exports[export_id] = parts[0]
            continue
        # Several files for one LC, e.g. LC_4_-_LO_5 and LC_4_-_LO_6: each is its own
        # export, as long as no outcome is covered twice.
        seen = {}
        for outcomes, source in parts:
            for outcome in outcomes:
                if outcome in seen:
                    raise SystemExit(f"{outcome} for {export_id} is in more than one export (remove all "
                                     f"but one): {seen[outcome].name}, {source.name}")
                seen[outcome] = source
            exports[f"{export_id}_{'_'.join(outcomes)}"] = (outcomes, source)
    if ignored:
        # Quoted so stray spaces or odd characters in a name are visible.
        print("Ignored (name not recognised or contains 'practice'):")
        for name in ignored:
            print(f"  {name!r}")
        print()
    return dict(sorted(exports.items(), key=lambda kv: natural_key(kv[0])))


def is_score_file(name):
    base = name.rsplit("/", 1)[-1]
    return (base.lower().endswith((".xlsx", ".csv"))
            and not base.startswith(("~$", "._")) and "__MACOSX" not in name)


def score_files(source):
    """{file name: raw bytes} for the spreadsheets in a folder, .zip, or single file."""
    if source.is_dir():
        return {p.name: p.read_bytes() for p in sorted(source.rglob("*"))
                if p.is_file() and is_score_file(str(p.relative_to(source)))}
    if is_zip(source):
        with zipfile.ZipFile(source) as z:
            return {n.rsplit("/", 1)[-1]: z.read(n) for n in sorted(z.namelist()) if is_score_file(n)}
    return {source.name: source.read_bytes()}


def read_table(name, raw):
    buf = io.BytesIO(raw)
    return pd.read_csv(buf) if name.lower().endswith(".csv") else pd.read_excel(buf)


def load_versions(export_id, source):
    """One DataFrame per test version (a single "-" version for bonus exports)."""
    files = score_files(source)
    versions = {VERSION_FILE.search(n)[1].upper(): n for n in files if VERSION_FILE.search(n)}
    if versions:
        if len(versions) != EXPECTED_VERSIONS:
            print(f"  WARNING: {export_id} has {len(versions)} versions ({', '.join(sorted(versions))}), "
                  f"expected {EXPECTED_VERSIONS}")
    elif len(files) == 1:
        versions = {"-": next(iter(files))}
    else:
        raise SystemExit(f"{export_id}: can't tell which file(s) to use in {source.name}: {sorted(files)}")

    frames = {}
    for version, name in sorted(versions.items()):
        df = read_table(name, files[name])
        missing = [c for c in ID_COLS if c not in df.columns]
        if missing:
            raise SystemExit(f"{export_id} / {name}: missing columns {missing}")
        if "Total Score" not in df.columns and not question_cols(df):
            raise SystemExit(f"{export_id} / {name}: no Total Score column and no question columns "
                             f"(headers ending in '(… pts)') to add up")
        df["Version"] = version
        frames[name] = df
    return frames


def question_cols(df):
    return [c for c in df.columns if c.endswith("pts)")]


def points_possible(cols):
    return round(sum(float(QUESTION_POINTS.search(c)[1]) for c in cols), 4)


def outcome_scores(export_id, name, df, outcomes):
    """Each outcome's score for every row of one version file, as a DataFrame.

    One outcome: Total Score if the file has it, otherwise the question columns
    added up. Several outcomes: question columns grouped by number.
    """
    questions = question_cols(df)
    if len(outcomes) == 1:
        if "Total Score" in df.columns:
            if "Max Points" in df.columns and not (df["Max Points"].dropna() == 1).all():
                raise SystemExit(f"{export_id} / {name}: Total Score is out of "
                                 f"{sorted(df['Max Points'].dropna().unique().tolist())}, expected 1")
            return pd.DataFrame({outcomes[0]: df["Total Score"]})
        if points_possible(questions) != 1:
            raise SystemExit(f"{export_id} / {name}: no Total Score column, and the question columns are "
                             f"worth {points_possible(questions)} points in total, expected 1")
        return pd.DataFrame({outcomes[0]: df[questions].sum(axis=1, min_count=1)})

    groups = {}
    for col in questions:
        match = QUESTION_GROUP.match(col)
        if not match:
            raise SystemExit(f"{export_id} / {name}: covers {', '.join(outcomes)} but question "
                             f"{col!r} isn't numbered like 1.1, 2.1 so it can't be assigned to one")
        groups.setdefault(int(match[1]), []).append(col)
    if len(groups) != len(outcomes):
        raise SystemExit(f"{export_id} / {name}: covers {len(outcomes)} outcomes ({', '.join(outcomes)}) "
                         f"but has {len(groups)} question groups ({', '.join(map(str, sorted(groups)))})")

    scores = {}
    for outcome, number in zip(outcomes, sorted(groups)):
        cols = groups[number]
        possible = points_possible(cols)
        if possible != 1:
            raise SystemExit(f"{export_id} / {name}: questions {number}.x ({outcome}) are worth "
                             f"{possible} points in total, expected 1")
        scores[outcome] = df[cols].sum(axis=1, min_count=1)
    return pd.DataFrame(scores)


def is_graded(export_id, name, df, score_cols):
    if "Status" not in df.columns:
        return df[score_cols].notna().any(axis=1)
    other = set(df["Status"].dropna()) - {"Graded", "Missing"}
    if other:
        print(f"  WARNING: {export_id} / {name}: status {sorted(other)} counted as no submission")
    return df["Status"] == "Graded"


def combine(export_id, outcomes, source, out_dir):
    graded_frames, all_rows = [], []
    for name, df in load_versions(export_id, source).items():
        scores = outcome_scores(export_id, name, df, outcomes)
        score_cols = [f"{o} Score" for o in outcomes]
        df[score_cols] = scores.to_numpy()
        graded = df[is_graded(export_id, name, df, score_cols)]
        graded_frames.append(graded)
        all_rows.append(df)
    all_rows = pd.concat(all_rows, ignore_index=True)
    graded = pd.concat(graded_frames, ignore_index=True)

    dupes = graded["SID"][graded["SID"].duplicated()]
    if not dupes.empty:
        raise SystemExit(f"{export_id}: students graded in more than one version: {dupes.tolist()}")

    for outcome in outcomes:
        # Round so float noise (e.g. 0.25 * 3) doesn't fall just under the cutoff.
        graded[outcome] = (graded[f"{outcome} Score"].round(4) >= CUTOFF).astype(int)

    # One row per student, including those who never submitted.
    questions = question_cols(all_rows)
    keep = ["SID", "Version", *questions, *(c for o in outcomes for c in (f"{o} Score", o))]
    master = all_rows[ID_COLS].drop_duplicates("SID").merge(graded[keep], on="SID", how="left")
    master["Version"] = master["Version"].fillna("Missing")
    master[outcomes] = master[outcomes].fillna(0).astype(int)
    master = master.sort_values(["Sections", "Last Name", "First Name"])
    master.to_excel(out_dir / f"{export_id}_master.xlsx", index=False)

    n_missing = (master["Version"] == "Missing").sum()
    summary = ", ".join(f"{o}: {master[o].sum()} x 1" for o in outcomes)
    print(f"{export_id} ({source.name}): {len(master)} students, {n_missing} no submission; {summary}")
    return master


def final_grades(masters, exports, out_dir):
    """Add up each outcome across exports, capped at MAX_SCORE."""
    roster = pd.concat([m[ID_COLS] for m in masters.values()]).drop_duplicates("SID")
    final = roster
    for export_id, master in masters.items():
        outcomes = exports[export_id][0]
        final = final.merge(master[["SID", *outcomes]].rename(columns={o: f"{export_id} {o}" for o in outcomes}),
                            on="SID", how="left")
    # A student missing from an export's roster (e.g. enrolled later) earned nothing from it.
    contrib_cols = [c for c in final.columns if c not in ID_COLS]
    final[contrib_cols] = final[contrib_cols].fillna(0).astype(int)

    all_outcomes = sorted({o for outcomes, _ in exports.values() for o in outcomes}, key=natural_key)
    for outcome in all_outcomes:
        sources = [c for c in contrib_cols if c.endswith(f" {outcome}")]
        final[outcome] = final[sources].sum(axis=1).clip(upper=MAX_SCORE)

    final = final.sort_values(["Sections", "Last Name", "First Name"])
    final.to_excel(out_dir / "final_grades.xlsx", index=False)

    print(f"\nfinal_grades.xlsx: {len(final)} students")
    for outcome in all_outcomes:
        counts = final[outcome].value_counts().sort_index()
        print(f"  {outcome}: " + ", ".join(f"{n} x {score}" for score, n in counts.items()))
    return final


def main(data_dir=None, out_dir=None):
    data_dir, out_dir = data_dir or DATA, out_dir or ROOT
    exports = find_exports(data_dir)
    if not exports:
        raise SystemExit(f"No exports found in {data_dir}")
    masters = {eid: combine(eid, outcomes, source, out_dir) for eid, (outcomes, source) in exports.items()}
    return final_grades(masters, exports, out_dir)


if __name__ == "__main__":
    main()
