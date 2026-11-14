import csv
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal
from app.kb.build import build_knowledge_base
from app.kb.chunking import build_chunks, split_text
from app.kb.cleaning import clean_record, clean_text, extract_stack_traces
from app.kb.embedder import HashEmbedder
from app.kb.evaluate import evaluate
from app.kb.records import CommentRecord, DefectRecord
from app.kb.retrieval import search_similar
from app.kb.vector_store import VectorStore
from app.models import DefectComment, HistoricalDefect

JAVA_TRACE = (
    "java.lang.NullPointerException: value is null\n"
    "\tat org.apache.foo.Bar.save(Bar.java:42)\n"
    "\tat org.apache.foo.Main.run(Main.java:10)\n"
    "Caused by: java.io.IOException: disk full\n"
    "\tat org.apache.io.Disk.write(Disk.java:7)\n"
    "\t... 5 more"
)


# ---------------------------------------------------------------- cleaning
def test_clean_text_normalises_and_removes_jira_markup():
    raw = "h2. Problem\r\nThe job fails.   \r\n\r\n\r\n\r\n{code:java}\r\nint x;\r\n{code}\r\nping [~bob] !shot.png!\x00"
    out = clean_text(raw, jira_markup=True)
    assert "\r" not in out and "\x00" not in out
    assert "{code" not in out and "[~bob]" not in out and "shot.png" not in out
    assert "h2." not in out
    assert "\n\n\n" not in out


def test_extract_java_trace_keeps_header_and_causes():
    text = "The save button crashes the app.\n" + JAVA_TRACE + "\nHappens every time."
    remaining, trace = extract_stack_traces(text)
    assert "NullPointerException" in trace and "Caused by: java.io.IOException" in trace
    assert "... 5 more" in trace
    assert "save button" in remaining and "every time" in remaining
    assert "Bar.java" not in remaining


def test_extract_python_trace():
    text = "Crash on start\nTraceback (most recent call last):\n  File \"a.py\", line 3, in <module>\n    run()\nValueError: bad value\nThanks"
    remaining, trace = extract_stack_traces(text)
    assert trace.startswith("Traceback") and trace.endswith("ValueError: bad value")
    assert remaining == "Crash on start\nThanks"


def test_prose_with_at_is_not_a_stack_trace():
    text = "The app is slow at startup.\nat the moment I wait about ten seconds."
    remaining, trace = extract_stack_traces(text)
    assert trace == "" and remaining == text


def test_clean_record_drops_short_descriptions_and_splits_trace():
    short = DefectRecord(source="mozilla", source_bug_id="1", title="t", description="too short")
    assert clean_record(short, 20) is None
    rec = DefectRecord(source="mozilla", source_bug_id="2", title=" Crash ", description="Crash when saving a file.\n" + JAVA_TRACE)
    out = clean_record(rec, 20)
    assert out.title == "Crash" and "NullPointerException" in out.stack_trace
    assert "Bar.java" not in out.description


# ---------------------------------------------------------------- chunking
def test_split_text_respects_size_and_covers_text():
    text = " ".join(f"word{i}" for i in range(600))
    parts = split_text(text, 500, 50)
    assert len(parts) > 1 and all(len(p) <= 500 for p in parts)
    assert parts[0].startswith("word0") and parts[-1].endswith("word599")


def test_build_chunks_types_ids_and_metadata():
    rec = DefectRecord(
        source="apache", source_bug_id="HADOOP-1", project="Hadoop", title="Write fails",
        description="Writing to HDFS fails with an IO error after restart.", stack_trace=JAVA_TRACE,
        resolution="Fixed", resolution_text="Fixed by closing the stream before the rename.",
        comments=[CommentRecord("short"), CommentRecord("I can reproduce this on version 2.7 with the default settings."),
                  CommentRecord("Fixed by closing the stream before the rename.")],
    )
    chunks = build_chunks(7, rec, 1000, 150)
    kinds = [c.metadata["chunk_type"] for c in chunks]
    assert kinds == ["description", "stack_trace", "resolution", "comment"]
    assert chunks[0].id == "7:description:0" and chunks[0].text.startswith("Write fails")
    assert chunks[0].metadata["source"] == "apache" and chunks[0].metadata["defect_id"] == 7
    assert all(v is not None for c in chunks for v in c.metadata.values())


