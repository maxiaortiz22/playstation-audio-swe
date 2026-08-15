# SPEC-000: System and product contract

- **Status:** Draft
- **Owners:** Repository maintainers
- **Created:** 2026-08-14
- **Last updated:** 2026-08-14
- **Target milestone:** M1 - End-to-end regression demonstration
- **Depends on:** ADR-0001, ADR-0002, ADR-0003

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

A manifest will eventually be serialized as versioned YAML or JSON and SHALL include:

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

A result SHALL include:

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
- **SYS-REP-002:** Every asset-based stimulus SHALL record a cryptographic content digest.
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

Target: suitable for every pull request with no external hardware or network access.

### Extended tier

- SPSC stress and sanitizer runs.
- High-resolution filter/resampler sweeps.
- Statistical repeated measurements.
- SOFA-based spatial conformance.
- Larger diagnostic artifacts.

Target: nightly, release, or manually selected CI.

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
| `T-SYS-001` | `SYS-REP-001`, `SYS-REP-004` | Run seeded stimulus twice | Equal deterministic metrics |
| `T-SYS-002` | `SYS-BND-003` | Pass float64, wrong rank, and non-contiguous views | Documented Python exceptions |
| `T-SYS-003` | `SYS-EXE-003` | Process identical input with two block sizes | Equivalent output within tolerance |
| `T-SYS-004` | `SYS-ANL-001`, `SYS-ANL-002` | Candidate has known delay | Raw delay preserved; aligned residual separate |
| `T-SYS-005` | `SYS-DIAG-001`, `SYS-DIAG-003` | Inject channel swap and dropout | Actionable report and reproduction command |
| `T-SYS-006` | `SYS-TTV-001`, `SYS-TTV-003` | Run labeled positive/negative corpus | Expected detector classifications and explanations |
| `T-SYS-007` | `SYS-EXE-005`, `SYS-ANL-005` | Inject NaN | Structural failure; no misleading similarity pass |

## Dependencies

- SPEC-001 defines comparison semantics.
- SPEC-002 defines streaming and real-time-style behavior.
- SPEC-003 defines filter/resampler conformance.
- SPEC-004 defines result, report, policy, and CI contracts.
- SPEC-005 defines optional spatial conformance.
- SPEC-006 defines statistical history and trend analysis.

## Open questions

- [ ] Choose YAML or JSON as the authoring format for M1 manifests. JSON remains the canonical schema representation either way.
- [ ] Decide whether M1 ships a short generated WAV fixture or generates every stimulus at runtime.
- [ ] Set the supported compiler and Python CI matrix after confirming local toolchain availability.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial system contract | New specification |
