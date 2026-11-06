# markdown-code-block-checker-cli

Check code blocks in Markdown are closed and tagged, fail CI on a bad block.

[![CI](https://github.com/haiderstudio/markdown-code-block-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/markdown-code-block-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`markdown_code_block_checker` reads Markdown files and checks every
fenced code block (the ```` ``` ```` and `~~~` fences):

- Every opening fence names a language (```python, ```sh, and so on).
  A block with no language tag fails, unless you pass
  `--allow-untagged`.
- Every block is closed by a matching fence. A block that is still
  open at the end of the file fails, with the line where it opened.
- A bare fence line that sits right after a block was closed, with
  only blank lines between, is a stray closing fence left over from
  an edit. It fails, and it is not treated as a new block.
- A fence line inside a block only closes the block when it uses the
  same fence character, is at least as long as the opening fence, and
  carries no language tag. Anything else inside a block is code, not
  a fence — so a three-backtick line inside a four-backtick block
  does not close it, and a `~~~` line inside a ``` block does not
  close it either.
- It checks one file, several files, or a whole folder (folders are
  scanned for `.md` and `.markdown` files, including subfolders,
  unless you pass `--no-recursive`). `--stdin` checks one document
  piped in.
- It prints `PASS` or `FAIL` per file, with the exact file and line,
  and a summary line. It exits 1 when any file fails, so it can fail
  a CI run. `--json` prints the same result as machine-readable JSON
  (the summary goes to standard error, so standard output stays
  clean JSON).
- It is report-only and runs fully offline: it never rewrites a file,
  sends nothing anywhere, and needs no API key.

## What it does NOT do

- It does not check what is inside a code block. Syntax errors in
  the code itself are another tool's job.
- It does not fix a bad block. A missing tag or a missing closing
  fence is reported, not repaired.
- It does not check indented code blocks (four-space indent) or
  inline code (single backticks). Only fenced blocks are checked.
- It does not know a list of "real" languages. Any plain first word
  after the fence counts as a language tag (`python`, `c++`, `c#`,
  `objective-c`).
- It does not fetch files from the network. Every input is a local
  file, folder, or standard input.

## Who it is for

Anyone who keeps Markdown files that need their code blocks right
before a build: a blogger whose posts carry code samples, a docs
site where every example must render, or a team adding a CI step
that fails the build when a page ships with an unclosed fence or a
block with no language. If the files are right, you get a quiet
pass; if one is wrong, the report says exactly which file and which
line.

## How this differs from similar tools

Code-block checkers for Markdown barely exist. The exact name
`markdown-code-block-checker-cli` matches 0 repositories on GitHub,
and the searches "markdown code block checker" and "markdown fence
checker" return 0 results each. The closest repos in the wider
field are small and unstarred: maxotto-agent/mdfence (0 stars)
lints fenced code blocks in Markdown, and
markkamuya/markdown-codeblock-linter (0 stars) validates fenced
blocks and inserts inline error feedback into the file — it edits
your docs, which this tool never does. The top hit in a broader
"markdown lint code fence" search is a PHP codesniffer with 1 star.
Day 24 (markdown-frontmatter-checker-cli) checks frontmatter at the
top of a Markdown file; Day 5 (markdown-table-converter-cli)
converts tables. Checking fenced code blocks is a different job,
and no tested tool owns it. This tool does that one job: a Python
standard-library-only CLI that checks fences in local files,
reports every problem with a file and line, and exits 1 on a bad
block for CI — no install beyond Python, no edits, no network.

## Install

Python standard library only — no packages to download. Clone the
repo and run it in place:

```
git clone https://github.com/haiderstudio/markdown-code-block-checker-cli.git
cd markdown-code-block-checker-cli
python3 src/markdown_code_block_checker.py examples/good.md
```

```
PASS examples/good.md
1 file(s) checked, 1 passed, 0 failed
```

## Usage

Check one file:

```
python3 src/markdown_code_block_checker.py docs/guide.md
```

Check a whole folder:

```
python3 src/markdown_code_block_checker.py docs/
```

Allow blocks with no language tag:

```
python3 src/markdown_code_block_checker.py examples/untagged.md --allow-untagged
```

```
PASS examples/untagged.md
1 file(s) checked, 1 passed, 0 failed
```

Machine-readable output with `--json` (the summary goes to
standard error, so standard output stays clean JSON):

```
python3 src/markdown_code_block_checker.py examples/good.md examples/untagged.md --json
```

```
{
  "files": [
    {
      "file": "examples/good.md",
      "valid": true,
      "problems": []
    },
    {
      "file": "examples/untagged.md",
      "valid": false,
      "problems": [
        {
          "line": 5,
          "message": "code block has no language tag"
        }
      ]
    }
  ],
  "summary": {
    "checked": 2,
    "passed": 1,
    "failed": 1,
    "problems": 1
  }
}
```

Exit codes: 0 when every file passes, 1 when any file fails, 2 for
a usage or input problem (a missing file, a bad flag, no input at
all).

## Examples

### 1. A bad file — unclosed block

`examples/unclosed.md` opens a block that is never closed:

```
python3 src/markdown_code_block_checker.py examples/unclosed.md
```

```
FAIL examples/unclosed.md:5: code block opened on line 5 is never closed
1 file(s) checked, 0 passed, 1 failed
```

### 2. A bad file — stray closing fence

`examples/stray-fence.md` has a good block, then a bare fence line
left over from an edit:

```
python3 src/markdown_code_block_checker.py examples/stray-fence.md
```

```
FAIL examples/stray-fence.md:9: stray closing fence (no block is open)
1 file(s) checked, 0 passed, 1 failed
```

### 3. The bundled examples, all at once

```
sh examples/run-example.sh
```

The script checks the good file (passes) and the three bad files
(all fail, on purpose). Its full output is in
`examples/sample-output.txt`:

```
PASS examples/good.md
FAIL examples/unclosed.md:5: code block opened on line 5 is never closed
FAIL examples/untagged.md:5: code block has no language tag
FAIL examples/stray-fence.md:9: stray closing fence (no block is open)
4 file(s) checked, 1 passed, 3 failed
```

## How it is tested

51 tests, standard library `unittest` only, no packages to install:

```
python3 tests/test_markdown_code_block_checker.py
```

The tests cover: good files (tagged blocks, tilde fences, longer
closing fences, `c++` and `c#` tags, inline code, indented fences),
missing tags, unclosed blocks, fences inside blocks (shorter
same-char fences, other-char fences, fences with a language tag),
stray fences, file reading (missing files, non-UTF-8 files, folder
collection, `--no-recursive`), the CLI (exit 0/1/2, `--json`,
`--stdin`, `--version`, input files left unchanged), the bundled
examples (sample output compared byte-for-byte against a fresh run,
and the README-quoted outputs checked against it), and hygiene
checks (no placeholder text, no absolute paths, stdlib imports
only, `.env` first in `.gitignore`).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The idea of
checking Markdown code blocks is not new — the similar tools named
above (maxotto-agent/mdfence,
markkamuya/markdown-codeblock-linter) are listed in "How this
differs" — but every line of code here is original, and the tool
builds on nothing but Python's standard library.
