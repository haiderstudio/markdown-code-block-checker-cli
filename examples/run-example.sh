#!/bin/sh
# Check the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The check exits 1 because three example files fail on purpose —
# that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- check all example files ---"
python3 src/markdown_code_block_checker.py examples/good.md examples/unclosed.md examples/untagged.md examples/stray-fence.md || true
echo "--- check the good file alone ---"
python3 src/markdown_code_block_checker.py examples/good.md
