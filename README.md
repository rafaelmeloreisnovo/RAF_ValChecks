# RAF_ValChecks — modular evidence preflight MVP

**Core:** immutable Git evidence and typed, recursive, fail-closed validation. The engine checks only what its registered specialists actually perform; `claim_allowed=false` always.

Two public entrypoints coexist without breaking consumers:

| Mode | Entry | What it actually proves |
| --- | --- | --- |
| `contract` (default) | `sh bin/raf-valcheck.sh` | V1 manifest/source identity; optionally a trusted V1 receipt contract |
| `mvp` (opt-in) | `python3 bin/raf_mvp.py run ...` | Recursive topology, individual module evidence, typed gaps, optional trusted receipt reuse |

### MVP modules

`manifest` → structural manifest validation; `source` → exact checkout identity; `receipt` → V1 receipt assertions; `file_sha256` → bounded file digest; `pair_relation` → relative comparison in a declared frame; `rollback_reference` → declaration of rollback locator only; `group` → structured aggregation; `slot` → typed vacant extension point.

**Every non-slot module gets a reserved `<module-id>.__void` port.** A parent may `fill` or `compose` versioned submodules into an allowed slot; attempts to suppress or replace required gates are rejected. A slot left empty is `TOKEN_VAZIO`, never PASS or zero. Recursion is bounded; optional slots do not by themselves block success, but failed inserted modules do.

`pair_relation` includes the example **6 mm vs 13 m in a hypothetical scaled model**. These are not empirical star measurements. Comparisons require a common dimension and explicit frame of reference.

### Try the MVP

```sh
python3 bin/raf_mvp.py plan --topology examples/topology.mvp.json
python3 bin/raf_mvp.py impact --topology examples/topology.mvp.json --changed model
python3 bin/raf_mvp.py run --topology examples/topology.mvp.json --manifest .raf/validation.yml
python3 -m unittest discover -s tests -v
```

For a local contract-only demonstration with `examples/validation.yml`, `RAF_EXPECTED_COMMIT=7e420be73925c133d77f2e894ea1ae62b8a70d63` asserts a synthetic checked-out SHA, marked `ASSERTED_LOCAL_TEST`. Never use this substitution to claim real checkout identity in production; GitHub Actions always reads Git HEAD.

### Impact-cone analyzer (advisory)

A separate deterministic analyzer traces affected nodes through recursive dependencies.
It **does not execute, skip, or authorize CI checks**. It requires caller-declared
scopes, rechecks mandatory identity gates, and returns `TOKEN_VAZIO` for an absent
or unknown change scope. Unaffected nodes are candidates only. Receipt reuse is
forbidden under such uncertainty. The user-supplied change set is *not* a verified
Git diff. See [contract](docs/MVP-CONTRACT.md).

### Verified Git change coverage (opt-in, read-only)

`git-impact` now reads a clean, exact local Git `base..HEAD` interval and
classifies changed paths using the explicit versioned
[`change-routes.v1.json`](examples/change-routes.v1.json) policy.
Unmapped paths, unknown topology scopes, empty diffs and changes to validator
control-plane paths produce a **typed unknown** and an all-nodes impact plan.
A path-to-scope rule is a hypothesis, never proof that other dependencies do not
exist. All results keep `runtime_skipping_authorized=false`.

```sh
python3 bin/raf_mvp.py git-impact --topology examples/topology.mvp.json \
  --routes examples/change-routes.v1.json --workspace . \
  --base "$(git rev-parse HEAD^)" --head "$(git rev-parse HEAD)"
```

Run before generating untracked files in the checkout. No implicit network
fetch, CI cancellation or receipt promotion occurs. Full boundaries and
adversarial evidence: [Git coverage contract](docs/GIT-COVERAGE-V1.md).

### CI and custody

- One read-only PR/dispatch workflow exercises legacy contract regression, graph plans, bad manifest rejection, recursive module execution, and the composite Action. A SHA-pinned checkout is used; no `pip` packages are installed.
- An MVP receipt has a content-based ID and optionally an append-only file name, an expiry, a predecessor digest, scope fingerprints, typed voids and a rollback **reference**. It is **not** a signed or provider-attested receipt. External trust of a previous receipt digest is a prerequisite for reuse, not something computed from the same untrusted file.
- For real consumers, pin the Action reference to an immutable reviewed commit, and provide a source manifest that matches the consuming repository’s checkout HEAD.
- No `PASS_GLOBAL`, merge authorization, actual rollback, device testing, scientific measurement, producer authentication, GitHub retention enforcement, or global impact-cone scheduler is claimed.

See [MVP contract and explicit boundaries](docs/MVP-CONTRACT.md), [recursive topology JSON Schema](schemas/topology-mvp.schema.json), [example topology](examples/topology.mvp.json), and [V1 schemas](schemas/validation-manifest.schema.json). The V1 interface is retained for compatibility. The repository owner retains decisions about an explicit software license (none inferred).

### Temporal unknowns and falsifier candidates (optional)

`python3 bin/raf_mvp.py temporal --workspace . --events examples/temporal-observations.v1.json`
performs a bounded, read-only analysis of repeated event orderings. Bad data,
missing receipt refs, duplicate identities and temporal inversions generate
**typed negative coverage**. The plugin `temporal_audit` can be inserted into a
`.__void` slot with a pinned SHA-256. Results are observations or candidate
associations only: there is no proof of causality, signature trust, runtime
skipping, or external producer integration.
See [Temporal Evidence V1](docs/TEMPORAL-EVIDENCE-V1.md).
