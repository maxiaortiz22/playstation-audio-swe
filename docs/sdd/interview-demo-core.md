# Interview Demo Core

- **Document type:** implementation-scope profile
- **Applies to:** a focused interview demonstration within M1
- **Authority:** subordinate to Accepted specifications and ADRs
- **Verification effect:** none; this profile does not change specification status

## Purpose and authority

Interview Demo Core selects a small, coherent path through the Accepted M1
contracts so the repository can demonstrate its architecture and diagnostic
value earlier. It is not a replacement milestone, an amendment to a
specification, or a claim that M1 is complete.

Accepted specifications remain the authority when this profile is incomplete,
ambiguous, or inconsistent with them. Implementing every item here supplies
evidence only for the named subset and partial requirements below. It does not
move any specification to `Verified`; that still requires evidence for every
mandatory requirement under the SDD lifecycle.

The profile contains exactly three slices. Work outside them remains on the M1
roadmap or in the documented future milestones.

## DEMO-1 — Native runtime showcase

### Included

- One coarse operation crosses Python -> pybind11 -> C++ -> Python.
- The boundary accepts C-contiguous float32 arrays shaped `(frames, channels)`
  for mono and stereo, with explicit ownership and mutability behavior.
- Boundary failures identify unsupported dtype, rank, shape, channel count, or
  contiguity instead of reaching native processing ambiguously.
- Native passthrough processes the same stream with at least two block sizes,
  including a partial final block with an explicit valid-frame count.
- An independently testable C++ SPSC queue uses and exposes a non-zero
  power-of-two capacity and demonstrates empty/full transitions, FIFO order,
  wraparound, and preservation of unread data after a failed push.

### Excluded

No complete concurrent callback harness, runtime timing distribution,
telemetry transport, cancellation path, long-running stress, sanitizer claim,
or performance claim belongs to this slice.

### Slice success

A reviewer can run focused native and cross-language tests and observe exact
passthrough output for both channel layouts and block partitions, actionable
buffer rejection, and the listed SPSC invariants without importing Python into
the native queue tests.

## DEMO-2 — Audio analysis showcase

### Included

- Python injects deterministic labeled integer delay, stereo channel swap, and
  dropout faults; parameters are retained for reproduction.
- Structural validation covers sample rate, channel count/labels, non-finite
  samples, empty/short overlap, and input immutability before similarity
  analysis.
- Integer cross-correlation uses the accepted M1 `OP-B-intermediate` values for
  the M1 manifest/policy only, with bounded search, signed peak, and ambiguity
  outcome. It is not a universal default.
- Raw latency is reported and evaluated before any declared time alignment.
- Aligned residual views record the measured integer transform and affected
  metrics, contain only valid overlap pairs, and exclude missing counterparts
  rather than zero-padding them.
- Analysis reports per-channel residual peak and RMS, including a clean/null
  residual case and explicit RMS floor, plus per-channel gain in dB and a
  distinct polarity diagnosis.
- Channel analysis uses independent content and reports observed-to-expected
  stereo mapping, score, confidence, and the configured mapping margin.
- Dropout analysis reports the affected channel set, exact-zero or near-silence
  classification, and start/end interval under explicit floors and duration.

### Excluded

No spectral aggregation, clock-drift estimator, click detector, repeated-block
detector, clipping detector, DC-offset detector, or crosstalk measurement
belongs to this slice.

### Slice success

Focused positive, negative, and boundary fixtures reproduce the three labeled
faults; clean input remains clean; delay cannot be hidden by alignment; and
each valid detector returns policy-ready values with explicit units.

## DEMO-3 — End-to-end interview workflow

### Included

- One command executes manifest -> deterministic stimulus -> native passthrough
  -> injected candidate -> analysis -> policies -> JSON and HTML.
- The command covers separate `clean`, `delay`, `channel-swap`, and `dropout`
  scenarios using the same runner and manifests locally and in fast CI.
- Failed policies show actual value, expected condition, unit, related
  requirement IDs, localized frame/second intervals where relevant, and a
  copy-pastable reproduction command.
