# SPEC-001: Aligned audio regression comparator

- **Status:** Review
- **Owners:** Audio analysis subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-15
- **Target milestone:** M1 - End-to-end regression demonstration
- **Depends on:** SPEC-000, ADR-0003, ADR-0004, ADR-0005

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

The manifest identifies the region and channel/downmix used for synchronization.
Optional DC removal or band limiting may be applied only to the temporary
synchronization copy, as required by `CMP-ALIGN-007`; measurement buffers remain
unchanged.

Periodic single tones are permitted only when the manifest supplies a disambiguating search window or synchronization marker.

### Stage 2: Integer delay estimation

Use normalized cross-correlation within the declared reported-lag range. Let
baseline sync signal `b_sync` have length `N_bs` and source-buffer frame origin
`o_b`, and candidate sync signal `c_sync` have length `N_cs` and origin `o_c`.
For local sync lag `q`, valid baseline-sync indices are the half-open interval:

```text
I_q_sync = [max(0, -q), min(N_bs, N_cs - q))
```

and each pair is `b_sync[i]` with `c_sync[i + q]`. The reported full-buffer lag
is:

```text
l = o_c + q - o_b
```

Only local lags whose reported `l` lies inside the manifest search bounds are
eligible. After only the declared synchronization-copy transforms, correlation
is:

```text
rho(q) = sum(b_sync[i] * c_sync[i + q]) /
         sqrt(sum(b_sync[i]^2) * sum(c_sync[i + q]^2)), i in I_q_sync
```

Each lag uses only its valid overlap. A lag is invalid when its overlap is
shorter than `minimum_overlap_frames` or either overlap RMS is at or below the
manifest's `sync_rms_floor` in linear FS. Those parameters include units and rationale;
neither has a universal default.

Select the valid local lag with largest `abs(rho)`, preserving the signed value
to detect possible polarity inversion. Exact score ties use the smallest
absolute reported `l` and then lowest signed `l` only to produce deterministic
diagnostics; an equivalent competing peak still makes automatic alignment
ambiguous.

The result includes:

- Integer lag in frames and seconds.
- Signed normalized peak correlation.
- Search boundaries.
- Peak-to-secondary-peak ratio or equivalent ambiguity indicator.
- Validity status.

The stable lag sign convention required by `CMP-ALIGN-003` is:

```text
positive lag: candidate occurs later than baseline
negative lag: candidate occurs earlier than baseline
```

### Stage 3: Optional fractional delay estimation

M1 reports and gates integer-frame delay only. It does not interpolate the
correlation peak or expose a fractional-delay policy. A fractional-delay fault
may be used to show a non-zero residual, but the result is not labeled as a
sub-frame latency estimate. A later specification amendment may select a local
parabolic, phase-slope, or GCC-based estimator after a calibration/holdout
comparison.

### Stage 4: Raw latency policy

Evaluate the measured delay before modifying either signal. A failing latency policy remains failed even when alignment produces a small residual.

### Stage 5: Declared compensation and overlap

Apply only declared transformations. M1 supports integer time alignment. Gain or polarity compensation is disabled by default and, if enabled, records both the measured transform and pre-compensation metrics.

For selected reported lag `l`, let full measurement buffers `B` and `C` have
lengths `N_B` and `N_C`. Their measurement overlap is recalculated independently
of the synchronization slice:

```text
J_l_measurement = [max(0, -l), min(N_B, N_C - l))
```

Compensated views contain exactly baseline `B[i]` and candidate `C[i + l]` for
`i` in `J_l_measurement`. No additional symmetric crop is applied. Samples
without a counterpart are excluded rather than zero-padded into residual
metrics.

### Stage 6: Residual and spectral analysis

Compute requested metrics over the valid overlap. Localized detectors operate on both raw and aligned views when their semantics require it.