# ---------------------------------------------------------------- pipeline + retrieval
TOPICS = [
    "connection pool exhausted when many threads open database sessions",
    "button label is cut off on high dpi display in the settings dialog",
    "memory leak in the image decoder after loading large png files",
    "kerberos ticket renewal fails for long running streaming jobs",
    "tab strip flickers when dragging a tab to a new window",
    "compiler crashes on generic method with recursive type bound",
    "scheduler ignores priority queue weights under heavy load",
    "spell checker underlines correct words in german documents",
    "json parser throws on unicode escapes in object keys",
    "file watcher misses rename events on network shares",
    "ssl handshake times out behind corporate proxy",
    "undo history lost after switching editor perspective",
]


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: r.get(h, "") for h in header})


@pytest.fixture()
def dataset(tmp_path):
    root = tmp_path / "data" / "apache_zip"
    root.mkdir(parents=True)
    issue_cols = ["id", "key", "summary", "resolution.name", "priority.name", "labels", "status.name",
                  "statusCategory.key", "issuetype.name", "project.name", "created", "resolutiondate", "description"]
    issues, comments, links = [], [], []
    for i, topic in enumerate(TOPICS):
        issues.append({"key": f"APA-{i}", "summary": f"Bug {i}: {topic}", "issuetype.name": "Bug",
                       "statusCategory.key": "done", "status.name": "Resolved", "resolution.name": "Fixed",
                       "priority.name": "Major", "project.name": "Apache Demo", "created": "2020-01-0%dT10:00:00.000+0000" % (i % 9 + 1),
                       "resolutiondate": "2020-02-01T10:00:00.000+0000",
                       "description": f"h2. Problem\n{topic}. This happens regularly in production.\n{{code}}\n{JAVA_TRACE}\n{{code}}"})
        comments.append({"key": f"APA-{i}", "comment.body": f"I can confirm that {topic} on the latest build.", "comment.created": "2020-01-10T10:00:00.000+0000"})
        comments.append({"key": f"APA-{i}", "comment.body": f"Fixed by patching the code path behind: {topic}.", "comment.created": "2020-01-20T10:00:00.000+0000"})
    # duplicates of the first four bugs, worded a little differently
    for i in range(4):
        issues.append({"key": f"APA-D{i}", "summary": f"Again: {TOPICS[i]}", "issuetype.name": "Bug",
                       "statusCategory.key": "done", "status.name": "Closed", "resolution.name": "Duplicate",
                       "priority.name": "Minor", "project.name": "Apache Demo", "created": "2020-03-01T10:00:00.000+0000",
                       "description": f"Seeing this again, {TOPICS[i]}, in our test cluster after the upgrade."})
        links.append({"key": f"APA-D{i}", "type.name": "Duplicate", "outwardIssue.key": f"APA-{i}"})
        links.append({"key": f"APA-{i}", "type.name": "Duplicate", "inwardIssue.key": f"APA-D{i}"})
    issues.append({"key": "APA-FEAT", "summary": "Add a feature", "issuetype.name": "New Feature", "statusCategory.key": "done", "description": "A feature request that is long enough."})
    issues.append({"key": "APA-OPEN", "summary": "Open bug", "issuetype.name": "Bug", "statusCategory.key": "new", "description": "An unresolved bug that is long enough."})
    _write_csv(root / "Issues.csv", issue_cols, issues)
    _write_csv(root / "Comments.csv", ["key", "comment.id", "comment.body", "comment.created"], comments)
    _write_csv(root / "Issuelinks.csv", ["key", "type.name", "inwardIssue.key", "outwardIssue.key"], links)

    moz_cols = ["bug_id", "creation_date", "component_name", "product_name", "short_description", "long_description",
                "resolution_category", "status_category", "resolution_date", "severity_category"]
    moz = [{"bug_id": 100 + i, "creation_date": "2015-05-01 10:00:00", "component_name": "Tabbed Browser",
            "product_name": "Firefox", "short_description": TOPICS[4].title() if i == 0 else f"Other issue {i}",
            "long_description": f"{TOPICS[4]}. Steps to reproduce: drag a tab out of the strip." if i == 0 else "Something unrelated to the topics above entirely, about audio playback glitches.",
            "resolution_category": "FIXED", "status_category": "RESOLVED", "severity_category": "normal"} for i in range(3)]
    moz.append({"bug_id": 999, "short_description": "x", "long_description": "tiny"})  # dropped: description too short
    _write_csv(tmp_path / "data" / "mozilla_bug_report_data.csv", moz_cols, moz)
    _write_csv(tmp_path / "data" / "eclipse_bug_report_data.csv", moz_cols,
               [{"bug_id": 5, "component_name": "UI", "product_name": "Platform", "short_description": TOPICS[11],
                 "long_description": f"{TOPICS[11]} and it happens every time I change perspective.", "resolution_category": "FIXED"}])
    return tmp_path / "data"


