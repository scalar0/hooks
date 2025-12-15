#!/usr/bin/env python3
"""Conventional commit message validator for git commit-msg hook."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List

ALLOWED_TYPES = {"feat", "fix", "refactor", "fmt", "test", "docs", "build", "chore"}
HEADER_RE = re.compile(r"^([a-z]+)(\(([A-Za-z0-9/-]+)\))?(!)?:\s*(.+)$")
FOOTER_RE = re.compile(r"^(BREAKING CHANGE|[A-Za-z-]+):\s")
DIFF_RE = re.compile(r"^(diff --git |\+\+\+ |--- |@@ )", re.MULTILINE)
IGNORE_MARKER_RE = re.compile(r"\s*-+\s+IGNORE\s*-+", re.MULTILINE)
INVALID_SUBJECT_CHARS_RE = re.compile(r"^[a-z0-9 \-_/():,#+]*$")


def fail(*reasons: str) -> None:
    """Print an error and exit non-zero."""
    print("commit message validation failed:", file=sys.stderr)
    for reason in reasons:
        print(f"  - {reason}", file=sys.stderr)
    print("\nExpected header: <type>(<scope>)!: <subject>", file=sys.stderr)
    print("Where:", file=sys.stderr)
    print(
        "  - type one of: feat|fix|refactor|fmt|test|docs|build|chore", file=sys.stderr
    )
    print("  - scope (optional) matches ^[A-Za-z0-9/-]+$", file=sys.stderr)
    print(
        "  - ! (optional) indicates breaking change and REQUIRES a 'BREAKING CHANGE:' footer",
        file=sys.stderr,
    )
    print(
        "  - subject: 1-50 chars, lowercase start, allowed: [a-z0-9 \\ -_/():,#+], no trailing .",
        file=sys.stderr,
    )
    print("\nBody (optional): lines wrapped to <= 72 chars.", file=sys.stderr)
    print(
        "Footers (optional): one trailer per line, e.g. 'BREAKING CHANGE: ...'",
        file=sys.stderr,
    )
    print("\nExamples:", file=sys.stderr)
    print("  feat(cli): add terse output flag", file=sys.stderr)
    print("  fix: handle empty input without panic", file=sys.stderr)
    sys.exit(1)


def normalize_message(msg_path: Path) -> List[str]:
    """Normalize CRLF, drop template lines, and rewrite the message file."""
    raw = msg_path.read_text(encoding="utf-8", errors="replace")
    # Normalize newlines
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for line in raw.split("\n"):
        if re.match(r"^[\s]*#", line):
            continue
        if re.match(r"^\$", line):
            continue
        if re.match(r"^\[\$", line):
            continue
        lines.append(line)

    # Rewrite sanitized message back to disk with trailing newline
    sanitized = "\n".join(lines)
    if not sanitized.endswith("\n"):
        sanitized = sanitized + "\n"
    msg_path.write_text(sanitized, encoding="utf-8")
    return lines


def find_header(lines: List[str]) -> tuple[str, int]:
    """Return (header, index) or fail if none."""
    for idx, line in enumerate(lines):
        if line.strip():
            return line, idx
    fail("empty commit message")
    raise AssertionError("unreachable")


def collect_footers(lines: List[str], start_idx: int) -> tuple[List[str], int]:
    """Collect footer lines and return (footers, first_footer_idx)."""
    first_footer_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            continue
        if FOOTER_RE.match(line):
            first_footer_idx = i
            continue
        break
    footers = [l for l in lines[first_footer_idx:] if l.strip()]
    return footers, first_footer_idx


def validate_header(header: str) -> tuple[str, str, str, str]:
    match = HEADER_RE.match(header)
    if not match:
        fail("header must match '<type>(<scope>)!: <subject>'")
    type_, scope, bang, subject = (
        match.group(1),
        match.group(3) or "",
        match.group(4) or "",
        match.group(5),
    )

    if type_ not in ALLOWED_TYPES:
        fail(f"invalid type '{type_}'")

    if scope and not re.fullmatch(r"[A-Za-z0-9/-]+", scope):
        fail(f"scope '{scope}' must match ^[A-Za-z0-9/-]+$")

    subject_len = len(subject)
    if subject_len < 1 or subject_len > 50:
        fail(f"subject must be 1-50 chars (got {subject_len})")
    if subject.endswith("."):
        fail("subject must not end with a period")
    if not subject or not subject[0].islower():
        fail("subject must start with a lowercase letter")
    if not INVALID_SUBJECT_CHARS_RE.match(subject):
        fail("subject contains invalid characters; allowed: [a-z0-9 -_/():,#+]")
    if "!" in subject:
        fail("subject contains invalid characters; '!' is not allowed")

    return type_, scope, bang, subject


def validate_body(lines: List[str], header_idx: int, first_footer_idx: int) -> None:
    for i in range(header_idx + 1, first_footer_idx):
        line = lines[i]
        if not line.strip():
            continue
        if len(line) > 72:
            fail(f"body line {i + 1} exceeds 72 chars")


def main(argv: Iterable[str]) -> None:
    args = list(argv)
    if not args:
        print(
            "commit-msg: message file not provided or does not exist", file=sys.stderr
        )
        sys.exit(1)
    msg_path = Path(args[0])
    if not msg_path.exists():
        print(
            "commit-msg: message file not provided or does not exist", file=sys.stderr
        )
        sys.exit(1)

    lines = normalize_message(msg_path)
    header, header_idx = find_header(lines)

    # Bypass certain auto-generated messages
    if header.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")):
        return

    sanitized_text = "\n".join(lines)
    if DIFF_RE.search(sanitized_text):
        fail("commit message appears to contain a raw diff; remove patch content")
    if IGNORE_MARKER_RE.search(sanitized_text):
        fail("commit message contains forbidden internal markers")

    _, _, bang, _ = validate_header(header)

    footers, first_footer_idx = collect_footers(lines, header_idx)

    if bang:
        has_breaking = any(f.startswith("BREAKING CHANGE: ") for f in footers)
        if not has_breaking:
            fail(
                "'!' in header requires a 'BREAKING CHANGE:' footer explaining the change"
            )

    validate_body(lines, header_idx, first_footer_idx)


if __name__ == "__main__":
    main(sys.argv[1:])
