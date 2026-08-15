# SPEC-000: System and product contract

- **Status:** Accepted
- **Owners:** Repository maintainers
- **Created:** 2026-08-14
- **Last updated:** 2026-08-15
- **Target milestone:** M1 - End-to-end regression demonstration
- **Depends on:** ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005, ADR-0006

## Context

The project demonstrates how a senior software engineer can transform ambiguous audio quality questions into maintainable validation software. The system must exercise C++, Python, audio analysis, automation, numerical reasoning, real-time constraints, CI, and developer-facing diagnostics as one coherent product.

The project uses a simulated audio SDK and controlled faults. It does not require proprietary platform APIs or claim to reproduce a commercial console implementation.

## Goals

- Run deterministic audio experiments against a native system under test.
- Compare a baseline and candidate without hiding latency, level, polarity, or channel regressions.
- Validate filters, resampling, streaming behavior, and real-time-style transport.
- Produce evidence that is sufficient to reproduce and begin debugging a failure.
- Demonstrate robust C++/Python boundaries through pybind11.
- Support local development and automated CI using the same manifests.
- Make all thresholds, transformations, baselines, and assumptions auditable.
- Validate the validators through labeled fault injection.

## Non-goals

- Emulating a PlayStation SDK, operating system, or DevKit.
- Claiming platform certification or compliance.
- Replacing subjective listening evaluation.
- Implementing PESQ, POLQA, or PEAQ algorithms from scratch.
- Operating a production distributed worker fleet, artifact store, or hardware lab.
- Guaranteeing hard real-time behavior on a general-purpose host OS.
- Supporting arbitrary compressed formats in M1.

## Milestone 1 requirement scope

| Requirement family | M1 disposition |
|---|---|
| `SYS-*` except `SYS-REP-002`, plus `RT-*`, `POL-*`, `RPT-*`, `CI-*` | Mandatory M1 contract; extended-tier evidence is still required before `Verified` where specified |
| `SYS-REP-002` | Conditional M2-or-later asset-input contract; M1 rejects asset-based input manifests |
| `CMP-*` | Mandatory M1 comparator contract, but implementation is blocked while SPEC-001 remains `Review` |
| `FIL-*` | Intended M1 filter slice, blocked while combined SPEC-003 remains `Review` |
| `SRC-*` | M2; no general resampler SUT or conformance claim in M1 |
| `SPA-*`, `STAT-*` | M2; not part of M1 exit |

A requirement assigned to an extended execution tier is still M1 scope when
this table says so; the tier controls when evidence runs, not whether the
requirement exists.

## Actors

- **Test author:** defines stimulus, SUT configuration, metrics, and policy.
- **Developer:** runs validation locally and inspects diagnostics.
- **CI runner:** executes an immutable manifest and publishes results.
- **Baseline reviewer:** approves intentional baseline or threshold changes.
- **System under test (SUT):** a native processing graph selected by the manifest.

## Terminology

- **Baseline:** approved result or reference output associated with explicit provenance.
- **Candidate:** output produced by the change being evaluated.
- **Stimulus:** deterministic input audio and associated generation parameters.
- **Raw metric:** a measurement before policy evaluation.
- **Policy:** rule converting metrics into informational, warning, or failure outcomes.
- **Compensation:** an explicitly allowed transform such as time shift or gain adjustment.
- **Fault injection:** deliberate, labeled behavior used to verify detector sensitivity.
- **Artifact:** WAV, JSON, plot, report, log, or trace supporting a validation result.
- **Fast tier:** deterministic tests suitable for every pull request.
- **Extended tier:** stress, statistical, spatial, or high-resolution tests intended for nightly/release runs.

## Logical components

1. **Manifest loader:** validates configuration and schema version.
2. **Stimulus generator:** produces deterministic PCM and metadata.
3. **Native harness:** executes a selected SUT using block processing.
4. **Fault injector:** introduces one or more declared defects.
5. **Capture and telemetry:** records output and runtime counters.
6. **Analysis engine:** computes time, frequency, channel, anomaly, and performance metrics.
7. **Policy engine:** evaluates metrics against explicit rules.
8. **Reporter:** emits machine-readable and human-readable evidence.
9. **CI adapter:** maps outcomes to process exit codes and artifacts.

## Canonical data model

### Audio buffer

Unless a feature specification states otherwise, M1 canonical audio is:

- Sample format: IEEE 754 32-bit floating point.
- Nominal full-scale range: `[-1.0, +1.0]`.
- Memory layout at the Python boundary: C-contiguous array shaped `(frames, channels)`.
- Memory layout inside a native block: explicitly documented interleaved or planar representation; conversion occurs only at a named boundary.
- Sample rate: positive integer in Hz.
- Channel count: positive integer with a manifest-defined channel map.
- Time origin: frame zero of the captured buffer, with pre-roll described separately.

### Manifest

M1 manifests and their embedded policies use strict UTF-8 JSON as decided by
ADR-0004. YAML, includes, and external policy references are not accepted M1
inputs. The manifest contains:

