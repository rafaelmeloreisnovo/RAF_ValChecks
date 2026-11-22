#!/bin/sh
set -eu
# Python standard library only. Avoid executable-bit dependence and shell parsing.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/raf_valcheck.py"