M1 spectral comparison uses manifest-declared, non-overlapping physical-Hz
bands with half-open bounds `[low_hz, high_hz)`, except that the final band may
include Nyquist explicitly. DC/Nyquist inclusion, window, segment length, FFT
length, overlap, one-sided scaling, and a positive linear-power floor are all
declared. A bin belongs to the band containing its center frequency; M1 does not
fractionally split edge bins, and a band containing no bin is invalid.

For each channel and band `k`, integrate the declared one-sided power estimate
in linear units, then compute:

```text
L_baseline_k = 10 * log10(max(P_baseline_k, power_floor))
L_candidate_k = 10 * log10(max(P_candidate_k, power_floor))
band_delta_k = L_candidate_k - L_baseline_k
spectral_distance_db = max_k(abs(band_delta_k))
```

Per-channel `P`, `L`, and `band_delta` remain available. Worst-bin delta and
frequency remain diagnostic evidence, so a band aggregate cannot hide a narrow
failure. M1 does not imply octave or perceptual weighting and never averages dB
values directly.

## Ambiguity calibration contract

The score is `abs(rho(q))`. A local peak is not smaller than either valid
immediate neighbor; a search-boundary peak has one neighbor. The primary
plateau is the contiguous set around the maximum whose score differs by no more
than `plateau_epsilon`. The deterministic representative lag follows the tie
rule above. The ambiguity indicator is the representative primary score divided
by the largest local-peak score outside the plateau expanded by
`secondary_exclusion_radius_frames`; it is positive infinity when no such peak
exists.

`plateau_epsilon`, `maximum_primary_plateau_width_frames`, the exclusion
radius, `minimum_primary_abs_correlation`, minimum accepted ratio,
`sync_rms_floor`, and minimum overlap are mandatory M1 manifest inputs with
units and rationale. A primary plateau wider than the allowed width, a primary
score below its minimum, a ratio below its minimum, or a missing parameter
invalidates automatic alignment.

All values must be finite unless the computed no-secondary-peak ratio is
positive infinity. `plateau_epsilon` is in `[0, 1)`, the primary correlation
minimum is in `(0, 1]`, the peak ratio minimum is at least `1`, the RMS floor is
non-negative linear FS, plateau width and minimum overlap are positive integer
frames, and exclusion radius is a non-negative integer smaller than the lag
search span. Search bounds and sync-region origins are integer frames. Invalid
domains fail manifest validation rather than enter the estimator.

No repository-wide numeric default is accepted. Before SPEC-001 can become
`Accepted`, `T-CMP-CAL-001` must run the deterministic calibration and holdout
protocol in the [M1 acceptance review](../sdd/M1-acceptance-review.md). The
reviewed M1 manifest selects an operating point from false-valid versus
false-ambiguous evidence; holdout families and seeds are disjoint from tuning
data.

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
- **CMP-COMP-005:** The aligned overlap SHALL contain exactly the valid baseline/candidate pairs under the documented lag convention and SHALL NOT zero-pad samples without counterparts into residual metrics.

### Core metrics

- **CMP-MET-001:** The comparator SHALL compute per-channel peak absolute error over the valid aligned overlap.
- **CMP-MET-002:** The comparator SHALL compute per-channel residual RMS in linear units and dBFS with an explicit numerical floor.
- **CMP-MET-003:** The comparator SHALL compute error-to-signal ratio or residual-relative-to-reference energy so results are not solely dependent on program level.
- **CMP-MET-004:** Near-silent reference regions SHALL use an absolute error policy rather than an unstable relative error.
- **CMP-MET-005:** A bit-exact mode SHALL report first differing frame/channel and differing sample count.
- **CMP-MET-006:** Floating-point numerical mode SHALL support absolute and relative tolerance, including explicit near-zero handling.
- **CMP-MET-007:** Spectral comparison SHALL declare FFT/window method, scaling, frequency range, aggregation bands, and dB floor.
- **CMP-MET-008:** Aggregate metrics SHALL NOT hide a failing channel; per-channel results remain available.
- **CMP-MET-009:** Gain delta SHALL be reported per channel in dB using declared RMS regions and numerical floors; gain compensation SHALL NOT be implicit.

