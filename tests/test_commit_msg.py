"""Unit tests for commit message validator."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "commit_msg" / "commit_msg.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("commit_msg", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load commit_msg module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


commit_msg = _load_module()
ValidationError = commit_msg.ValidationError
validate_commit_message = commit_msg.validate_commit_message


def write_message(tmp_path: Path, content: str) -> Path:
    message = textwrap.dedent(content).strip() + "\n"
    path = tmp_path / "COMMIT_MSG.txt"
    path.write_text(message, encoding="utf-8")
    return path


def test_valid_message_passes(tmp_path: Path) -> None:
    path = write_message(tmp_path, "feat: add terse output")
    validate_commit_message(path)


def test_invalid_type_rejected(tmp_path: Path) -> None:
    path = write_message(tmp_path, "feature: add thing")
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "invalid type 'feature'" in err.value.reasons[0]


def test_scope_validation(tmp_path: Path) -> None:
    path = write_message(tmp_path, "fix(invalid*scope): update")
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "scope 'invalid*scope' must match" in err.value.reasons[0]


def test_subject_character_rules(tmp_path: Path) -> None:
    path = write_message(tmp_path, "fix: Invalid subject")
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "subject must start with a lowercase letter" in err.value.reasons[0]


def test_body_line_length_enforced(tmp_path: Path) -> None:
    too_long = "a" * 73
    path = write_message(tmp_path, f"feat: add long body\n\n{too_long}")
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "exceeds 72 chars" in err.value.reasons[0]


def test_requires_breaking_change_footer(tmp_path: Path) -> None:
    path = write_message(tmp_path, "chore!: restructure modules")
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "BREAKING CHANGE" in err.value.reasons[0]


def test_breaking_change_footer_allows_bang(tmp_path: Path) -> None:
    path = write_message(
        tmp_path,
        """
        refactor!: adjust api

        BREAKING CHANGE: api output shape
        """,
    )
    validate_commit_message(path)


def test_rejects_raw_diffs(tmp_path: Path) -> None:
    path = write_message(
        tmp_path,
        """
        fix: avoid panic

        diff --git a/file b/file
        @@ context
        """,
    )
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "raw diff" in err.value.reasons[0]


def test_rejects_ignore_marker(tmp_path: Path) -> None:
    path = write_message(tmp_path, "docs: add note\n\n--- IGNORE ---")
    with pytest.raises(ValidationError) as err:
        validate_commit_message(path)
    assert "forbidden internal markers" in err.value.reasons[0]


def test_merge_messages_bypass_validation(tmp_path: Path) -> None:
    path = write_message(tmp_path, "Merge branch 'main'")
    validate_commit_message(path)