- Schema version and test ID.
- Human-readable purpose and owner.
- Deterministic seed.
- Stimulus definition or asset hash.
- Sample rate, duration, channel map, and block-size set.
- SUT and fault-injection parameters.
- Permitted comparison transforms.
- Requested metrics and policies.
- Artifact policy and execution tier.

### Result

A result contains:

- Result schema version and run ID.
- Test ID, requirement IDs, and manifest digest.
- Source revision and dirty-worktree indicator.
- Native and Python toolchain information.
- Platform, architecture, and relevant runtime configuration.
- Raw metrics with units and validity.
- Policy evaluations and final status.
- Artifact inventory with relative paths and hashes.
- Reproduction command.

## System requirements

### Reproducibility

- **SYS-REP-001:** Every generated stochastic stimulus SHALL use a manifest-provided seed recorded in the result.
- **SYS-REP-002:** If a future accepted feature permits an asset-based stimulus, it SHALL record and verify a cryptographic content digest; M1 SHALL reject asset-based input manifests.
- **SYS-REP-003:** Every result SHALL record the manifest digest, source revision, dependency revision, toolchain, and platform fingerprint.
- **SYS-REP-004:** A local run and CI run using the same manifest and deterministic SUT SHALL produce equivalent raw metrics within the metric's documented numerical tolerance.
- **SYS-REP-005:** Baselines SHALL be immutable inputs during validation; a validation run SHALL NOT silently update them.

### Native/Python separation

- **SYS-BND-001:** Core native libraries SHALL build and test without importing Python or depending on Python object lifetimes.
- **SYS-BND-002:** Python SHALL invoke native processing through coarse-grained pybind11 operations.
- **SYS-BND-003:** Boundary validation SHALL reject unsupported dtype, rank, shape, channel count, or non-contiguous layout with a documented exception.
- **SYS-BND-004:** The simulated real-time callback SHALL NOT access Python objects or acquire the Python GIL.
- **SYS-BND-005:** Buffer ownership and mutability SHALL be explicit for every binding.

### Execution

- **SYS-EXE-001:** A manifest SHALL identify exactly one SUT configuration and zero or more labeled faults.
- **SYS-EXE-002:** The harness SHALL support at least 48 kHz mono and stereo float32 processing in M1.
- **SYS-EXE-003:** The same offline SUT SHALL be executable using at least two block sizes so chunking invariance can be tested.
- **SYS-EXE-004:** Native errors SHALL produce structured failure information rather than an unexplained process termination, except for sanitizer-identified fatal defects.
- **SYS-EXE-005:** Non-finite output samples SHALL be treated as structural failures and SHALL NOT be converted into ordinary numerical similarity scores.
- **SYS-EXE-006:** A manifest SHALL validate the schema version, test identity, owner, deterministic stimulus definition, audio format, channel map, block sizes, SUT, labeled faults, permitted transforms, metrics, policies, artifact policy, and execution tier before native execution begins.
- **SYS-EXE-007:** M1 manifest and policy readers SHALL accept only strict UTF-8 JSON, reject duplicate keys, comments, trailing commas, non-finite tokens, implicit type coercion, and schema-unknown authoring fields, and report failures with document and schema paths.

### Analysis and policy

- **SYS-ANL-001:** Analysis SHALL preserve raw measurements separately from compensated measurements.
- **SYS-ANL-002:** Every compensation SHALL be enabled explicitly by the manifest and recorded in the result.
- **SYS-ANL-003:** Policy evaluation SHALL reject a rule whose units are incompatible with its metric.
- **SYS-ANL-004:** A missing or invalid mandatory metric SHALL fail the owning policy rather than defaulting to pass.
- **SYS-ANL-005:** Structural defects such as channel-count mismatch, non-finite samples, or undecodable input SHALL take precedence over similarity scoring.

### Diagnostics

- **SYS-DIAG-001:** Every failure SHALL identify the violated policy, expected condition, actual value, units, and requirement IDs.
- **SYS-DIAG-002:** Time-localized defects SHALL report frame index and seconds.
- **SYS-DIAG-003:** Every result SHALL contain a deterministic reproduction command that references the original manifest.
- **SYS-DIAG-004:** Human-readable reports SHALL avoid presenting compensated outputs as raw observations.
- **SYS-DIAG-005:** Artifact creation failures SHALL be reported without erasing the underlying validation outcome.
- **SYS-DIAG-006:** Every result SHALL record the result schema version, run and test identity, requirement IDs, manifest digest, source and dependency revisions, dirty state, resolved toolchain and platform, raw metrics and validity, policy evaluations, separate `validation_status`, `run_status`, and `completion_status`, artifact inventory, and a reproduction command.

### Test-the-validator

- **SYS-TTV-001:** Every mandatory defect detector SHALL have at least one labeled positive fixture and one legitimate negative fixture.
- **SYS-TTV-002:** Fault parameters SHALL be stored with the result so the expected detector response is auditable.
- **SYS-TTV-003:** Integration tests SHALL assert both the final status and the diagnostic explanation.
- **SYS-TTV-004:** A detector SHALL NOT be accepted solely because it detects the same signal used to tune its threshold.

