# SPEC-001: Aligned audio regression comparator

- **Status:** Draft
- **Owners:** Audio analysis subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-14
- **Target milestone:** M1 - End-to-end regression demonstration
- **Depends on:** SPEC-000, ADR-0003

## Context

Direct sample subtraction is only meaningful when signals share a time origin, channel mapping, gain convention, sample clock, and intended deterministic behavior. A one-sample shift can create a large residual even when waveform shape is unchanged, while unrestricted alignment can erase a genuine latency regression.

The comparator therefore separates measurement into explicit stages and preserves both raw and compensated observations.

## Goals

- Measure latency or offset before any time compensation.
- Align signals robustly within a declared search range.
- Detect polarity, gain, channel, clock-drift, residual, spectral, and localized anomaly changes.
- Produce interpretable results for silence, low-level content, periodic content, unequal lengths, and invalid samples.
- Permit bit-exact checks where determinism is required without imposing them on all audio behavior.

## Non-goals

- Declaring two arbitrary pieces of music perceptually equivalent.
- Automatically deciding which differences are intentional.
- Hiding gain, phase, polarity, or delay changes through implicit normalization.
- Providing a standards-compliant PEAQ/PESQ/POLQA implementation.
- Correcting long-term sample-clock drift in M1; drift is measured and reported.

## Inputs

- Baseline audio buffer and metadata.
- Candidate audio buffer and metadata.
- Channel map.
- Comparison configuration:
  - Sync channel or downmix rule.
  - Maximum positive/negative lag.
  - Active-region selection.
  - Allowed time, gain, polarity, and drift operations.
  - Requested metrics and policies.
  - Numerical floors and minimum overlap.

## Outputs

- Structural validation outcome.
- Per-channel and aggregate raw metrics.
- Alignment estimate and confidence information.
- Compensated overlap and residual metrics where valid.
- Localized anomaly events.
- Policy-ready metrics with explicit units.
- Diagnostic data for plots and residual audio.

## Processing stages

### Stage 0: Structural validation

Validate sample rate, channels, channel labels, dtype, dimensions, finite samples, and sufficient duration. Structural mismatch is not an ordinary residual error.

### Stage 1: Active-region and synchronization signal

The manifest identifies the region and channel/downmix used for synchronization. Optional DC removal or band limiting may be applied to a temporary synchronization copy only and SHALL NOT alter the measurement buffers.

Periodic single tones are permitted only when the manifest supplies a disambiguating search window or synchronization marker.

### Stage 2: Integer delay estimation

Use normalized cross-correlation within the declared lag range. Select the largest absolute normalized correlation and preserve its sign to detect possible polarity inversion.

The result includes:

- Integer lag in frames and seconds.
- Signed normalized peak correlation.
- Search boundaries.
- Peak-to-secondary-peak ratio or equivalent ambiguity indicator.
- Validity status.

The lag sign convention SHALL be stable and documented as:

```text
positive lag: candidate occurs later than baseline
negative lag: candidate occurs earlier than baseline
```

### Stage 3: Optional fractional delay estimation

M1 MAY estimate sub-frame delay by local interpolation around an unambiguous correlation peak. The result is diagnostic unless a dedicated fractional-delay policy opts into it. A later phase-slope or GCC-based estimator may supersede it through a specification amendment.

### Stage 4: Raw latency policy

Evaluate the measured delay before modifying either signal. A failing latency policy remains failed even when alignment produces a small residual.

### Stage 5: Declared compensation and overlap

Apply only declared transformations. M1 supports integer time alignment. Gain or polarity compensation is disabled by default and, if enabled, records both the measured transform and pre-compensation metrics.

The overlap is cropped symmetrically according to the lag convention. Samples without a counterpart SHALL NOT be zero-padded into the residual metric.

### Stage 6: Residual and spectral analysis

Compute requested metrics over the valid overlap. Localized detectors operate on both raw and aligned views when their semantics require it.

## Requirements

### Structural validation

- **CMP-STR-001:** The comparator SHALL reject different sample rates unless a manifest explicitly selects an upstream resampling step; the comparator SHALL NOT silently resample.
- **CMP-STR-002:** Channel-count or channel-label mismatch SHALL produce a structural result before sample comparison.
- **CMP-STR-003:** NaN or infinity SHALL produce a localized structural failure containing channel and first frame index.
- **CMP-STR-004:** Empty input or overlap shorter than the configured minimum SHALL produce an invalid comparison, never a pass.
- **CMP-STR-005:** Input buffers SHALL remain unchanged by analysis.

