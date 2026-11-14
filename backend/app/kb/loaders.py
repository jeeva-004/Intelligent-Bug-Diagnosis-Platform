"""Readers for the Kaggle datasets. Output is standardised DefectRecord objects (uncleaned).

Apache  : Issues.csv + Comments.csv + Issuelinks.csv
Mozilla : mozilla_bug_report_data.csv
Eclipse : eclipse_bug_report_data.csv
"""
import random
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from .records import CommentRecord, DefectRecord

Log = Callable[[str], None]
CHUNKSIZE = 100_000


def find_file(data_dir: Path, name: str) -> Path | None:
    """Find a file by name (case-insensitive) anywhere under data_dir."""
    wanted = name.lower()
    for path in Path(data_dir).rglob("*"):
        if path.is_file() and path.name.lower() == wanted:
            return path
    return None


def _s(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _dt(value) -> datetime | None:
    if _s(value) is None:
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_convert(None).to_pydatetime()


def _header(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0, encoding="utf-8", encoding_errors="replace").columns)


def _require(path: Path, required: list[str]) -> None:
    missing = [c for c in required if c not in _header(path)]
    if missing:
        raise ValueError(f"{path.name} is missing expected columns: {', '.join(missing)}")


def _read(path: Path, columns: list[str], chunksize: int = CHUNKSIZE):
    wanted = set(columns)
    return pd.read_csv(
        path,
        usecols=lambda c: c in wanted,
        dtype=str,
        chunksize=chunksize,
        encoding="utf-8",
        encoding_errors="replace",
    )


