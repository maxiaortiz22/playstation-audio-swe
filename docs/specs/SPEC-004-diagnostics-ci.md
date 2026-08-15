# SPEC-004: Diagnostics, policy, and CI

- **Status:** Draft
- **Owners:** Developer experience and automation subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-14
- **Target milestone:** M1 - End-to-end regression demonstration
- **Depends on:** SPEC-000, SPEC-001, ADR-0003

## Context

The product of a validation system is engineering confidence. A flaky gate, unexplained threshold, missing artifact, or silently updated baseline erodes that confidence even when the underlying metric is mathematically sound.

This specification defines policy evaluation, result serialization, human-readable reports, process exit behavior, artifact handling, and CI tiers.

## Goals

- Separate raw measurement from policy evaluation.
- Represent informational, warning, failure, and invalid outcomes explicitly.
- Give every failure enough context to reproduce and triage it.
- Use the same manifests and policy locally and in CI.
- Preserve result schema compatibility through explicit versioning.
- Support fast pull-request feedback and deeper scheduled validation.

## Non-goals

- Implementing a hosted dashboard, database, queue, or artifact service in M1.
- Automatically approving new baselines.
- Retrying until a failed test passes.
- Hiding invalid measurements behind a warning.
- Embedding large binary artifacts directly inside JSON.

## Outcome model

### Metric validity

Each raw metric has one validity state:

- `valid`: numerical value can be evaluated.
- `not_applicable`: metric does not apply by declared design.
- `insufficient_data`: input/overlap/history cannot support it.
- `invalid_input`: structural input problem.
- `analysis_error`: detector failed to produce a trustworthy result.

### Policy status

Each policy evaluation has one status:

- `pass`
- `info`
- `warning`
- `fail`
- `invalid`

`invalid` is distinct from `fail`: it communicates that the required measurement could not be trusted. A mandatory invalid result still causes a failing process outcome.

### Run status precedence

```text
internal_error > invalid mandatory measurement > fail > warning > pass
```

## Policy model

A policy SHALL declare:

- Stable policy ID and related requirement IDs.
- Metric name and expected unit.
- Scope: aggregate, channel, band, event type, or statistic.
- Comparison operator and threshold(s).
- Directionality.
- Severity.
- Mandatory/optional flag.
- Minimum valid observations.
- Baseline reference where used.
- Rationale and owner.
- Any allowed preprocessing or compensation dependency.

Supported M1 policy shapes:

- Upper bound.
- Lower bound.
- Inclusive range.
- Exact categorical match.
- Event count bound.
- Absolute difference from baseline.
- Relative difference from baseline.

Statistical policies are extended by SPEC-006.

## Requirements

### Policy evaluation

- **POL-EVAL-001:** Raw metrics SHALL be immutable inputs to policy evaluation.
- **POL-EVAL-002:** Policies SHALL validate metric name, unit, scope, operator, and threshold type before execution.
- **POL-EVAL-003:** A mandatory metric with invalid or insufficient data SHALL produce `invalid` and fail the run.
- **POL-EVAL-004:** An optional not-applicable metric MAY be omitted from the final gate but SHALL remain visible in results.
- **POL-EVAL-005:** Multiple policies MAY evaluate one metric; each result remains independent and traceable.
- **POL-EVAL-006:** A pass in one metric SHALL NOT override a failure in another.
- **POL-EVAL-007:** Floating-point threshold comparisons SHALL document inclusive/exclusive boundaries and any comparison epsilon.
- **POL-EVAL-008:** Contradictory policies for the same scope SHOULD be detected during manifest validation.
- **POL-EVAL-009:** Policy rationale and owner SHALL be serialized with or resolvable from the result.

### Result schema

- **RPT-SCHEMA-001:** Machine-readable results SHALL use a versioned JSON schema.
- **RPT-SCHEMA-002:** Every run SHALL include run ID, timestamps, test ID, manifest digest, source revision, dirty state, and final status.
- **RPT-SCHEMA-003:** Metrics SHALL store numerical value separately from unit, validity, method/version, and scope.
- **RPT-SCHEMA-004:** Policy evaluations SHALL store expected condition, actual value, status, severity, and requirement IDs.
- **RPT-SCHEMA-005:** Compensations SHALL be represented as named transformations with measured parameters, not free-form prose only.
- **RPT-SCHEMA-006:** Events SHALL store type, channel set, start/end frame, start/end seconds, confidence, and evidence references.
- **RPT-SCHEMA-007:** Artifacts SHALL store relative URI/path, media type, content hash, size, role, and generation status.
- **RPT-SCHEMA-008:** Unknown additive fields SHALL be tolerated within a major schema version; semantic breaking changes require a major version increment.
- **RPT-SCHEMA-009:** JSON SHALL contain no NaN or infinity tokens; invalid numbers use metric validity plus a null value.

### Human-readable HTML report

- **RPT-HTML-001:** The first view SHALL summarize final status, failed policies, test identity, baseline/candidate identity, and reproduction command.
- **RPT-HTML-002:** Every failed policy SHALL show actual value, expected condition, unit, severity, and requirement IDs.
- **RPT-HTML-003:** Raw and compensated metrics SHALL be visually distinguishable.
- **RPT-HTML-004:** Time-domain plots SHALL use seconds and provide frame indices in event details.
- **RPT-HTML-005:** Spectral plots SHALL label frequency scale, magnitude units/reference, window, FFT configuration, and compared channels.
- **RPT-HTML-006:** The report SHALL link to residual or failure-context audio where generated.
- **RPT-HTML-007:** Missing optional artifacts SHALL show a reason rather than a broken link.
- **RPT-HTML-008:** Reports SHALL be self-contained or use only relative packaged assets so CI artifacts can be downloaded and viewed offline.
- **RPT-HTML-009:** Color SHALL NOT be the sole indicator of status.

