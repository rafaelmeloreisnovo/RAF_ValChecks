# RAF_ValChecks — validation-contract gate

**Status: draft, validation limited to manifest/checkout identity and receipt assertions.**

`action.yml` is a **preflight**, not an execution engine for arbitrary CI checks. It intentionally never reports that listed project checks have run. It uses Python 3 standard library and POSIX `sh` with no `pip` installs, no network requests, no repository writes and no credential access. The strict YAML-subset parser supports the included example (simple mappings, lists, booleans, scalars and comments); advanced YAML features such as anchors, aliases, merges and multiline scalars are rejected. Full JSON is also supported; unsupported forms fail closed.

## Provenance and scope

- `project.repository` is matched to `GITHUB_REPOSITORY`, when present.
- `project.source_commit` must be an actual nonzero 40-hex SHA matching the **checked-out Git HEAD** on GitHub Actions. For local isolated tests only, `RAF_EXPECTED_COMMIT` can assert an expected SHA and the output explicitly labels this `ASSERTED_LOCAL_TEST` (not a Git verification).
- Every dependency entry needs a pinned nonzero 40-hex SHA and explicit `approved: true`, but dependency commit **existence, integrity and security** are not independently fetched or evaluated.
- The requested `checks` are a plan; only `manifest_schema`, `source_identity` and (when given) `receipt_contract` are checked by this action.
- `PASS_SCOPED` means `MANIFEST_STRUCTURE_AND_SOURCE_IDENTITY_ONLY`, not build, CI, E2E, signature, rollback, runtime or release PASS. `claim_allowed=false` is always enforced.
- `policy.recompute: impact_cone_only` documents intent. **No graph, impact-cone traversal or incremental recomputation runs in V1.** Output says `recompute=NOT_COMPUTED`.

## Usage in a consuming repository

Checkout the target commit first. Set `.raf/validation.yml` to match your repository and the actual checkout SHA (use `examples/validation.yml` as a template, never as production evidence). Reference the Action by a reviewed immutable commit after its branch has passed CI and the change has been approved. For now the draft is **not production-approved**.

```yaml
# Example step within a consumer workflow after checkout:
- name: RAF validation preflight
  uses: rafaelmeloreisnovo/RAF_ValChecks@<reviewed-full-commit-sha>
  with:
    manifest: .raf/validation.yml
```

To run it locally:

```sh
RAF_MANIFEST=examples/validation.yml RAF_EXPECTED_COMMIT=7e420be73925c133d77f2e894ea1ae62b8a70d63 sh bin/raf-valcheck.sh
python3 -m unittest discover -s tests -v
```

The local override is for contract demonstrations only. Never treat it as a cryptographic or remotely authenticated identity check.

## Receipt reuse — fail-closed

With `receipt` supplied, the validator requires all of the following:

1. A **trusted, independently obtained** SHA-256 digest of the *exact raw receipt bytes* provided in `trusted_receipt_sha256`. If missing or mismatched, reuse is blocked. A matching digest alone does **not** prove authorship, signing or attestation; the caller must separately establish trust in the digest's producer and delivery.
2. Receipt source repository, commit, raw manifest SHA-256, dependency map, validated check names and impact scope matching the current manifest.
3. `result=PASS_SCOPED`, `evidence=EXECUTED` or `REPRODUCED`, `claim_allowed=false`, a nonempty predecessor, rollback reference and falsifier labels, and timestamps that are valid and unexpired.

These rules verify a *pinned prior assertion*, not re-execution of its checks or the authenticity of its producer. Before relying on such an assertion, the consuming workflow must authorize and verify the producer, trust root, and exact scope independently. Without that external proof, do not supply a trusted digest. Never promote global PASS.

The schemas in `schemas/` define the structural contracts; the Python validator enforces the additional contextual checks and fail-closed conditions. No receipt is generated or persisted by this Action; future receipt producers must preserve append-only predecessor links and define external attestation separately.

## Tests, CI budget and rollback

- `tests/test_valchecks.py` covers positive parsing and negative cases for malformed manifests, duplicate keys, incorrect SHA, wrong repository, unsafe YAML, policy, receipt trust, expiry, mismatched scope and lineage. Tests are entirely offline.
- `.github/workflows/contract-tests.yml` is read-only and runs only on changes to the validator contract (and manual dispatch). It uses a pinned checkout Action and cancels superseded runs for the same PR/ref to reduce wasted CI.
- `main` remains unchanged while PR #1 is draft; rollback is to leave the PR unmerged or make a reviewed corrective commit on its branch. No branch deletion, force push, release, deployment, cross-repo workflow or permission change is authorized by this work.

**Authority and licensing:** The repository owner retains licensing decisions; no license is inferred from a public GitHub URL. This repo does not copy the private RAFAELIA corpus.
