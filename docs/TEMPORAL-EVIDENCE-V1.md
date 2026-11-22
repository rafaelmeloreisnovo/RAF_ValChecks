# Temporal Evidence V1 — candidate discovery only

This is a bounded, offline, **non-causal** anomaly/sequence explorer for typed
`TOKEN_VAZIO` and testable hypotheses. It does not execute device workloads,
collect personal data, discover latent causes with statistical guarantees, or
verify the authenticity of a producer receipt.

## Inputs and limits

A JSON document has `version: 1`, `window_ms` (1..86400000), `min_support`
(2..32), and `events` (at most 512) over at most 16 declared channels. Each
observation requires a stable `id`, `channel`, nonnegative integer
`occurred_ms` and `observed_ms`, `source_ref`, and an explicit `quality` of
`good`, `suspect`, or `missing`. It can have `receipt_ref`, `parent`, and a
bounded integer `value`. `missing` cannot have zero substituted as a value.

Suspect observations, duplicate IDs, missing receipt references, unresolved
parents and timestamps observed before they occurred are **not deleted**:
only metadata anomaly counts are emitted, without the user payload. They are
excluded from candidate correlations; all reasons remain inspectable.

The one-to-one lag matcher prevents a single downstream event from being counted
as many independent effects. A lagged-association hypothesis needs repeated
matches in a window and remains `causality_verified=false`,
`statistical_significance_verified=false`, `negative_controls_passed=false`.
A two-hop path is a candidate cascade, not evidence of mediation. Sources may
share hidden causes; clock skew and selection bias can mimic directionality.

`TOKEN_VAZIO` means insufficient eligible observations or a coverage anomaly.
This does not imply that the dataset is worthless. It gives the falsifier an
explicit target: deduplication, authenticated receipts, improved timestamps,
independent holdout, or a controlled perturbation. Every normal result is
`OBSERVATION_ONLY`; neither is permission to skip CI.

The raw byte SHA-256 can be checked against an independently supplied digest.
This check is *not* digital signing or external producer authentication. If the
caller cannot validate an external trusted receipt, the output retains
`external_source_trust_verified=false` and an explicit typed gap.

## Entry points

```sh
# Strictly read-only standalone exploration. No topology or manifest needed.
python3 bin/raf_mvp.py temporal --workspace . \
  --events examples/temporal-observations.v1.json

# Bind the dataset digest before running a registered specialist in a versioned
# topology. Exact V1 manifest and source checkout still required.
python3 bin/raf_mvp.py plan --topology examples/topology.temporal.json
python3 bin/raf_mvp.py run --topology examples/topology.temporal.json \
  --manifest .raf/validation.json
```

## Federated authority boundary

- The authoritative producer for BitOmega, B7 buffering and stability is
  `rafaelmeloreisnovo/Vectras-VM-Android`, not this repository.
- `engine/rmr/src/bitomega.c` has a `VOID` and a `NOISE` state; these are state
  machine symbols, **not** identical to missing evidence in this engine.
- `engine/rmr/src/raf_b7_orchestrator.c` has fixed-size ring receipts with
  epoch, offset, stage and CRC fields; they **do not contain trusted UTC event
  timestamps**. Never invent `occurred_ms` from an epoch or infer CPU temperature,
  CPU utilization, memory pressure or physical device stability from CRC alone.
- Termux Android belongs to `rafaelmeloreisnovo/termux-app-rafacodephi` and must
  produce its own scoped runtime evidence before integration claims.
- The literal code filenames `iiop.c`, `bitghost.c` and `pvr_magisck` were not
  confirmed in the relevant producer trees during preflight. Their paths and
  ABI/authority remain typed unknowns, not silently created substitutes.
- No direct Vectra, Termux, PVR, RMR or Supabase producer code, CI, schedules,
  permissions or releases are modified by this capability.

An approved adapter may translate **metadata only** into this format, with
producer-issued refs, provenance, timestamp semantics, privacy classification,
lineage and user-approved authority. Do not export raw VM memory, guest paths,
logs, voice data, device identities or raw host addresses into public CI.
