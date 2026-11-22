#!/bin/sh
# POSIX entrypoint. V1 default stays compatible; MVP mode is explicitly opted in.
set -eu
here=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
case "${RAF_MODE:-contract}" in
  contract)
    exec python3 "$here/raf_valcheck.py"
    ;;
  mvp)
    set -- run --topology "${RAF_TOPOLOGY:-.raf/topology.json}" --manifest "${RAF_MANIFEST:-.raf/validation.yml}" --workspace .
    if [ -n "${RAF_MVP_PRIOR:-}" ]; then
      set -- "$@" --prior "$RAF_MVP_PRIOR"
    fi
    if [ -n "${RAF_MVP_PRIOR_SHA256:-}" ]; then
      set -- "$@" --prior-sha256 "$RAF_MVP_PRIOR_SHA256"
    fi
    if [ -n "${RAF_MVP_OUTPUT:-}" ]; then
      set -- "$@" --output "$RAF_MVP_OUTPUT"
    fi
    exec python3 "$here/raf_mvp.py" "$@"
    ;;
  *)
    printf '%s\n' 'result=BLOCKED' 'token=MODE_UNSUPPORTED' 'claim_allowed=false'
    exit 1
    ;;
esac