## Execution tiers

### Fast tier

- Native and Python unit tests.
- Small deterministic integration vectors.
- Alignment and residual analysis.
- Basic filter, channel, and fault-injection tests.
- Schema and report generation.
- Short deterministic drift algebra and validity cases.

Target: suitable for every pull request with no external hardware or network access.

### Extended tier

- Long SPSC stress, ThreadSanitizer, and host timing characterization.
- High-resolution filter sweeps in M1 and resampler sweeps beginning in M2.
- Long-duration drift sensitivity and statistical repeated measurements.
- SOFA-based spatial conformance.
- Larger diagnostic artifacts.

Target: nightly, release, or manually selected CI.

The required M1 compiler, platform, Python, and sanitizer jobs are defined by
ADR-0006. General resampler conformance is an M2 feature even though its future
contract remains in SPEC-003. M1 input stimuli are generated at runtime under
ADR-0005; WAV files are diagnostic outputs rather than normative input
fixtures.

## M1 acceptance criteria

1. One command executes a complete manifest through Python, pybind11, C++, analysis, policy, and reporting.
2. A clean baseline scenario passes with reproducible metrics.
3. A candidate containing delay, channel swap, and dropout fails with three distinct diagnoses.
4. Delay is reported before alignment, while residual analysis operates on the declared aligned overlap.
5. The report contains JSON, HTML, audio evidence, source/environment provenance, and a reproduction command.
6. Unit and integration tests trace to every M1 mandatory requirement.
7. CI runs the fast tier and uploads diagnostics on failure.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-SYS-001` | `SYS-REP-001`, `SYS-REP-003`, `SYS-REP-004`, `SYS-REP-005` | Repeat generated stimuli and attempt baseline mutation | Equivalent metrics, complete provenance, immutable baseline |
| `T-SYS-ASSET-001` | `SYS-REP-002` | In M1 reject an asset-based input manifest; after a future asset feature is accepted, verify content mismatch handling | Explicit M1 rejection; future execution requires matching digest |
| `T-SYS-002` | `SYS-BND-001`, `SYS-BND-002`, `SYS-BND-003`, `SYS-BND-004`, `SYS-BND-005` | Build native-only, then pass valid and invalid Python buffers through one coarse call | Independent native core, explicit ownership, documented rejection, no callback GIL access |
| `T-SYS-003` | `SYS-EXE-001`, `SYS-EXE-002`, `SYS-EXE-003`, `SYS-EXE-004`, `SYS-EXE-006`, `SYS-EXE-007` | Validate strict/invalid JSON, process mono/stereo at two block sizes, and force a recoverable native error | Path-specific schema errors, complete execution, equivalent output, structured native error |
| `T-SYS-004` | `SYS-ANL-001`, `SYS-ANL-002` | Candidate has known delay | Raw delay preserved; aligned residual separate |
| `T-SYS-005` | `SYS-DIAG-001`, `SYS-DIAG-002`, `SYS-DIAG-003`, `SYS-DIAG-004`, `SYS-DIAG-005`, `SYS-DIAG-006` | Inject localized faults and force one artifact failure | Actionable dual-status result, provenance, and packaged reproduction command |
| `T-SYS-006` | `SYS-TTV-001`, `SYS-TTV-002`, `SYS-TTV-003`, `SYS-TTV-004` | Run disjoint labeled calibration and holdout corpora | Expected classifications, stored fault parameters, explanations, no tuning leakage |
| `T-SYS-007` | `SYS-EXE-005`, `SYS-ANL-005` | Inject NaN | Structural failure; no misleading similarity pass |
| `T-POL-001` | `SYS-ANL-003`, `SYS-ANL-004` | Validate incompatible-unit and missing-mandatory-metric policies | Policy rejected or run invalid; never defaults to pass |

## Dependencies

- SPEC-001 defines mandatory M1 comparison semantics; its recorded calibration
  gate blocks comparator implementation.
- SPEC-002 defines accepted M1 streaming and real-time-style behavior.
- SPEC-003 proposes the M1 filter slice and preserves M2 resampler requirements;
  its `Review` status blocks filter production work.
- SPEC-004 defines accepted M1 result, report, policy, and CI contracts.
- SPEC-005 defines M2 spatial conformance.
- SPEC-006 defines M2 statistical history and trend analysis.

## Open questions

No SPEC-000-local question blocks implementation. ADR-0004 selects JSON,
ADR-0005 selects generated stimuli, and ADR-0006 defines the initial toolchain
and dependency matrix. The complete M1 demonstration still depends on accepting
SPEC-001 and the M1 filter slice of SPEC-003; see the
[M1 acceptance review](../sdd/M1-acceptance-review.md).

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial system contract | New specification |
| 2026-08-15 | Resolve M1 format, stimulus, toolchain, tier, result, and traceability decisions; accept contract | Compatible clarification |