### Alignment

- **CMP-ALIGN-001:** The system SHALL use cross-correlation between baseline and candidate, not autocorrelation, to estimate relative delay.
- **CMP-ALIGN-002:** The lag search SHALL be bounded by manifest configuration.
- **CMP-ALIGN-003:** Delay SHALL be reported in signed frames and milliseconds using the documented convention.
- **CMP-ALIGN-004:** The raw delay policy SHALL be evaluated before alignment.
- **CMP-ALIGN-005:** Correlation peak sign SHALL be preserved so polarity inversion can be diagnosed.
- **CMP-ALIGN-006:** An ambiguous peak SHALL invalidate automatic alignment unless the manifest provides an accepted disambiguation rule.
- **CMP-ALIGN-007:** DC removal or filtering used for synchronization SHALL affect only the synchronization copy.
- **CMP-ALIGN-008:** Sub-frame estimates SHALL be labeled with their estimator and validity; integer correlation SHALL NOT be described as sub-sample precision.

### Compensation

- **CMP-COMP-001:** Time, gain, polarity, phase, or drift compensation SHALL be disabled unless individually enabled by the manifest.
- **CMP-COMP-002:** Every applied compensation SHALL be recorded with measured value, method, and affected metric set.
- **CMP-COMP-003:** Enabling compensation SHALL NOT discard the corresponding raw metric or policy outcome.
- **CMP-COMP-004:** M1 SHALL NOT time-warp a signal to remove measured clock drift.

### Core metrics

- **CMP-MET-001:** The comparator SHALL compute per-channel peak absolute error over the valid aligned overlap.
- **CMP-MET-002:** The comparator SHALL compute per-channel residual RMS in linear units and dBFS with an explicit numerical floor.
- **CMP-MET-003:** The comparator SHALL compute error-to-signal ratio or residual-relative-to-reference energy so results are not solely dependent on program level.
- **CMP-MET-004:** Near-silent reference regions SHALL use an absolute error policy rather than an unstable relative error.
- **CMP-MET-005:** A bit-exact mode SHALL report first differing frame/channel and differing sample count.
- **CMP-MET-006:** Floating-point numerical mode SHALL support absolute and relative tolerance, including explicit near-zero handling.
- **CMP-MET-007:** Spectral comparison SHALL declare FFT/window method, scaling, frequency range, aggregation bands, and dB floor.
- **CMP-MET-008:** Aggregate metrics SHALL NOT hide a failing channel; per-channel results remain available.

### Channel behavior

- **CMP-CH-001:** The analyzer SHALL support a channel-identification stimulus with independent content per channel.
- **CMP-CH-002:** Channel swap detection SHALL report observed-to-expected mapping and confidence.
- **CMP-CH-003:** Crosstalk SHALL be measured relative to the driven channel using a configured floor and frequency region.
- **CMP-CH-004:** Polarity inversion SHALL be distinct from a generic high residual.

### Localized anomaly detection

- **CMP-EVT-001:** Click detection SHALL combine a time-local discontinuity feature with stimulus-aware context or aligned residual evidence.
- **CMP-EVT-002:** Dropout detection SHALL report start, end, duration, channel set, and whether the region contains exact zeros or near-silence.
- **CMP-EVT-003:** Repeated-block detection SHALL identify block length and repetition interval when confidence is sufficient.
- **CMP-EVT-004:** Clipping detection SHALL distinguish integer rail saturation from float samples outside nominal range.
- **CMP-EVT-005:** DC offset SHALL be reported per channel over a declared region.
- **CMP-EVT-006:** Event detectors SHALL merge adjacent detections according to a configured gap and preserve the highest-severity evidence.

### Clock drift

- **CMP-DRIFT-001:** Drift estimation SHALL use lag measurements across at least two separated analysis windows.
- **CMP-DRIFT-002:** Drift SHALL be reported as lag slope and estimated parts per million with validity bounds.
- **CMP-DRIFT-003:** M1 drift measurement SHALL be diagnostic and SHALL NOT silently stretch the candidate for residual comparison.

### Diagnostics

