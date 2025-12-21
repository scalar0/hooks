#!/usr/bin/env python3
"""Conventional commit message validator for git commit-msg hook."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

ALLOWED_TYPES = frozenset(
    {"feat", "fix", "refactor", "fmt", "test", "docs", "build", "chore"}
)
AUTO_BYPASS_PREFIXES = ("Merge ", "Revert ", "fixup! ", "squash! ")
HEADER_RE = re.compile(r"^([a-z]+)(\(([^)]+)\))?(!)?:\s*(.+)$")
FOOTER_RE = re.compile(r"^(BREAKING CHANGE|[A-Za-z-]+):\s")
DIFF_RE = re.compile(r"^(diff --git |\+\+\+ |--- |@@ )", re.MULTILINE)
IGNORE_MARKER_RE = re.compile(r"\s*-+\s+IGNORE\s*-+", re.MULTILINE)
INVALID_SUBJECT_CHARS_RE = re.compile(r"^[a-z0-9 \-_/():,#+]*$")


class ValidationError(Exception):
    """Raised when a commit message violates validation rules."""

    def __init__(self, reasons: Sequence[str]):
        super().__init__("\n".join(reasons))
        self.reasons = tuple(reasons)


@dataclass(frozen=True)
class ParsedMessage:
    lines: List[str]
    header: str
    header_idx: int
    footers: List[str]
    first_footer_idx: int


def _error_summary(reasons: Sequence[str]) -> str:
    parts = ["commit message validation failed:"]
    parts.extend(f"  - {reason}" for reason in reasons)
    parts.extend(
        (
            "",
            "Expected header: <type>(<scope>)!: <subject>",
            "Where:",
            "  - type one of: feat|fix|refactor|fmt|test|docs|build|chore",
            "  - scope (optional) matches ^[A-Za-z0-9/-]+$",
            (
                "  - ! (optional) indicates breaking change and "
                "REQUIRES a 'BREAKING CHANGE:' footer"
            ),
            (
                "  - subject: 1-50 chars, lowercase start, allowed: "
                "[a-z0-9 \\ -_/():,#+], no trailing ."
            ),
            "",
            "Body (optional): lines wrapped to <= 72 chars.",
            "Footers (optional): one trailer per line, e.g. 'BREAKING CHANGE: ...'",
            "",
            "Examples:",
            "  feat(cli): add terse output flag",
            "  fix: handle empty input without panic",
        )
    )
    return "\n".join(parts)


def _raise_invalid(*reasons: str) -> None:
    raise ValidationError(list(reasons))


def normalize_message(msg_path: Path) -> List[str]:
    """Normalize CRLF, drop template lines, and rewrite the message file."""

    raw = msg_path.read_text(encoding="utf-8", errors="replace")
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")

    lines: list[str] = []
    for line in normalized.split("\n"):
        if re.match(r"^[\s]*#", line):
            continue
        if re.match(r"^\$", line):
            continue
        if re.match(r"^\[\$", line):
            continue
        lines.append(line)

    sanitized = "\n".join(lines)
    if not sanitized.endswith("\n"):
        sanitized = f"{sanitized}\n"
    msg_path.write_text(sanitized, encoding="utf-8")
    return lines


def find_header(lines: List[str]) -> tuple[str, int]:
    """Return (header, index) or raise if missing."""

    for idx, line in enumerate(lines):
        if line.strip():
            return line, idx
    _raise_invalid("empty commit message")
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
    footers = [line for line in lines[first_footer_idx:] if line.strip()]
    return footers, first_footer_idx


def validate_header(header: str) -> tuple[str, str, str, str]:
    match = HEADER_RE.match(header)
    if not match:
        _raise_invalid("header must match '<type>(<scope>)!: <subject>'")

    type_, scope, bang, subject = (
        match.group(1),
        match.group(3) or "",
        match.group(4) or "",
        match.group(5),
    )

    if type_ not in ALLOWED_TYPES:
        _raise_invalid(f"invalid type '{type_}'")

    if scope and not re.fullmatch(r"[A-Za-z0-9/-]+", scope):
        _raise_invalid(f"scope '{scope}' must match ^[A-Za-z0-9/-]+$")

    subject_len = len(subject)
    if subject_len < 1 or subject_len > 50:
        _raise_invalid(f"subject must be 1-50 chars (got {subject_len})")
    if subject.endswith("."):
        _raise_invalid("subject must not end with a period")
    if not subject or not subject[0].islower():
        _raise_invalid("subject must start with a lowercase letter")
    if not INVALID_SUBJECT_CHARS_RE.fullmatch(subject):
        _raise_invalid(
            "subject contains invalid characters; allowed: [a-z0-9 -_/():,#+]"
        )
    if "!" in subject:
        _raise_invalid("subject contains invalid characters; '!' is not allowed")

    return type_, scope, bang, subject


def validate_body(lines: List[str], header_idx: int, first_footer_idx: int) -> None:
    for i in range(header_idx + 1, first_footer_idx):
        line = lines[i]
        if not line.strip():
            continue
        if len(line) > 72:
            _raise_invalid(f"body line {i + 1} exceeds 72 chars")


def ensure_no_diff_or_ignore_markers(text: str) -> None:
    if IGNORE_MARKER_RE.search(text):
        _raise_invalid("commit message contains forbidden internal markers")
    if DIFF_RE.search(text):
        _raise_invalid(
            "commit message appears to contain a raw diff; remove patch content"
        )


def ensure_breaking_footer_if_needed(bang: str, footers: List[str]) -> None:
    if not bang:
        return
    if any(footer.startswith("BREAKING CHANGE: ") for footer in footers):
        return
    _raise_invalid(
        "'!' in header requires a 'BREAKING CHANGE:' footer explaining the change"
    )


def parse_message(msg_path: Path) -> ParsedMessage:
    lines = normalize_message(msg_path)
    header, header_idx = find_header(lines)
    footers, first_footer_idx = collect_footers(lines, header_idx)
    return ParsedMessage(lines, header, header_idx, footers, first_footer_idx)


def validate_commit_message(msg_path: Path) -> None:
    parsed = parse_message(msg_path)

    if parsed.header.startswith(AUTO_BYPASS_PREFIXES):
        return

    ensure_no_diff_or_ignore_markers("\n".join(parsed.lines))
    _, _, bang, _ = validate_header(parsed.header)
    ensure_breaking_footer_if_needed(bang, parsed.footers)
    validate_body(parsed.lines, parsed.header_idx, parsed.first_footer_idx)


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

    try:
        validate_commit_message(msg_path)
    except ValidationError as err:
        print(_error_summary(err.reasons), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
