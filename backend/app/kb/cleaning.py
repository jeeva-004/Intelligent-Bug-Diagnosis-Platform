"""Cleaning and standardisation of historical bug reports.

Steps (see docs/M1.4-knowledge-base.md):
1. Normalise text: line endings, control characters, Jira markup, blank-line runs.
2. Drop records whose description is shorter than MIN_DESCRIPTION_CHARS.
3. Separate stack traces from the description so each can be chunked on its own.
"""
import re

from .records import CommentRecord, DefectRecord

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_JIRA_BLOCKS = re.compile(r"\{(?:code|noformat|quote|panel)(?::[^}]*)?\}", re.IGNORECASE)
_JIRA_MENTION = re.compile(r"\[~[^\]]+\]")
_JIRA_IMAGE = re.compile(r"![^\s!|]+\.(?:png|jpe?g|gif|bmp)(?:\|[^!]*)?!", re.IGNORECASE)
_JIRA_HEADING = re.compile(r"(?m)^h[1-6]\.\s+")
_BLANK_RUNS = re.compile(r"\n{3,}")


def clean_text(value: str | None, jira_markup: bool = False) -> str:
    if not value:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    if jira_markup:
        text = _JIRA_BLOCKS.sub("\n", text)
        text = _JIRA_MENTION.sub("", text)
        text = _JIRA_IMAGE.sub("", text)
        text = _JIRA_HEADING.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_RUNS.sub("\n\n", text)
    return text.strip()


# ---- stack trace extraction ----
_FRAME = re.compile(
    r"^\s*at\s+[^\s(][^()]*\(.*\)\s*$"  # Java:  at pkg.Class.method(File.java:10)
    r"|^\s*at\s+\S+\s+\(?.*:\d+(?::\d+)?\)?\s*$"  # JavaScript:  at fn (file.js:10:5)
    r"|^\s*#\d+\s+0x[0-9a-fA-F]+\b"  # gdb / C++:  #0 0x0000 in fn ()
)
_EXC_HEADER = re.compile(
    r'^\s*(?:Exception in thread "[^"]*"\s+)?(?:[\w$]+\.)+[\w$]*(?:Exception|Error|Throwable)\b.*$'
    r"|^\s*[\w$]*(?:Exception|Error)\s*:.*$"
    r"|^\s*Caused by:.*$"
)
_CAUSED = re.compile(r"^\s*Caused by:.*$")
_MORE = re.compile(r"^\s*\.\.\.\s*\d+\s+(?:more|common frames omitted).*$")
_PY_START = re.compile(r"^\s*Traceback \(most recent call last\):\s*$")


def extract_stack_traces(text: str) -> tuple[str, str]:
    """Split text into (text without stack traces, stack traces joined by blank lines)."""
    lines = text.split("\n")
    kept: list[str] = []
    blocks: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if _PY_START.match(line):
            j = i + 1
            while j < n and lines[j][:1] in (" ", "\t"):
                j += 1
            if j < n and lines[j].strip():
                j += 1  # the final "SomeError: message" line
            blocks.append("\n".join(lines[i:j]))
            i = j
            continue
        if _FRAME.match(line):
            j, frames = i, 0
            while j < n:
                if _FRAME.match(lines[j]):
                    frames += 1
                elif _CAUSED.match(lines[j]) or _MORE.match(lines[j]):
                    pass
                elif _EXC_HEADER.match(lines[j]) and j + 1 < n and _FRAME.match(lines[j + 1]):
                    pass
                else:
                    break
                j += 1
            if frames >= 2:
                block = lines[i:j]
                if kept and _EXC_HEADER.match(kept[-1]):
                    block = [kept.pop()] + block
                blocks.append("\n".join(block))
                i = j
                continue
        kept.append(line)
        i += 1
    remaining = _BLANK_RUNS.sub("\n\n", "\n".join(kept)).strip()
    return remaining, "\n\n".join(blocks).strip()


def clean_record(rec: DefectRecord, min_description_chars: int) -> DefectRecord | None:
    """Return the cleaned record, or None if it should be dropped."""
    jira = rec.source == "apache"
    title = clean_text(rec.title, jira)
    full_text = clean_text(rec.description, jira)
    if len(full_text) < min_description_chars:
        return None
    description, trace = extract_stack_traces(full_text)

    comments: list[CommentRecord] = []
    for c in rec.comments:
        text = clean_text(c.text, jira)
        if text:
            comments.append(CommentRecord(text=text, created_at=c.created_at))

    rec.title = title or None
    rec.description = description or None
    rec.stack_trace = trace or None
    rec.comments = comments
    rec.resolution_text = clean_text(rec.resolution_text, jira) or None
    for name in ("project", "component", "status", "resolution", "severity", "priority", "duplicate_of"):
        value = getattr(rec, name)
        setattr(rec, name, str(value).strip() or None if value is not None else None)
    return rec
