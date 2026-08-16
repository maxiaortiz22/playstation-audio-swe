# SPEC-004: Diagnostics, policy, and CI

- **Status:** Accepted
- **Owners:** Developer experience and automation subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-16
- **Target milestone:** M1 - End-to-end regression demonstration
- **Depends on:** SPEC-000, ADR-0003, ADR-0004, ADR-0006

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

### Validation and run status

`validation_status` is derived only from structural validity and policy
evaluation, using this precedence:

```text
invalid mandatory measurement > fail > warning > pass
```

`info` remains visible on individual policy evaluations but does not create a
distinct aggregate: a run containing only `pass` and `info` policies has
`validation_status = pass`.

It becomes immutable when validation finishes. `run_status` uses the same value
for a completed run, or `internal_error` when runner execution or mandatory
JSON/HTML reporting could not complete trustworthily. `completion_status`
records `complete`, `complete_with_optional_artifact_errors`, or `incomplete`.
An operational error may therefore dominate process exit while preserving the
underlying `validation_status` and all completed policy evaluations. A failed
optional plot or audio artifact does not change `run_status`; its per-artifact
status and reason remain visible.

## Policy model

A policy is valid only when it supplies the fields required by `POL-EVAL-010`:

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

Manifest and policy authoring uses strict JSON under ADR-0004. Unknown fields,
duplicate keys, type coercion, NaN, and infinity are rejected before policy
execution.

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
- **POL-EVAL-010:** Every policy SHALL declare a stable policy ID, related requirement IDs, metric name, expected unit, scope, operator and typed threshold, directionality, severity, mandatory flag, minimum valid observations, rationale, owner, baseline reference when used, and every allowed preprocessing or compensation dependency.

### Result schema

Deterministic offline fixture manifests MAY request byte-reproducible result
identity by declaring an explicit RFC 3339 timestamp in the parameters of the
selected versioned SUT. In that mode, `run_id` is derived from the exact
manifest digest, both required timestamps use the declared value, and the
result records `timestamps.basis = manifest_declared_fixture` plus
`timestamps.wall_clock_recorded = false`. Reports SHALL label that value as a
logical fixture timestamp rather than elapsed or wall-clock evidence. This mode
is limited to deterministic fixture/demo execution; a runner SHALL NOT invent a
fixed timestamp or silently replace wall-clock timing for an execution that did
not request it. Equivalent runs in this mode serialize byte-identical JSON when
their manifest, deterministic SUT, source/dependency provenance, and result
schema are unchanged.

- **RPT-SCHEMA-001:** Machine-readable results SHALL use a versioned JSON schema.
- **RPT-SCHEMA-002:** Every run SHALL include run ID, timestamps, test ID, manifest digest, source revision, dirty state, `validation_status`, `run_status`, and `completion_status` as separate fields.
- **RPT-SCHEMA-003:** Metrics SHALL store numerical value separately from unit, validity, method/version, and scope.
- **RPT-SCHEMA-004:** Policy evaluations SHALL store expected condition, actual value, status, severity, and requirement IDs.
- **RPT-SCHEMA-005:** Compensations SHALL be represented as named transformations with measured parameters, not free-form prose only.
- **RPT-SCHEMA-006:** Events SHALL store type, channel set, start/end frame, start/end seconds, confidence, and evidence references.
- **RPT-SCHEMA-007:** Artifacts SHALL store relative URI/path, media type, content hash, size, role, and generation status.
- **RPT-SCHEMA-008:** Unknown additive fields SHALL be tolerated within a major schema version; semantic breaking changes require a major version increment.
- **RPT-SCHEMA-009:** JSON SHALL contain no NaN or infinity tokens; invalid numbers use metric validity plus a null value.

### Human-readable HTML report

M1 HTML is rendered with Jinja2 autoescaping. Matplotlib uses the non-interactive
Agg backend to emit static PNG or SVG evidence under relative packaged paths;
the report uses no CDN, remote font, or required client-side JavaScript. CSS may
be embedded. Cross-platform automation validates semantic content,
accessibility markers, and links rather than relying on pixel-identical plots.

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

