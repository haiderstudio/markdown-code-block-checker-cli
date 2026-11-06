#!/usr/bin/env python3
"""Check code blocks in Markdown files are closed and tagged, fail CI on a bad block.

Run: python3 src/markdown_code_block_checker.py docs/
     python3 src/markdown_code_block_checker.py post.md --allow-untagged

The tool reads Markdown files and checks every fenced code block
(the ``` and ~~~ fences):

- Every opening fence names a language (```python, ```sh, and so on).
  A block with no language tag fails, unless you pass
  --allow-untagged.
- Every block is closed by a matching fence. A block that is still
  open at the end of the file fails, with the line where it opened.
- A bare fence line that sits right after a block was closed, with
  only blank lines between, is a stray closing fence left over from
  an edit. It fails, and it is not treated as a new block.
- A fence line inside a block only closes the block when it uses the
  same fence character, is at least as long as the opening fence, and
  carries no language tag. Anything else inside a block is code, not
  a fence — so a ``` line inside a ``` block does not close it, and a
  ~~~ line inside a ``` block does not close it either.

It is report-only: it never rewrites a file, and it runs fully
offline. It sends nothing anywhere and needs no API key.

Exit codes: 0 when every file passes, 1 when any file fails,
2 for a usage or input problem (a missing file, a bad flag, no input).
"""

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"

FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
LANGUAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_#.-]*$")
MARKDOWN_SUFFIXES = (".md", ".markdown")


class Problem:
    """One problem in one file, with its line number (0 = whole file)."""

    def __init__(self, line, message):
        self.line = line
        self.message = message

    def __eq__(self, other):
        return (
            isinstance(other, Problem)
            and self.line == other.line
            and self.message == other.message
        )

    def __repr__(self):
        return "Problem(%r, %r)" % (self.line, self.message)


def _fence_parts(line):
    """Split a line into (char, length, info) if it is a fence line.

    Returns None when the line is not a fence: more than three leading
    spaces, fewer than three fence characters, or — for a backtick
    fence — a backtick inside the info string.
    """
    match = FENCE_RE.match(line.rstrip("\n"))
    if not match:
        return None
    fence = match.group(2)
    info = match.group(3).strip()
    if fence[0] == "`" and "`" in info:
        return None
    return fence[0], len(fence), info


def check_text(text):
    """Check one Markdown document. Returns a list of Problems."""
    return check_lines(text.splitlines())


def check_lines(lines):
    """Check Markdown lines. Returns a list of Problems."""
    problems = []
    open_fence = None  # (char, length, opening line)
    last_close = None  # (char, length) of the fence that just closed a block
    blank_since_close = False

    for number, line in enumerate(lines, start=1):
        parts = _fence_parts(line)
        if parts is None:
            if line.strip():
                blank_since_close = False
            continue
        char, length, info = parts
        if open_fence is not None:
            open_char, open_length, open_line = open_fence
            if char == open_char and length >= open_length and not info:
                open_fence = None
                last_close = (char, length)
                blank_since_close = True
            # Anything else inside a block is code, not a fence.
            continue
        # No block is open: this fence line opens one — unless it is a
        # stray closing fence left over from an edit.
        if (
            not info
            and last_close == (char, length)
            and blank_since_close
        ):
            problems.append(
                Problem(number, "stray closing fence (no block is open)")
            )
            last_close = None
            blank_since_close = False
            continue
        if not info:
            problems.append(
                Problem(number, "code block has no language tag")
            )
        elif not LANGUAGE_RE.match(info.split()[0]):
            problems.append(
                Problem(
                    number,
                    "code block language tag %r is not a plain word"
                    % info.split()[0],
                )
            )
        open_fence = (char, length, number)
        last_close = None
        blank_since_close = False

    if open_fence is not None:
        problems.append(
            Problem(
                open_fence[2],
                "code block opened on line %d is never closed"
                % open_fence[2],
            )
        )
    return problems


def check_file(path):
    """Check one file. Returns a list of Problems."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [Problem(0, "file is not valid UTF-8")]
    except OSError as exc:
        return [Problem(0, "cannot read file (%s)" % exc.strerror)]
    return check_text(text)


def collect_files(paths, recursive=True):
    """Turn files and folders into a sorted list of Markdown files."""
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            pattern = "**/*" if recursive else "*"
            for item in sorted(path.glob(pattern)):
                if item.is_file() and item.suffix.lower() in MARKDOWN_SUFFIXES:
                    found.append(item)
        else:
            raise FileNotFoundError(raw)
    return found


def check_paths(paths, recursive=True, allow_untagged=False):
    """Check every file. Returns {str(path): [Problem, ...]}."""
    results = {}
    for path in collect_files(paths, recursive=recursive):
        problems = check_file(path)
        if allow_untagged:
            problems = [
                p
                for p in problems
                if p.message != "code block has no language tag"
            ]
        results[str(path)] = problems
    return results


def format_problem(path, problem):
    """One problem as a single report line."""
    if problem.line:
        return "FAIL %s:%d: %s" % (path, problem.line, problem.message)
    return "FAIL %s: %s" % (path, problem.message)


def run(argv=None, stdin=None, stdout=None, stderr=None):
    """Run the CLI. Returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="markdown_code_block_checker",
        description=(
            "Check code blocks in Markdown are closed and tagged, "
            "fail CI on a bad block."
        ),
    )
    parser.add_argument("paths", nargs="*", help="Markdown files or folders")
    parser.add_argument(
        "--allow-untagged",
        action="store_true",
        help="allow code blocks with no language tag",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="do not look inside subfolders",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="read one Markdown document from standard input",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON (summary goes to stderr)",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        args = parser.parse_args(argv)

    if args.stdin and args.paths:
        parser.error("--stdin takes no file or folder")
    if not args.stdin and not args.paths:
        parser.error("no input: name a file, a folder, or --stdin")

    if args.stdin:
        text = (stdin or sys.stdin).read()
        problems = check_text(text)
        if args.allow_untagged:
            problems = [
                p
                for p in problems
                if p.message != "code block has no language tag"
            ]
        results = {"<stdin>": problems}
    else:
        try:
            results = check_paths(
                args.paths,
                recursive=not args.no_recursive,
                allow_untagged=args.allow_untagged,
            )
        except FileNotFoundError as exc:
            parser.error("no such file or folder: %s" % exc)

    checked = len(results)
    failed = sum(1 for problems in results.values() if problems)
    passed = checked - failed
    problems_total = sum(len(p) for p in results.values())

    if args.json:
        data = {
            "files": [
                {
                    "file": path,
                    "valid": not problems,
                    "problems": [
                        {"line": p.line, "message": p.message}
                        for p in problems
                    ],
                }
                for path, problems in results.items()
            ],
            "summary": {
                "checked": checked,
                "passed": passed,
                "failed": failed,
                "problems": problems_total,
            },
        }
        print(json.dumps(data, indent=2), file=out)
    else:
        for path, problems in results.items():
            if not problems:
                print("PASS %s" % path, file=out)
            for problem in problems:
                print(format_problem(path, problem), file=out)

    summary = "%d file(s) checked, %d passed, %d failed" % (
        checked,
        passed,
        failed,
    )
    if args.json:
        print(summary, file=err)
    else:
        print(summary, file=out)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
