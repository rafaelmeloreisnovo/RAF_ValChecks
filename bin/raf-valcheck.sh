#!/bin/sh
set -eu

manifest=${RAF_MANIFEST:-.raf/validation.yml}
receipt=${RAF_RECEIPT:-}

if [ ! -f "$manifest" ]; then
  printf '%s\n' 'result=BLOCKED'
  printf '%s\n' 'token=MANIFEST_MISSING'
  exit 1
fi

case "$manifest" in
  *.yml|*.yaml|*.json) ;;
  *) printf '%s\n' 'result=BLOCKED'; printf '%s\n' 'token=UNSUPPORTED_MANIFEST_FORMAT'; exit 1 ;;
esac

if [ -n "$receipt" ] && [ ! -f "$receipt" ]; then
  printf '%s\n' 'result=BLOCKED'
  printf '%s\n' 'token=RECEIPT_PATH_MISSING'
  exit 1
fi

if ! LC_ALL=C grep -Eq 'source_commit:[[:space:]]*[0-9a-fA-F]{40}' "$manifest" &&
   ! LC_ALL=C grep -Eq '"source_commit"[[:space:]]*:[[:space:]]*"[0-9a-fA-F]{40}"' "$manifest"; then
  printf '%s\n' 'result=BLOCKED'
  printf '%s\n' 'token=SOURCE_COMMIT_NOT_PINNED'
  exit 1
fi

if ! LC_ALL=C grep -Eq 'updates:[[:space:]]*observe_only' "$manifest" &&
   ! LC_ALL=C grep -Eq '"updates"[[:space:]]*:[[:space:]]*"observe_only"' "$manifest"; then
  printf '%s\n' 'result=BLOCKED'
  printf '%s\n' 'token=UPDATE_POLICY_UNDECLARED'
  exit 1
fi

printf '%s\n' 'result=PASS_SCOPED'
printf '%s\n' 'evidence=DOCUMENTED'
printf '%s\n' 'claim_allowed=false'
printf '%s\n' 'recompute=IMPACT_CONE_ONLY'