# ---------------------------------------------------------------- Apache
def load_apache(
    data_dir: Path,
    sample_size: int,
    duplicate_pairs: int,
    seed: int = 42,
    log: Log = print,
) -> list[DefectRecord]:
    issues = find_file(data_dir, "Issues.csv")
    if issues is None:
        log("Apache: Issues.csv not found, skipping Apache.")
        return []
    _require(issues, ["key", "summary", "description", "issuetype.name", "statusCategory.key"])
    rng = random.Random(seed)

    # Pass 1 (light columns only): which issues are eligible? Bugs that are done (resolved/closed).
    eligible: list[str] = []
    type_counts: dict[str, int] = {}
    for chunk in _read(issues, ["key", "issuetype.name", "statusCategory.key"]):
        for kind, n in chunk["issuetype.name"].fillna("(blank)").value_counts().items():
            type_counts[kind] = type_counts.get(kind, 0) + int(n)
        mask = (chunk["issuetype.name"].str.lower() == "bug") & (chunk["statusCategory.key"].str.lower() == "done")
        eligible.extend(chunk.loc[mask, "key"].dropna().tolist())
    log(f"Apache: {len(eligible):,} eligible issues (issue type 'Bug', status category 'done').")
    if not eligible:
        top = sorted(type_counts.items(), key=lambda kv: -kv[1])[:8]
        raise ValueError(f"Apache: no eligible issues found. Issue types seen: {top}")
    eligible_set = set(eligible)

    # Duplicate links: "X duplicates Y" gives duplicate_of[X] = Y.
    duplicate_of: dict[str, str] = {}
    links = find_file(data_dir, "Issuelinks.csv")
    if links is None:
        log("Apache: Issuelinks.csv not found, duplicate links will be empty.")
    else:
        _require(links, ["key", "type.name", "outwardIssue.key"])
        type_names: set[str] = set()
        for chunk in _read(links, ["key", "type.name", "outwardIssue.key"]):
            dup = chunk[chunk["type.name"].fillna("").str.lower().str.contains("duplicate")]
            type_names.update(dup["type.name"].dropna().unique().tolist())
            for key, original in zip(dup["key"], dup["outwardIssue.key"]):
                if isinstance(key, str) and isinstance(original, str):
                    duplicate_of[key] = original
        log(f"Apache: duplicate link types found: {sorted(type_names) or 'none'}; {len(duplicate_of):,} duplicate links.")

    # Sample: duplicate pairs first (so retrieval can be tested), then random fill.
    if sample_size <= 0 or sample_size >= len(eligible):
        selected = set(eligible)
    else:
        pairs = [(a, b) for a, b in duplicate_of.items() if a in eligible_set and b in eligible_set]
        rng.shuffle(pairs)
        selected: set[str] = set()
        for a, b in pairs[:duplicate_pairs]:
            selected.update((a, b))
        selected = set(list(selected)[:sample_size])
        rest = [k for k in eligible if k not in selected]
        selected.update(rng.sample(rest, min(sample_size - len(selected), len(rest))))
    log(f"Apache: sampling {len(selected):,} issues.")

    # Pass 2: read full rows for the selected issues only.
    columns = ["key", "summary", "description", "project.name", "priority.name", "status.name",
               "resolution.name", "created", "resolutiondate"]
    records: dict[str, DefectRecord] = {}
    for chunk in _read(issues, columns):
        for row in chunk[chunk["key"].isin(selected)].to_dict("records"):
            key = row["key"]
            records[key] = DefectRecord(
                source="apache",
                source_bug_id=key,
                project=_s(row.get("project.name")),
                title=_s(row.get("summary")),
                description=_s(row.get("description")),
                status=_s(row.get("status.name")),
                resolution=_s(row.get("resolution.name")),
                priority=_s(row.get("priority.name")),
                duplicate_of=duplicate_of.get(key),
                created_at=_dt(row.get("created")),
                resolved_at=_dt(row.get("resolutiondate")),
            )

    comments_file = find_file(data_dir, "Comments.csv")
    if comments_file is None:
        log("Apache: Comments.csv not found, comments and resolution text will be empty.")
    else:
        _require(comments_file, ["key", "comment.body"])
        known_keys = list(records)
        by_key: dict[str, list[CommentRecord]] = {}
        for chunk in _read(comments_file, ["key", "comment.body", "comment.created"]):
            for row in chunk[chunk["key"].isin(known_keys)].to_dict("records"):
                body = _s(row.get("comment.body"))
                if body:
                    by_key.setdefault(row["key"], []).append(
                        CommentRecord(text=body, created_at=_dt(row.get("comment.created")))
                    )
        for key, comments in by_key.items():
            comments.sort(key=lambda c: c.created_at or datetime.min)
            records[key].comments = comments
            # Heuristic: the last comment on a resolved issue is the closing note / fix explanation.
            rec = records[key]
            if rec.resolved_at or rec.resolution:
                rec.resolution_text = comments[-1].text
    return list(records.values())


# ---------------------------------------------------------------- Mozilla / Eclipse
def load_bugzilla_csv(
    data_dir: Path,
    filename: str,
    source: str,
    sample_size: int = 0,
    seed: int = 42,
    log: Log = print,
) -> list[DefectRecord]:
    path = find_file(data_dir, filename)
    if path is None:
        log(f"{source.title()}: {filename} not found, skipping.")
        return []
    _require(path, ["bug_id", "short_description", "long_description"])
    columns = ["bug_id", "creation_date", "component_name", "product_name", "short_description",
               "long_description", "resolution_category", "status_category", "resolution_date",
               "severity_category"]
    frames = list(_read(path, columns))
    df = pd.concat(frames, ignore_index=True)
    log(f"{source.title()}: {len(df):,} rows read from {path.name}.")
    if sample_size and len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=seed)
    records = []
    for row in df.to_dict("records"):
        bug_id = _s(row.get("bug_id"))
        if bug_id is None:
            continue
        records.append(
            DefectRecord(
                source=source,
                source_bug_id=bug_id,
                project=_s(row.get("product_name")),
                component=_s(row.get("component_name")),
                title=_s(row.get("short_description")),
                description=_s(row.get("long_description")),
                status=_s(row.get("status_category")),
                resolution=_s(row.get("resolution_category")),
                severity=_s(row.get("severity_category")),
                created_at=_dt(row.get("creation_date")),
                resolved_at=_dt(row.get("resolution_date")),
            )
        )
    return records
