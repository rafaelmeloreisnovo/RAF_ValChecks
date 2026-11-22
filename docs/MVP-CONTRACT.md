# RAF ValChecks MVP — scoped contract v1

This is an **executed local preflight and composition engine**, not a general CI scheduler, a signature verifier, an automated rollback executor, or proof of an astrophysical claim.

## Recursive semantics

- `root` is a required `group`. Exactly one **required** authored `manifest` node and one **required** authored `source` node must occur in the tree. The source node explicitly depends on the manifest node. Extensions cannot create replacements for these mandatory checks.
- Every non-`slot` module has an automatically reserved port `<module-id>.__void`, even if deeply nested. A port is an optional typed `TOKEN_VAZIO` until it receives a versioned extension. Explicit `slot` modules are also supported. Slots themselves do **not** recursively spawn more ports (finite expansion).
- `extensions` are ordered, keyed by slot id. `fill` binds one module; `compose` binds multiple modules. Both require a reason and respect the slot's allowed module types. An inserted module may contain new submodules and slots. `replace`, `suppress`, `skip_required`, and undeclared target slots **fail closed**.
- Every module has one job: strict manifest, checkout source, receipt assertion, bounded file SHA-256, contextual two-value comparison, or rollback locator. No dynamic Python import, user code execution, network request or automatic deletion.
- `required` children block their parent on `BLOCKED` or `TOKEN_VAZIO`. A deliberately unfilled *optional* slot remains `TOKEN_VAZIO`; it is not boolean `false`, numerical zero, or PASS. An optional extension that runs and fails still blocks the final receipt.
- Groups only aggregate their declared children; `PASS_SCOPED` is *not* a claim that undisclosed tests ran. Every output includes `claim_allowed=false`.

## Evidence and reuse

- `manifest` verifies syntax and structure; `source` verifies declared source commit versus checkout `HEAD`. `RAF_EXPECTED_COMMIT` is permitted **only outside GitHub Actions** for isolated local tests and is explicitly labeled `ASSERTED_LOCAL_TEST`.
- `file_sha256` reads a regular file within the selected workspace (at most 32 MiB) and checks its expected lowercase digest. It does not infer origin or file meaning.
- The `receipt` specialist checks V1 receipt assertions with the legacy contract and external trust digest. The MVP runner also optionally consumes a previous MVP receipt via `--prior` plus `--prior-sha256`.
- `--prior-sha256` MUST come from an **independent trusted channel**. Calculating it from the same untrusted receipt does **not** authenticate the producer. MVP compares the prior receipt's byte hash, self-consistent receipt ID, lineage/source, manifest digest, expiry and per-node fingerprint. The output intentionally says `external_trust_verified=false` because the runner cannot verify the outside trust channel.
- Only deterministic, unchanged specialists (`pair_relation`, `rollback_reference`) can be marked `REUSED_VALID_RECEIPT`; V1 manifest, checkout identity, file hashing and receipt checks are re-executed. `--changed scope` prevents reuse for nodes with intersecting `scope`. No changes to the source commit can reuse a prior receipt. Reuse does not assert producer signatures, actual third-party tests or global PASS.
- `--output PATH` writes once using exclusive-create plus fsync; it never replaces a prior receipt. The returned `receipt_id` is a SHA-256 of the canonical receipt body, **not a digital signature**. `rollback_ref` is a locator, never an executed rollback. A real external writer needs a separate cross-process lock and durable receipt lineage to serialize concurrent producers.

## Why a comparison needs two values and a frame

`pair_relation` compares two declared positive measurements of a compatible dimension within an explicit `frame` and `assumption`. In the shipped example, a *hypothetical model* uses 6 mm vs 13 m; this does **not** state the actual physical diameters of the Sun or any star. This specialist teaches that large/small is relative to a reference and a shared unit, not an absolute universal truth.

## Commands

```sh
# Existing V1 contract gate remains the default.
RAF_MANIFEST=.raf/validation.yml sh bin/raf-valcheck.sh

# No test or write: inspect topology and dependencies.
python3 bin/raf_mvp.py plan --topology examples/topology.mvp.json

# Run modular preflight with source at checkout HEAD; JSON to stdout only.
python3 bin/raf_mvp.py run --topology .raf/topology.json --manifest .raf/validation.yml

# Optional append-only receipt and explicit rollback locator.
python3 bin/raf_mvp.py run --topology .raf/topology.json --manifest .raf/validation.yml \
  --output .raf/receipts/new-unique-name.json --rollback-ref 'git:reviewed-revert'

# Constrained replay with independently trusted hash supplied by caller.
python3 bin/raf_mvp.py run --topology .raf/topology.json --manifest .raf/validation.yml \
  --prior .raf/receipts/older.json --prior-sha256 "$TRUSTED_PREVIOUS_DIGEST" --changed source_files
```

Consumer Action example (pin the `uses:` repository to an independently reviewed **full commit SHA**):

```yaml
- uses: rafaelmeloreisnovo/RAF_ValChecks@FULL_REVIEWED_COMMIT_SHA
  with:
    mode: mvp
    manifest: .raf/validation.yml
    topology: .raf/topology.json
```

## Evidence ladder and limits

`DOCUMENTED` → `IMPLEMENTED_UNTESTED` → `LOCAL_TESTED_SCOPED` → `EXACT_HEAD_CI_SCOPED` → `INTEGRATED_CONSUMER_EVIDENCE` → `DEVICE_EVIDENCE` are **distinct** states. The MVP neither infers latter states from former ones nor implements arbitrary project CI. An extension can add another specialist, but its validator must be reviewed and tested separately. For now module kinds are allowlisted and internal.

No direct writes to Drive, Supabase, Notion, Slack, rulesets, branch protection, releases or consumer repositories occur. No external dependencies or secrets are required. Relative comparison is a model, not science validation.

## Incremental impact-cone advisory (post-MVP)

`python3 bin/raf_mvp.py impact --topology examples/topology.mvp.json --changed model`
provides a **read-only plan**, not permission to skip checks. The planner traces
propagating effects through dependencies, nested group aggregation and versioned
slot extensions. `manifest` and `source` remain mandatory at every run.

Declared changes are **not** a verified Git diff. If a scope is absent or unknown
then `impact_advisory.status=TOKEN_VAZIO`, all nodes are affected conservatively
and reuse is disabled. Known-scope unaffected candidates are *only candidates*;
`runtime_skipping_authorized=false` and `change_source_verified=false` always.
Reusing deterministic leaf assertions additionally requires a valid, externally
trusted prior receipt and matching fingerprints. No business, security or CI
check is silently skipped because the user provided `--changed`.

Safety budgets: maximum 32 levels, 512 represented nodes including virtual slots,
and 128 declared extension patches. Overflow is a typed contract rejection, not
a truncation or implicit success. For larger graphs, use independently verified
shards connected through a future federation contract.
