#!/usr/bin/env python3
"""Tests for markdown_code_block_checker. Standard library unittest only."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from markdown_code_block_checker import (  # noqa: E402
    Problem,
    check_file,
    check_lines,
    check_text,
    collect_files,
    run,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXAMPLES = ROOT / "examples"


def run_cli(argv, stdin_text=None):
    """Run the CLI in-process and capture stdout/stderr. Returns (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    stdin = io.StringIO(stdin_text) if stdin_text is not None else None
    try:
        code = run(argv, stdin=stdin, stdout=out, stderr=err)
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def write_file(folder, name, text):
    path = Path(folder) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def messages(problems):
    return [(p.line, p.message) for p in problems]


class TestGoodFiles(unittest.TestCase):
    def test_empty_document_passes(self):
        self.assertEqual(check_text(""), [])

    def test_plain_text_passes(self):
        self.assertEqual(check_text("# Title\n\nSome words.\n"), [])

    def test_tagged_block_passes(self):
        text = "```python\nprint(1)\n```\n"
        self.assertEqual(check_text(text), [])

    def test_tilde_fence_passes(self):
        text = "~~~sh\necho hi\n~~~\n"
        self.assertEqual(check_text(text), [])

    def test_longer_closing_fence_passes(self):
        text = "```python\ncode\n````\n"
        self.assertEqual(check_text(text), [])

    def test_language_with_plus_and_hash_passes(self):
        text = "```c++\nint main() {}\n```\n```c#\nvar x = 1;\n```\n"
        self.assertEqual(check_text(text), [])

    def test_inline_code_is_not_a_fence(self):
        text = "Use `print` here, and ``two`` there.\n"
        self.assertEqual(check_text(text), [])

    def test_fence_with_four_leading_spaces_is_not_a_fence(self):
        text = "    ```python\n    code\n"
        self.assertEqual(check_text(text), [])

    def test_three_leading_spaces_still_a_fence(self):
        text = "   ```python\n   code\n   ```\n"
        self.assertEqual(check_text(text), [])

    def test_multiple_blocks_pass(self):
        text = "```python\na = 1\n```\n\nText.\n\n~~~js\nlet b = 2;\n~~~\n"
        self.assertEqual(check_text(text), [])


class TestMissingTag(unittest.TestCase):
    def test_untagged_block_fails(self):
        problems = check_text("```\ncode\n```\n")
        self.assertEqual(
            messages(problems),
            [(1, "code block has no language tag")],
        )

    def test_untagged_tilde_block_fails(self):
        problems = check_text("~~~\ncode\n~~~\n")
        self.assertEqual(
            messages(problems),
            [(1, "code block has no language tag")],
        )

    def test_blank_info_string_fails(self):
        problems = check_text("```   \ncode\n```\n")
        self.assertEqual(
            messages(problems),
            [(1, "code block has no language tag")],
        )

    def test_tag_must_be_a_plain_word(self):
        problems = check_text("```!!!\ncode\n```\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("not a plain word", problems[0].message)

    def test_info_string_after_first_word_is_allowed(self):
        text = "```python title=\"demo\"\ncode\n```\n"
        self.assertEqual(check_text(text), [])


class TestUnclosed(unittest.TestCase):
    def test_unclosed_block_reports_opening_line(self):
        text = "# Title\n\n```python\ncode\n"
        problems = check_text(text)
        self.assertEqual(
            messages(problems),
            [(3, "code block opened on line 3 is never closed")],
        )

    def test_unclosed_tilde_block(self):
        text = "~~~\ncode\n"
        self.assertEqual(
            messages(check_text(text)),
            [
                (1, "code block has no language tag"),
                (1, "code block opened on line 1 is never closed"),
            ],
        )

    def test_second_block_unclosed(self):
        text = "```python\na\n```\n\n```sh\nb\n"
        self.assertEqual(
            messages(check_text(text)),
            [(5, "code block opened on line 5 is never closed")],
        )


class TestFenceInsideBlock(unittest.TestCase):
    def test_shorter_same_char_fence_is_content(self):
        text = "````python\ncode\n```\nmore code\n````\n"
        self.assertEqual(check_text(text), [])

    def test_other_char_fence_is_content(self):
        text = "```python\n~~~\ncode\n```\n"
        self.assertEqual(check_text(text), [])

    def test_fence_with_info_inside_block_is_content(self):
        text = "```python\ncode\n```sh\nmore\n```\n"
        self.assertEqual(check_text(text), [])

    def test_backtick_in_backtick_info_is_not_a_fence(self):
        text = "```foo`bar\ncode\n```\n"
        # The first line is not a fence, so the ``` line opens a block
        # with no tag and it is never closed.
        problems = check_text(text)
        self.assertIn((3, "code block has no language tag"), messages(problems))
        self.assertIn(
            (3, "code block opened on line 3 is never closed"),
            messages(problems),
        )


class TestStrayFence(unittest.TestCase):
    def test_bare_fence_right_after_a_close_is_stray(self):
        text = "```python\ncode\n```\n\n```\n"
        self.assertEqual(
            messages(check_text(text)),
            [(5, "stray closing fence (no block is open)")],
        )

    def test_bare_fence_after_text_is_a_new_block(self):
        text = "```python\ncode\n```\n\nSome words.\n\n```\nmore\n```\n"
        self.assertEqual(
            messages(check_text(text)),
            [(7, "code block has no language tag")],
        )

    def test_tagged_fence_right_after_a_close_opens_a_block(self):
        text = "```python\na\n```\n```sh\nb\n```\n"
        self.assertEqual(check_text(text), [])

    def test_stray_fence_of_other_char_is_not_stray(self):
        text = "```python\ncode\n```\n\n~~~\n"
        problems = check_text(text)
        self.assertEqual(
            messages(problems),
            [
                (5, "code block has no language tag"),
                (5, "code block opened on line 5 is never closed"),
            ],
        )

    def test_stray_fence_of_other_length_is_not_stray(self):
        text = "```python\ncode\n```\n\n````\n"
        problems = check_text(text)
        self.assertEqual(
            messages(problems),
            [
                (5, "code block has no language tag"),
                (5, "code block opened on line 5 is never closed"),
            ],
        )


class TestFileChecks(unittest.TestCase):
    def test_missing_file_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems = check_file(Path(tmp) / "nope.md")
            self.assertEqual(len(problems), 1)
            self.assertIn("cannot read file", problems[0].message)

    def test_non_utf8_file_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_bytes(b"```python\n\xff\xfe\n```\n")
            problems = check_file(path)
            self.assertEqual(
                messages(problems), [(0, "file is not valid UTF-8")]
            )

    def test_collect_files_from_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.md", "```python\nx\n```\n")
            write_file(tmp, "sub/b.markdown", "text\n")
            write_file(tmp, "sub/c.txt", "```\n")
            found = collect_files([tmp])
            names = sorted(p.name for p in found)
            self.assertEqual(names, ["a.md", "b.markdown"])

    def test_collect_files_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "a.md", "text\n")
            write_file(tmp, "sub/b.md", "text\n")
            found = collect_files([tmp], recursive=False)
            self.assertEqual([p.name for p in found], ["a.md"])

    def test_collect_files_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            collect_files(["/no/such/path/at/all"])


class TestCli(unittest.TestCase):
    def test_good_file_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, "good.md", "```python\nx\n```\n")
            code, out, err = run_cli([str(path)])
            self.assertEqual(code, 0)
            self.assertIn("PASS %s" % path, out)
            self.assertIn("1 file(s) checked, 1 passed, 0 failed", out)

    def test_bad_file_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, "bad.md", "```\nx\n```\n")
            code, out, err = run_cli([str(path)])
            self.assertEqual(code, 1)
            self.assertIn(
                "FAIL %s:1: code block has no language tag" % path, out
            )
            self.assertIn("1 file(s) checked, 0 passed, 1 failed", out)

    def test_allow_untagged_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, "plain.md", "```\nx\n```\n")
            code, out, err = run_cli([str(path), "--allow-untagged"])
            self.assertEqual(code, 0)
            self.assertIn("PASS %s" % path, out)

    def test_folder_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "good.md", "```python\nx\n```\n")
            write_file(tmp, "bad.md", "```python\nx\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("2 file(s) checked, 1 passed, 1 failed", out)

    def test_stdin(self):
        code, out, err = run_cli(["--stdin"], stdin_text="```\nx\n```\n")
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>:1: code block has no language tag", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "x.md"], stdin_text="")
        self.assertEqual(code, 2)

    def test_no_input_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_is_usage_error(self):
        code, out, err = run_cli(["/no/such/path/at/all.md"])
        self.assertEqual(code, 2)

    def test_bad_flag_is_usage_error(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_file(tmp, "good.md", "```python\nx\n```\n")
            write_file(tmp, "bad.md", "```\nx\n```\n")
            code, out, err = run_cli([tmp, "--json"])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["summary"]["checked"], 2)
            self.assertEqual(data["summary"]["passed"], 1)
            self.assertEqual(data["summary"]["failed"], 1)
            self.assertEqual(data["summary"]["problems"], 1)
            self.assertIn("2 file(s) checked", err)
            bad = [f for f in data["files"] if f["file"].endswith("bad.md")][0]
            self.assertEqual(bad["problems"][0]["line"], 1)
            self.assertIn("no language tag", bad["problems"][0]["message"])

    def test_version_flag(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "1.0.0")

    def test_input_files_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_file(tmp, "doc.md", "```\nx\n```\n")
            before = path.read_text(encoding="utf-8")
            run_cli([str(path)])
            self.assertEqual(path.read_text(encoding="utf-8"), before)


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        sample = (EXAMPLES / "sample-output.txt").read_text(encoding="utf-8")
        self.assertEqual(result.stdout, sample)

    def test_run_example_script_exits_zero(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_readme_quotes_real_output(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        sample = (EXAMPLES / "sample-output.txt").read_text(encoding="utf-8")
        for line in [
            "PASS examples/good.md",
            "FAIL examples/unclosed.md:5: code block opened on line 5 is never closed",
            "FAIL examples/untagged.md:5: code block has no language tag",
            "FAIL examples/stray-fence.md:9: stray closing fence (no block is open)",
            "4 file(s) checked, 1 passed, 3 failed",
        ]:
            self.assertIn(line, readme, "README must quote: %s" % line)
            self.assertIn(line, sample, "sample output must contain: %s" % line)


class TestHygiene(unittest.TestCase):
    def test_no_placeholder_text(self):
        banned = ["TODO", "FIXME", "coming soon", "lorem", "API_KEY"]
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path, word))
        self.assertEqual(hits, [])

    def test_no_absolute_workspace_paths(self):
        hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "/home/" in text or "/Users/" in text or "C:\\" in text:
                hits.append(str(path))
        self.assertEqual(hits, [])

    def test_stdlib_only(self):
        import ast

        allowed = set(sys.stdlib_module_names) | {
            "markdown_code_block_checker"
        }
        source = (ROOT / "src" / "markdown_code_block_checker.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
        self.assertEqual(imported - allowed, set())

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], ".env")


if __name__ == "__main__":
    unittest.main()