- **CMP-DIAG-001:** A failed metric SHALL report baseline value, candidate value where applicable, threshold, units, and comparison operator.
- **CMP-DIAG-002:** Alignment diagnostics SHALL include correlation peak, lag, ambiguity indicator, and search range.
- **CMP-DIAG-003:** Residual audio SHALL be generated only from a valid overlap and SHALL record any applied compensation.
- **CMP-DIAG-004:** Time-local failures SHALL provide context before and after the event where available.
- **CMP-DIAG-005:** Plots SHALL label raw versus aligned or compensated data unambiguously.

## Initial metric set

| Metric | Unit | Default interpretation |
|---|---|---|
| `latency_frames` | frames | Signed candidate delay |
| `latency_ms` | ms | Signed candidate delay |
| `correlation_peak` | unitless | Signed alignment confidence |
| `peak_error` | linear FS | Worst aligned sample error |
| `residual_rms_dbfs` | dBFS | Absolute residual energy |
| `error_to_signal_db` | dB | Residual relative to baseline energy |
| `spectral_distance_db` | dB | Configured band-aggregated difference |
| `gain_delta_db` | dB | Candidate relative level |
| `dc_offset` | linear FS | Mean per channel |
| `drift_ppm` | ppm | Relative sample-clock estimate |
| `event_count.<type>` | count | Localized anomaly count |

Threshold values are deliberately not universal defaults. Test manifests own their numeric policy and rationale.

## Acceptance criteria

1. A delayed but otherwise identical broadband signal reports the correct raw delay and near-zero aligned residual.
2. A delay outside policy fails even when aligned residual passes.
3. An inverted-polarity candidate selects the correct lag and reports polarity inversion.
4. A periodic tone without a constrained search window is rejected as ambiguous when multiple peaks are equivalent.
5. A gain change is measured but not normalized away by default.
6. Synthetic click, dropout, repeated block, clipping, NaN, channel swap, and drift faults produce distinct diagnoses.
7. Clean intentional transients and silence fixtures do not trigger their paired negative detectors under the approved policies.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-CMP-001` | `CMP-ALIGN-001..005` | Broadband candidate delayed 37 frames | `+37` frames and high signed correlation |
| `T-CMP-002` | `CMP-ALIGN-005`, `CMP-CH-004` | Delayed and polarity-inverted candidate | Correct lag plus polarity diagnosis |
| `T-CMP-003` | `CMP-ALIGN-006` | Unconstrained 440 Hz tone | Ambiguous alignment result |
| `T-CMP-004` | `CMP-COMP-001..003` | Candidate differs by +1 dB | Raw gain delta; no implicit normalization |
| `T-CMP-005` | `CMP-MET-002..004` | Near-silent baseline with small absolute error | Finite absolute metric; relative metric invalid/not used |
| `T-CMP-006` | `CMP-MET-005` | One exact sample differs | First location and count reported |
| `T-CMP-007` | `CMP-CH-001..003` | Distinct tones with swapped stereo channels | Mapping failure and leakage metrics |
| `T-CMP-008` | `CMP-EVT-001` | Inject click into steady sine and compare legitimate onset | Fault detected; intentional onset not flagged |
| `T-CMP-009` | `CMP-EVT-002` | Inject 20 ms zero and near-zero dropouts | Correct intervals and classifications |
| `T-CMP-010` | `CMP-EVT-003` | Repeat one 128-frame block | Repetition interval reported |
| `T-CMP-011` | `CMP-EVT-004`, `CMP-STR-003` | Inject clipping and NaN separately | Distinct structural/event failures |
| `T-CMP-012` | `CMP-DRIFT-001..003` | Resample candidate with known ppm error | Drift estimate within specified estimator tolerance |
| `T-CMP-013` | `CMP-DIAG-001..005` | Multi-fault run | Raw/aligned evidence and localized context |

## Dependencies

- NumPy/SciPy-equivalent offline analysis capability.
- SPEC-004 result and report schemas.
- Deterministic fault generators from the native or Python test-vector layer.

## Open questions

- [ ] Select the M1 fractional-delay estimator or explicitly defer fractional gating to M2.
- [ ] Select spectral aggregation: fixed linear bands, octave/third-octave bands, or configurable arbitrary bands.
- [ ] Define the minimum correlation ambiguity ratio through empirical fixtures rather than a universal guess.
- [ ] Decide whether drift estimation belongs in the fast or extended tier for M1.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial comparator contract | New specification |