def test_build_search_and_evaluate(dataset, tmp_path):
    store = VectorStore(tmp_path / "chroma_test", "test_defects", "hash")
    embedder = HashEmbedder()
    summary = build_knowledge_base(dataset, reset=True, apache_sample=0, store=store, embedder=embedder, log=lambda m: None)

    # 12 bugs + 4 duplicates (Apache), 3 Mozilla (the 4th row is too short), 1 Eclipse; the feature request and open bug are excluded
    assert summary["by_source"] == {"apache": 16, "mozilla": 3, "eclipse": 1}
    assert summary["index_count"] == summary["chunks"] > 19

    with SessionLocal() as s:
        dup = s.scalar(select(HistoricalDefect).where(HistoricalDefect.source_bug_id == "APA-D2"))
        assert dup.duplicate_of == "APA-2" and dup.resolution == "Duplicate"
        original = s.scalar(select(HistoricalDefect).where(HistoricalDefect.source_bug_id == "APA-3"))
        assert "NullPointerException" in original.stack_trace and "Bar.java" not in original.description
        assert original.resolution_text.startswith("Fixed by patching")
        assert s.scalar(select(func.count()).select_from(DefectComment)) == 24

        # semantic search finds the right defect first, and can filter by source
        hits = search_similar("tab strip flickering while dragging a tab into another window", s, store, embedder, top_k=3)
        assert hits[0].source_bug_id in {"APA-4", "100"} and 0 < hits[0].score <= 1
        only_moz = search_similar("dragging a tab", s, store, embedder, top_k=5, source="mozilla")
        assert only_moz and all(h.source == "mozilla" for h in only_moz)
        assert search_similar("   ", s, store, embedder) == []

        # known duplicates are retrieved
        report = evaluate(s, store, embedder, max_pairs=50)
        assert report["pairs"] == 4 and report["recall@5"] == 1.0


def test_build_refuses_to_overwrite_without_reset(dataset, tmp_path):
    store = VectorStore(tmp_path / "chroma_test2", "test_defects", "hash")
    kwargs = dict(apache_sample=0, store=store, embedder=HashEmbedder(), log=lambda m: None)
    build_knowledge_base(dataset, reset=True, **kwargs)
    with pytest.raises(SystemExit):
        build_knowledge_base(dataset, reset=False, **kwargs)


def test_missing_dataset_folder(tmp_path):
    with pytest.raises(SystemExit):
        build_knowledge_base(tmp_path, reset=True, store=VectorStore(tmp_path / "c", "test_defects", "hash"),
                             embedder=HashEmbedder(), log=lambda m: None)
