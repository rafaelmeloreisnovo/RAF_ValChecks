# Verified Git-delta negative-coverage advisory (V1)

**Status:** intentionally limited to local, committed, *observed* changes.

This is the first step toward a discovery system for unknown dependencies and
indirect impacts. It does NOT infer causality from correlated changes and it
NEVER authorizes skipping required checks, merging a pull request or disabling
CI. `claim_allowed=false` and `runtime_skipping_authorized=false` are invariant.

## Trust boundary

1. Reads **local Git objects** for an exact 40-hex `--head` equal to the checkout
   `HEAD` and an exact `--base` that is its ancestor. A clean working tree,
   including no untracked files, is required before comparison. Ignored files
   are outside this committed-diff audit. No remote fetch, token, API call,
   commit operation, network dependency or shell evaluation is performed.
2. Parses `git diff --no-renames --name-only -z` (so moves count as both source
   and destination paths) with byte-size, filename count and UTF-8 safety limits.
   Compares **the chosen Git interval only**. `HEAD^..HEAD` covers one commit;
   it is not automatically a complete PR comparison.
3. Applies local, versioned `--routes` with *exact paths* or *directory prefixes*,
   each mapping to one or more scopes declared in the selected topology.
   Path routing is a **hypothesis entered by the repo producer**, not proof
   that other modules cannot be affected. The route-file raw SHA-256 and Git
   diff raw SHA-256 are recorded for audit; no producer signature is verified.
4. **Negative coverage:** unmapped changed paths, unknown mapped scopes, changes
   to the route file, changes to protected control-plane paths and empty Git
   diffs produce `TOKEN_VAZIO` and an **all-nodes-affected** advisory.
   Unmapped paths yield `UNKNOWN_DEPENDENCY_CANDIDATE` placeholders, *not*
   inferred edges or causal claims. A new owner-reviewed mapping plus tests is
   required before any claim about coverage can strengthen.
5. Known-scope unaffected nodes are **candidates**, not safe skips. Even when
   every file is mapped, route completeness and remote authenticity are not
   independently verified; `independent_route_authority_verified=false` and
   `remote_provenance_verified=false`. Legacy identity gates remain mandatory.

## Example

```sh
# Run on a CLEAN checkout with the requested base object already available.
BASE=$(git rev-parse HEAD^)
HEAD=$(git rev-parse HEAD)
python3 bin/raf_mvp.py git-impact \
  --topology examples/topology.mvp.json \
  --routes examples/change-routes.v1.json \
  --workspace . --base "$BASE" --head "$HEAD"
```

Return code `0` means a read-only `PLAN_ONLY` analysis. Return code `1`
means a typed uncertainty (`TOKEN_VAZIO`) or a blocked input, not necessarily
software malfunction. The printed JSON includes `anomaly_tokens`,
`changed_paths`, `unmapped_paths`, `critical_paths`, `coverage`,
`hypotheses`, a deterministic `audit_id`, and `impact_advisory`.

The existing `--output path` creates a file with **exclusive create and fsync**.
Use a unique append-only destination. A hash or audit ID proves byte
consistency only, never external producer authenticity, causal correctness or
legal timestamp.

## Priority falsifiers

- A known mapped path must identify its declared scope and still forbid runtime
  skipping.
- A novel path cannot quietly become an unaffected candidate.
- A change to `rafvalchecks/`, `schemas/`, `action.yml`, `.github/workflows/`,
  the CLI entrypoints, or the route file must invalidate selective conclusions.
- Dirty, non-ancestor, missing-object, wrong-HEAD, duplicate-route, path traversal,
  rename and empty-diff cases must fail closed or return all-node uncertainty.
- Local and GitHub CI tests must agree, but exact HEAD CI success does not prove
  end-to-end operation in a third-party consuming repository.

## Future extension points (not yet built)

`OBSERVED_EVENT` -> `TEMPORAL_CORRELATION` -> `HYPOTHESIS_RELATION` ->
`FALSIFIER_EXECUTED` -> `EVIDENCED_SCOPED`. A relationship remains unproven until
independent observations and a designed falsifier support promotion.
No raw private system logs or correlation graphs are published by this tool.