### Channel behavior

- **CMP-CH-001:** The analyzer SHALL support a channel-identification stimulus with independent content per channel.
- **CMP-CH-002:** Channel swap detection SHALL report observed-to-expected mapping, scoring method, confidence, and the manifest-declared minimum mapping margin.
- **CMP-CH-003:** Crosstalk SHALL be measured relative to the driven channel using a manifest-declared numerical floor, frequency region, and rationale.
- **CMP-CH-004:** Polarity inversion SHALL be distinct from a generic high residual.

### Localized anomaly detection

- **CMP-EVT-001:** Click detection SHALL combine a time-local discontinuity feature with stimulus-aware context or aligned residual evidence and SHALL declare derivative/context windows, threshold units, and boundary handling in the manifest.
- **CMP-EVT-002:** Dropout detection SHALL report start, end, duration, channel set, and whether the region contains exact zeros or near-silence using manifest-declared active-reference floor, near-silence floor, and minimum duration.
- **CMP-EVT-003:** Repeated-block detection SHALL declare candidate block lengths, comparison tolerance, minimum repeats, and validity/confidence rule before identifying block length and repetition interval.
- **CMP-EVT-004:** Clipping detection SHALL distinguish a plateau at a declared integer-origin quantizer rail when source-format metadata supports that claim from float samples outside nominal range; without such metadata it SHALL use float plateau/out-of-range terminology.
- **CMP-EVT-005:** DC offset SHALL be reported per channel over a manifest-declared region and minimum valid frame count.
- **CMP-EVT-006:** Event detectors SHALL merge adjacent detections according to a configured gap and preserve the highest-severity evidence.

Every detector parameter above is explicit JSON policy input with unit, owner,
and rationale. Initial operating points are derived from disjoint deterministic
calibration and holdout cases under `SYS-TTV-004`; the specification does not
provide shared numerical defaults. These values are test-specific policy data,
not a cross-test product default, so their later per-manifest calibration gates
verification of that detector policy rather than acceptance of this measurement
contract. The automatic alignment operating point is the exception because it
controls whether downstream comparison may proceed and therefore remains the
explicit SPEC-001 acceptance blocker.

### Clock drift

- **CMP-DRIFT-001:** Drift estimation SHALL use lag measurements across at least two separated analysis windows.
- **CMP-DRIFT-002:** Drift SHALL be reported as lag slope and estimated parts per million with validity bounds.
- **CMP-DRIFT-003:** M1 drift measurement SHALL be diagnostic and SHALL NOT silently stretch the candidate for residual comparison.