- **RPT-REP-001:** Every report SHALL contain a copy-pastable display command and a structured argument vector referencing the byte-identical packaged manifest; platform-specific quoting SHALL NOT change the represented arguments.
- **RPT-REP-002:** Source revision, submodule revisions, toolchain, Python version, native build type, platform, CPU architecture, and allowlisted relevant environment parameters SHALL be recorded.
- **RPT-REP-003:** The manifest and small generated stimulus metadata SHALL be packaged with the report.
- **RPT-REP-004:** Baseline and candidate artifacts SHALL be identified by digest.
- **RPT-REP-005:** Secret values and machine-specific credentials SHALL NOT be serialized.

### Baseline governance

- **POL-BASE-001:** Validation SHALL NOT create or update an approved baseline implicitly.
- **POL-BASE-002:** Baseline changes SHALL use a separate explicit command/workflow and record reviewer rationale.
- **POL-BASE-003:** A baseline SHALL bind to test ID, manifest/schema version, SUT configuration, and relevant environment class.
- **POL-BASE-004:** A missing required baseline SHALL produce an invalid run rather than treating the candidate as its own baseline.
- **POL-BASE-005:** Expected feature changes SHOULD create a new baseline generation while retaining prior provenance.

An approved M1 baseline uses `schemas/v1/baseline.schema.json`. Its descriptor
binds a stable baseline ID and generation number to the test ID, exact
manifest/schema identity, SUT configuration, environment class, generated
stimulus metadata, canonical PCM format/shape/digest, and an approval record.
The approval record has explicit reviewer, rationale, and timestamp fields.

Baseline creation and replacement are separate privileged operations from
stimulus generation and future validation. Creation fails if a descriptor
already exists; replacement fails if it does not. Neither operation accepts a
blank rationale. Replacement increments the generation, retains each prior
PCM object, and appends the prior generation's descriptor digest, PCM digest,
and approval provenance. The normal load/preparation API is read-only and has
no baseline-writing operation.

Loading verifies the strict descriptor, safe relative PCM path, byte count,
shape, and SHA-256 before exposing an immutable little-endian float32 array.
Missing, malformed, truncated, or digest-mismatched input yields a structured
`invalid_input` baseline outcome. That outcome contains no baseline buffer and
must never substitute the candidate. This slice supplies the structured
boundary for `POL-BASE-004`; propagation into the future complete runner and
result/report schemas remains pending evidence.

### CI behavior

- **CI-RUN-001:** Local and CI execution SHALL invoke the same test runner and manifests.
- **CI-RUN-002:** Fast deterministic tests SHALL run on every pull request.
- **CI-RUN-003:** M1 extended SPSC stress, ThreadSanitizer, host timing characterization, and long drift sensitivity SHALL run on a documented scheduled or manual trigger; statistical and spatial suites SHALL be added only when their M2 specifications are accepted and implemented.
- **CI-RUN-004:** Failure and invalid outcomes SHALL return non-zero process status; warnings SHALL return zero in every M1 tier. A blocking condition SHALL use explicit `fail` severity rather than promote all warnings by workflow context.
- **CI-RUN-005:** CI SHALL attempt to publish JSON and HTML for every completed validation run using a step that executes regardless of validation exit status; failure and invalid runs SHALL additionally publish generated context plots and WAV artifacts. An upload failure SHALL fail the CI adapter job and preserve the already-generated JSON, `validation_status`, and `run_status` without rewriting them.
- **CI-RUN-006:** Native unit tests, Python unit tests, cross-language integration, and sanitizer jobs SHALL have separate visible results.
- **CI-RUN-007:** Sanitizer runs SHALL NOT be used for performance thresholds.
- **CI-RUN-008:** A retry MAY gather confirmation evidence but SHALL NOT replace the first result or automatically convert the original failure to pass.
- **CI-RUN-009:** Network-independent fast tests SHALL use repository-contained or generated deterministic assets.
- **CI-RUN-010:** Process exit meanings SHALL remain `0` for pass/info/warning, `1` for policy failure, `2` for invalid mandatory measurement or input/configuration, and `3` for an internal runner/reporting error; later meanings require a breaking-contract revision.

