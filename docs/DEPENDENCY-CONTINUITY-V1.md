# Dependency Continuity / GC / Friction — advisory V1

**State:** SOURCE_IMPLEMENTED / CI_PENDING / CONSUMER_NOT_INTEGRATED. No automatic merges,
releases, workflow stops, security-policy edits, or mutation of existing dependencies.

## Goal and three independent identities

- **Source:** compile the known immutable 40-byte Git SHA, not `main`, a moving tag,
  a date string, or the current latest package. Record its Git committer time as
  **asserted metadata** only, never as trusted timestamping.
- **Resolved dependencies:** compile the **transitive** versions and digests that
  actually belong to that checkout. Stable source SHA alone is insufficient if
  Gradle/npm/pip resolution, compiler/plugins or action refs can float.
- **Runtime:** a clean build is not performance proof. The JVM may allocate or
  collect under different workloads, hardware, heap and GC settings. Measure
  allocation bytes/operation, GC event rate/pause p99, RSS peak, CPU time and
  latency, and compare under the **same load/environment** with repeated samples.
  Native C need not have GC but still requires allocation/copy/fragmentation data.

## Signaling and dependency comparison

`dependency-guard` consumes `git-impact` for exact ancestry and a clean HEAD.
It flags changed `build.gradle`, lockfiles, `requirements*`, `pom.xml`,
`package[-lock].json`, Actions workflows and related descriptors. Changed
*descriptor* != changed resolved dependency; metadata-only diffs can be false
positives, therefore the alert is deliberately **POSSIBLE DEPENDENCY CHANGE**.

Use optional producer-committed JSON snapshots at the same path in BASE/HEAD.
The tool reads **each file from its exact Git tree** (`git show SHA:path`), not
untracked runtime files. Each file is bounded at 1 MiB. Their contents remain
producer **assertions**, not attested resolver output.

Graph snapshot example (values are **synthetic fixtures**, not the user's build):

```json
{"schema":1,"resolution":"FULL_TRANSITIVE_RESOLVED",
 "components":[{"id":"org.example:component","version":"1.0.0",
                "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],
 "edges":[{"consumer":"app","dependency":"org.example:component"}]}
```

Runtime snapshot example (**synthetic**, not a measured benchmark):

```json
{"schema":1,"runtime":"JVM","workload_id":"build-scenario-X",
 "environment_id":"same-device-and-heap","samples":8,
 "metrics":{"alloc_bytes_per_op":100,"gc_pause_p99_ms":2.5,
            "gc_events_per_1000_ops":2,"cpu_ms_per_op":3.1,"peak_rss_bytes":2000000}}
```

Snapshot hashes are SHA-256 of **raw committed bytes**. Identical performance
snapshot bytes before/after a changed build descriptor are a **gap**, not proof
of no regression. Missing data, changed workload/environment, zero denominators,
insufficient metric types and absent approved thresholds remain typed unknowns.
No P0 severity or risk acceptance is inferred from versions or metrics alone.

## Human decision matrix — do not automate unsafe assumptions

| Evidence | Outcome |
|---|---|
| No descriptor delta observed in bounded Git interval | `OBSERVATION_ONLY`; not a global dependency proof |
| Descriptor touched, transitive graph unavailable | `TOKEN_VAZIO`, warn loudly, **do not promote** |
| Graph changes with new edges/revisions | Revalidate direct and indirect consumers; retained predecessor |
| New functionality increases allocation/GC/friction | Profile; make optional when safe, optimize or defer promotion |
| Exact-head build/API/safety gate fails due to update | **P0 — REVISAR COM URGÊNCIA**, draft/HOLD on producing PR; retain stable version |
| Security vulnerability in stable version | Review urgency and alternatives separately; preserving old version forever is **not** a security policy |
| Reproducible comparator in new environment | Not comparable; preserve both data points, use a controlled A/B test |

Don't equate all library version numbering to SemVer. When a library follows
SemVer, `MAJOR.MINOR.PATCH` normally means incompatible API change, backward-
compatible features, backward-compatible fix, respectively. This is **not** a
compatibility guarantee across Gradle, Android, NDK, JVM, ABI, behavior or a
project that uses another scheme. Release-note claims are hypotheses until
contract and consumer tests support them.

## Energy and impact principle

Use a fixed workload and the smallest sufficient test cone; **never skip**
mandatory security/ABI/compatibility gates from this advisory. Prefer attaching
new optional behavior instead of injecting overhead into a stable hot path.
Use JVM measurements (JFR, allocation profiling, GC logs) in a controlled
environment; quantify native heap/copy/memory bandwidth independently.
Pass/fail cannot be calculated from one noisy timing sample or an arbitrary
percentage. An owner-approved per-metric tolerance and negative controls are
required before any non-regression **claim**.

## Evidence boundary

`pinned_source_checkout_verified=true` verifies local Git objects and clean HEAD;
`independent_producer_authenticity_verified=false`, `claim_allowed=false`,
`performance_claim_allowed=false`, `promote_dependency_update_authorized=false`,
`runtime_skipping_authorized=false` throughout. The tool never changes or
interrupts dependencies in a running program. To enforce a consumer's merge
policy, the owner must integrate an independently trusted gate in that producer.