- Process outcomes retain the accepted meanings: `0` pass, `1` policy failure,
  `2` invalid input or mandatory measurement, and `3` internal runner/reporting
  error.
- HTML is simple and offline, using no hosted dashboard or required network
  resource. JSON remains the machine-readable result.

### Excluded

This slice does not create a dashboard, distributed service, exhaustive
artifact system, extended CI tier, or full M1 evidence package.

### Slice success

The clean scenario passes; each fault scenario fails for its intended reason;
JSON and HTML agree on status and diagnosis; every report can reproduce its
scenario; invalid and internal failures remain distinguishable from policy
failures; and the deterministic workflow completes in fast CI.

## Requirement coverage matrix

“Demonstrated” below means evidence targeted by this profile after the slices
are implemented and tested. It never means the owning specification is
`Verified`.

| Slice | Requirements demonstrated by the slice | Partial requirements | Explicitly deferred |
|---|---|---|---|
| DEMO-1 | `SYS-BND-001..003`, `SYS-BND-005`, `SYS-EXE-002..004`, `RT-SPSC-001..002`, `RT-QUE-001..004`, `RT-QUE-006`, `RT-BLK-002`, `RT-BLK-004` | `RT-SPSC-003..006`, `RT-PY-001..003` | `RT-MEM-*`, `RT-CB-*`, `RT-OVR-*`, `RT-TIME-*`, `RT-BLK-001`, `RT-BLK-003`, `RT-BLK-005`, `RT-PY-004`, concurrent/long stress |
| DEMO-2 | `SYS-ANL-001..002`, `CMP-STR-001..005`, `CMP-ALIGN-001..007`, `CMP-COMP-001..003`, `CMP-COMP-005`, `CMP-MET-001..002`, `CMP-MET-009`, `CMP-CH-001..002`, `CMP-CH-004`, `CMP-EVT-002` | `SYS-TTV-001..003`, `CMP-MET-008`, `CMP-DIAG-001..005` | `CMP-ALIGN-008`, `CMP-MET-003..007`, spectral aggregation, `CMP-CH-003`, `CMP-EVT-001`, `CMP-EVT-003..006`, `CMP-DRIFT-*` |
| DEMO-3 | `SYS-EXE-001`, `SYS-DIAG-001..004`, `POL-EVAL-001..006`, `RPT-SCHEMA-003..004`, `RPT-HTML-001..004`, `RPT-HTML-008..009`, `RPT-REP-001`, `CI-RUN-001..002`, `CI-RUN-004`, `CI-RUN-009..010` | `SYS-REP-003..004`, `SYS-EXE-006..007`, `SYS-DIAG-006`, `POL-EVAL-007..010`, `RPT-SCHEMA-001..002`, `RPT-SCHEMA-005..009`, `RPT-REP-002..005` | Extended CI, exhaustive artifact handling, hosted retention/upload policy, dashboard, remaining M1 scenarios and evidence |

## Profile-level success criteria

Interview Demo Core succeeds only when all of the following are true:

1. The three slice-success statements have automated, requirement-linked
   evidence in the fast tier.
2. The four end-to-end scenarios are deterministic and use explicit manifests,
   fault parameters, policies, and reproduction commands.
3. Raw latency, declared alignment, residual metrics, channel mapping, and
   dropout localization remain distinct observations in diagnostics.
4. Native-only SPSC evidence and the coarse Python/native boundary are both
   reviewable without a complete callback simulation.
5. Documentation and reports state that the profile is a subset and do not
   claim M1 or any Accepted specification is `Verified`.

## Deferred roadmap and independence

The full M1 roadmap remains intact. Biquad and general resampler conformance,
extended timing and stress evidence, drift analysis, HRTF/spatial validation,
and statistical regression remain future extensions governed by their owning
specifications and acceptance gates.

This repository and the Interview Demo Core are independent educational work.
Their results demonstrate general audio-validation engineering and do not
imply access to PlayStation or Sony proprietary knowledge, source code, APIs,
assets, requirements, or internal behavior.