### Artifact policy

- **RPT-ART-001:** M1 CI SHALL invoke JSON/HTML generation and upload for every run regardless of validation exit status; hosting retention and size limits SHALL be explicit validated workflow configuration. Generation failures SHALL follow the dual-status model, while later upload failures SHALL be represented by the CI adapter job/log without mutating the frozen result JSON.
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

Exact CLI syntax remains subject to the implementation specification. The
stable meanings are governed by `CI-RUN-010`.

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
| `T-POL-001` | `POL-EVAL-001`, `POL-EVAL-002`, `POL-EVAL-003`, `POL-EVAL-004`, `POL-EVAL-005`, `POL-EVAL-006`, `POL-EVAL-007`, `POL-EVAL-008`, `POL-EVAL-009`, `POL-EVAL-010` | Evaluate mixed pass/info/warning/fail/invalid, exact boundaries, contradictory policies, and immutable metrics | Validated policy fields, independent results, and correct validation precedence |
| `T-RPT-001` | `RPT-SCHEMA-001`, `RPT-SCHEMA-002`, `RPT-SCHEMA-003`, `RPT-SCHEMA-004`, `RPT-SCHEMA-005`, `RPT-SCHEMA-006`, `RPT-SCHEMA-007`, `RPT-SCHEMA-008`, `RPT-SCHEMA-009` | Serialize full, invalid, additive-field, and non-finite cases | Schema-valid JSON without non-standard numbers |
| `T-RPT-002` | `RPT-HTML-001`, `RPT-HTML-002`, `RPT-HTML-003`, `RPT-HTML-004`, `RPT-HTML-005`, `RPT-HTML-006`, `RPT-HTML-007`, `RPT-HTML-008`, `RPT-HTML-009` | Render multi-fault, missing-artifact, escaped-text, and offline report cases | Complete accessible offline report with resolved relative links |
| `T-RPT-003` | `RPT-REP-001`, `RPT-REP-002`, `RPT-REP-003`, `RPT-REP-004`, `RPT-REP-005` | Package a reproducible run and inject secret-like non-allowlisted environment values | Working structured/display command, safe provenance, no secret serialization |
| `T-BASE-001` | `POL-BASE-001`, `POL-BASE-002`, `POL-BASE-003`, `POL-BASE-004`, `POL-BASE-005` | Validate with missing and intentionally changed baseline | Invalid or explicit workflow; no silent update |
| `T-CI-001` | `CI-RUN-001`, `CI-RUN-002`, `CI-RUN-003`, `CI-RUN-004`, `CI-RUN-005`, `CI-RUN-006`, `CI-RUN-007`, `CI-RUN-008`, `CI-RUN-009`, `CI-RUN-010` | Force pass/warning/fail/invalid/internal outcomes, retry, sanitizer, and artifact steps | Correct visible jobs, stable exit codes, first-result preservation, and always-attempted evidence |
| `T-ART-001` | `RPT-ART-001`, `RPT-ART-002`, `RPT-ART-003`, `RPT-ART-004`, `RPT-ART-005` | Exceed configured artifact size and force optional/mandatory generation failures | Declared omission or artifact error; validation status and partial evidence preserved |

## Open questions

No contract question blocks M1 implementation. ADR-0004 selects JSON, Jinja2
and static Matplotlib assets define HTML, and M1 warnings never block. Artifact
retention days and size limits are deployment values that must be checked
against the actual GitHub plan before the workflow PR; no value is invented by
this specification. A future release process can use explicit `fail` policies
or amend the contract rather than silently promoting warnings.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial diagnostics/policy/CI contract | New specification |
| 2026-08-15 | Resolve JSON, dual-status, HTML, warning, artifact, exit-code, and traceability decisions; accept contract | Compatible clarification |
| 2026-08-16 | Fix the approved-baseline descriptor, explicit create/replace lifecycle, retained provenance, digest verification, and structured invalid-input boundary | Compatible clarification |
| 2026-08-16 | Define explicit manifest-declared logical timestamps and content-addressed run identity for byte-reproducible deterministic fixture results | Compatible clarification |