### Reproduction and provenance

- **RPT-REP-001:** Every report SHALL contain a copy-pastable command using the original manifest.
- **RPT-REP-002:** Source revision, submodule revisions, toolchain, Python version, native build type, platform, CPU architecture, and relevant environment parameters SHALL be recorded.
- **RPT-REP-003:** The manifest and small generated stimulus metadata SHALL be packaged with the report.
- **RPT-REP-004:** Baseline and candidate artifacts SHALL be identified by digest.
- **RPT-REP-005:** Secret values and machine-specific credentials SHALL NOT be serialized.

### Baseline governance

- **POL-BASE-001:** Validation SHALL NOT create or update an approved baseline implicitly.
- **POL-BASE-002:** Baseline changes SHALL use a separate explicit command/workflow and record reviewer rationale.
- **POL-BASE-003:** A baseline SHALL bind to test ID, manifest/schema version, SUT configuration, and relevant environment class.
- **POL-BASE-004:** A missing required baseline SHALL produce an invalid run rather than treating the candidate as its own baseline.
- **POL-BASE-005:** Expected feature changes SHOULD create a new baseline generation while retaining prior provenance.

### CI behavior

- **CI-RUN-001:** Local and CI execution SHALL invoke the same test runner and manifests.
- **CI-RUN-002:** Fast deterministic tests SHALL run on every pull request.
- **CI-RUN-003:** Extended stress/statistical/spatial tests SHALL run on a documented scheduled or manual trigger.
- **CI-RUN-004:** Failure and invalid outcomes SHALL return non-zero process status; warnings SHALL be configurable but default to zero.
- **CI-RUN-005:** CI SHALL publish the JSON result and HTML report when a validation test fails or is invalid.
- **CI-RUN-006:** Native unit tests, Python unit tests, cross-language integration, and sanitizer jobs SHALL have separate visible results.
- **CI-RUN-007:** Sanitizer runs SHALL NOT be used for performance thresholds.
- **CI-RUN-008:** A retry MAY gather confirmation evidence but SHALL NOT replace the first result or automatically convert the original failure to pass.
- **CI-RUN-009:** Network-independent fast tests SHALL use repository-contained or generated deterministic assets.

### Artifact policy

- **RPT-ART-001:** M1 SHALL retain small JSON and HTML results for every CI validation run if platform limits allow.
- **RPT-ART-002:** Failure-context WAV and plots SHALL be retained for failure/invalid runs.
- **RPT-ART-003:** Large raw captures MAY use a size threshold and explicit retention policy.
- **RPT-ART-004:** Artifact truncation or omission SHALL be recorded with reason and original size estimate.
- **RPT-ART-005:** Generated artifacts SHALL be written outside source-controlled directories by default.

## Proposed process exit codes

| Exit code | Meaning |
|---:|---|
| `0` | Pass, info, or permitted warnings only |
| `1` | One or more validation policies failed |
| `2` | Mandatory measurement invalid or input/configuration invalid |
| `3` | Internal runner/reporting error prevented trustworthy completion |

Exact CLI syntax remains subject to the implementation spec, but meanings SHALL remain stable after acceptance.

## Report evidence hierarchy

1. Final status and policy table.
2. Structural/audio-format findings.
3. Raw latency, gain, polarity, channel, and drift measurements.
4. Compensated residual and spectral metrics.
5. Localized event timeline.
6. Waveform/spectrum/spectrogram plots.
7. Audio artifacts.
8. Environment and reproduction details.

This order prevents an attractive plot from obscuring a structural defect.

## Acceptance criteria

1. A multi-fault run produces independent policy failures with correct precedence.
2. An invalid mandatory metric fails with an explanation and never serializes NaN.
3. JSON validates against its schema and HTML links resolve inside the artifact package.
4. The report clearly distinguishes raw delay from aligned residual.
5. Re-running the packaged command with the same environment regenerates equivalent deterministic metrics.
6. Baselines cannot be changed through the normal validation command.
7. CI uploads evidence for failing tests and does not use sanitizer timing for performance gates.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-POL-001` | `POL-EVAL-001..009` | Evaluate mixed pass/warn/fail policies | Independent results and correct precedence |
| `T-RPT-001` | `RPT-SCHEMA-001..009` | Serialize full and invalid results | Schema-valid JSON without non-standard numbers |
| `T-RPT-002` | `RPT-HTML-001..009` | Render multi-fault report | Complete accessible offline report |
| `T-RPT-003` | `RPT-REP-001..005` | Package reproducible run | Safe provenance and working command |
| `T-BASE-001` | `POL-BASE-001..005` | Validate with missing and changed baseline | Invalid/explicit workflow; no silent update |
| `T-CI-001` | `CI-RUN-001..009` | Run fast workflow and forced failure | Correct jobs, exit code, and artifacts |
| `T-ART-001` | `RPT-ART-001..005` | Exceed configured artifact size | Declared omission/truncation, result preserved |

## Open questions

- [ ] Choose the HTML rendering approach and dependency after a minimal prototype compares maintainability and artifact size.
- [ ] Choose YAML or JSON authoring for policies while retaining JSON Schema validation.
- [ ] Define CI artifact retention days after selecting the hosting platform plan.
- [ ] Decide whether warnings should optionally block release-tier workflows in M1 or M2.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial diagnostics/policy/CI contract | New specification |
