"""Unit tests for commit message validator."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "commit-msg" / "main.pl"


def write_message(tmp_path: Path, content: str) -> Path:
    message = textwrap.dedent(content).strip() + "\n"
    path = tmp_path / "COMMIT_MSG.txt"
    path.write_text(message, encoding="utf-8")
    return path


def run_hook(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["perl", str(SCRIPT_PATH), str(path)],
        check=False,
        text=True,
        capture_output=True,
    )


def test_valid_message_passes(tmp_path: Path) -> None:
    path = write_message(tmp_path, "feat: add terse output")
    result = run_hook(path)
    assert result.returncode == 0
    assert result.stderr == ""


def test_uppercase_words_in_subject_allowed(tmp_path: Path) -> None:
    path = write_message(tmp_path, "feat: add API response parser")
    assert run_hook(path).returncode == 0


def test_invalid_type_rejected(tmp_path: Path) -> None:
    path = write_message(tmp_path, "feature: add thing")
    result = run_hook(path)
    assert result.returncode == 1
    assert "invalid type 'feature'" in result.stderr


def test_scope_validation(tmp_path: Path) -> None:
    path = write_message(tmp_path, "fix(invalid*scope): update")
    result = run_hook(path)
    assert result.returncode == 1
    assert "scope 'invalid*scope' must match" in result.stderr


def test_subject_character_rules(tmp_path: Path) -> None:
    path = write_message(tmp_path, "fix: Invalid subject")
    result = run_hook(path)
    assert result.returncode == 1
    assert "subject must start with a lowercase letter" in result.stderr


def test_body_line_length_enforced(tmp_path: Path) -> None:
    too_long = "a" * 73
    path = write_message(tmp_path, f"feat: add long body\n\n{too_long}")
    result = run_hook(path)
    assert result.returncode == 1
    assert "exceeds 72 chars" in result.stderr


def test_requires_breaking_change_footer(tmp_path: Path) -> None:
    path = write_message(tmp_path, "chore!: restructure modules")
    result = run_hook(path)
    assert result.returncode == 1
    assert "BREAKING CHANGE" in result.stderr


def test_breaking_change_footer_allows_bang(tmp_path: Path) -> None:
    path = write_message(
        tmp_path,
        """
        refactor!: adjust api

        BREAKING CHANGE: api output shape
        """,
    )
    assert run_hook(path).returncode == 0


def test_rejects_raw_diffs(tmp_path: Path) -> None:
    path = write_message(
        tmp_path,
        """
        fix: avoid panic

        diff --git a/file b/file
        @@ context
        """,
    )
    result = run_hook(path)
    assert result.returncode == 1
    assert "raw diff" in result.stderr


def test_rejects_ignore_marker(tmp_path: Path) -> None:
    path = write_message(tmp_path, "docs: add note\n\n--- IGNORE ---")
    result = run_hook(path)
    assert result.returncode == 1
    assert "forbidden internal markers" in result.stderr


def test_merge_messages_bypass_validation(tmp_path: Path) -> None:
    path = write_message(tmp_path, "Merge branch 'main'")
    assert run_hook(path).returncode == 0


def test_reports_multiple_diagnostics_at_once(tmp_path: Path) -> None:
    path = write_message(
        tmp_path,
        """
        feature(bad*scope): Invalid subject!

        bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

        diff --git a/file b/file
        """,
    )
    result = run_hook(path)
    assert result.returncode == 1
    assert "invalid type 'feature'" in result.stderr
    assert "scope 'bad*scope' must match" in result.stderr
    assert "subject must start with a lowercase letter" in result.stderr
    assert "'!' is not allowed" in result.stderr
    assert "body exceeds 72 chars" in result.stderr
    assert "raw diff" in result.stderr