Fast-tier tests cover estimator sign, fixed-lag zero slope, insufficient data,
and deterministic known-slope algebra. Long-duration sensitivity across window,
duration, level, and injected-ratio cases runs in the extended tier. The
extended calibration selects each manifest's estimator tolerance and validity
bounds; M1 defines no universal ppm gate.

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
| `T-CMP-CAL-001` | `CMP-ALIGN-002`, `CMP-ALIGN-005`, `CMP-ALIGN-006`, `CMP-ALIGN-007` | Calibrate then hold out deterministic broadband, periodic, low-energy, boundary-lag, polarity, level, and noise cases | Reviewed per-manifest operating point; no universal threshold or tuning leakage |
| `T-CMP-001` | `CMP-ALIGN-001`, `CMP-ALIGN-002`, `CMP-ALIGN-003`, `CMP-ALIGN-004`, `CMP-ALIGN-005`, `CMP-ALIGN-007` | Broadband candidates at negative, zero, positive, and search-boundary lags | Correct signed frame/ms result and sync-only preprocessing |
| `T-CMP-002` | `CMP-ALIGN-005`, `CMP-CH-004` | Delayed and polarity-inverted candidate | Correct lag plus polarity diagnosis |
| `T-CMP-003` | `CMP-ALIGN-006` | Unconstrained 440 Hz tone | Ambiguous alignment result |
| `T-CMP-004` | `CMP-COMP-001`, `CMP-COMP-002`, `CMP-COMP-003`, `CMP-MET-009` | Candidate differs by +1 dB | Raw per-channel gain delta; no implicit normalization |
| `T-CMP-005` | `CMP-MET-001`, `CMP-MET-002`, `CMP-MET-003`, `CMP-MET-004`, `CMP-MET-008` | Near-silent and active references with localized channel error | Finite absolute metrics, valid relative metrics only when supported, failing channel retained |
| `T-CMP-006` | `CMP-MET-005`, `CMP-MET-006` | One exact sample differs; then exercise near-zero absolute/relative tolerance boundaries | First location/count and documented tolerance behavior |
| `T-CMP-007` | `CMP-CH-001`, `CMP-CH-002`, `CMP-CH-003` | Distinct tones with swapped stereo channels and controlled leakage | Mapping failure and leakage metrics |
| `T-CMP-008` | `CMP-EVT-001` | Inject click into steady sine and compare legitimate onset | Fault detected; intentional onset not flagged |
| `T-CMP-009` | `CMP-EVT-002` | Inject 20 ms zero and near-zero dropouts | Correct intervals and classifications |
| `T-CMP-010` | `CMP-EVT-003` | Repeat one 128-frame block | Repetition interval reported |
| `T-CMP-011` | `CMP-EVT-004`, `CMP-STR-003` | Inject clipping and NaN separately | Distinct structural/event failures |
| `T-CMP-012` | `CMP-COMP-004`, `CMP-DRIFT-001`, `CMP-DRIFT-002`, `CMP-DRIFT-003` | Fast algebra cases plus extended wrong-ratio sweep | Valid slope/ppm or insufficient data; no time warp |
| `T-CMP-013` | `CMP-DIAG-001`, `CMP-DIAG-002`, `CMP-DIAG-003`, `CMP-DIAG-004`, `CMP-DIAG-005` | Multi-fault run | Raw/aligned evidence and localized context |
| `T-CMP-014` | `CMP-STR-001`, `CMP-STR-002`, `CMP-STR-003`, `CMP-STR-004`, `CMP-STR-005` | Mismatched formats/labels, non-finite sample, empty/short overlap, and input digest before/after | Structural or invalid results; inputs unchanged |
| `T-CMP-015` | `CMP-ALIGN-008`, `CMP-COMP-005` | Fractional fault, non-zero sync-region origins, and unequal full-buffer lengths at positive/negative lag | Integer-only label, correct local-to-reported lag, and exact measurement overlap without padding |
| `T-CMP-016` | `CMP-MET-007`, `CMP-MET-008` | Declared band edges including DC/Nyquist and a narrow spectral fault | Linear-power band aggregation, per-channel evidence, worst frequency retained |
| `T-CMP-017` | `CMP-EVT-005`, `CMP-EVT-006` | Known DC shift and adjacent events around configured merge gap | Per-channel DC and deterministic event merge evidence |

## Dependencies

- NumPy/SciPy-equivalent offline analysis capability.
- SPEC-004 result and report schemas.
- Deterministic fault generators from the native or Python test-vector layer.

## Open questions

- [ ] Execute `T-CMP-CAL-001`, record calibration and disjoint holdout evidence, and obtain owner approval for the M1 manifest's ambiguity operating point.

Fractional gating is deferred to M2, spectral aggregation uses arbitrary
manifest bands, detector configuration is explicit, and drift uses split
fast/extended coverage. These decisions are closed. The ambiguity evidence item
above keeps this specification in `Review`.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial comparator contract | New specification |
| 2026-08-15 | Define integer correlation/overlap, defer fractional gating, select spectral bands and drift tiers, and expose calibration blocker | Compatible clarification |
