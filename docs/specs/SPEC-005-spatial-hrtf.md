# SPEC-005: Spatial and HRTF conformance

- **Status:** Draft
- **Owners:** Spatial analysis subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-14
- **Target milestone:** M2 - Spatial conformance demonstration
- **Depends on:** SPEC-000, SPEC-001, SPEC-004

## Context

Binaural rendering encodes source direction through interaural timing, interaural level, and direction-dependent spectral filtering. A strict sample-level comparison may be appropriate for an unchanged deterministic renderer, but feature-level conformance is also needed when implementation changes legitimately alter low-level samples.

Universal physiological thresholds are inappropriate because results depend on listener anatomy, dataset, coordinate convention, sample rate, estimator, frequency region, and interpolation method.

## Goals

- Load a small, licensed, versioned HRIR dataset represented in SOFA.
- Render deterministic sources at known azimuth/elevation positions.
- Measure ITD, frequency-dependent ILD, spectral coloration, symmetry, and movement continuity.
- Compare against dataset-derived references and declared invariants.
- Diagnose swapped ears, wrong coordinates, incorrect interpolation, spectral corruption, and spatial discontinuities.

## Non-goals

- Claiming subjective localization quality from objective metrics alone.
- Defining one universal ITD/ILD range for all humans and HRTFs.
- Reconstructing proprietary spatial-renderer behavior.
- Implementing head tracking or room acoustics in M2 unless separately specified.
- Shipping an HRTF dataset without verified redistribution terms.

## Data and coordinate contract

- Input data uses a supported SOFA convention, initially `SimpleFreeFieldHRIR` or an explicitly documented equivalent.
- Dataset file, license, source URL, subject/listener identifier, SOFA convention/version, sample rate, coordinate units, and digest are recorded.
- Internal canonical source coordinates are azimuth in degrees, elevation in degrees, and distance in meters.
- Zero direction, positive azimuth direction, ear order, listener view/up vectors, and handedness are declared before conversion.
- Coordinate conversion is tested independently from rendering.

## Rendering model

M2 begins with impulse or broadband mono input convolved with left/right HRIRs. Optional source movement uses a sequence of directions and a declared interpolation method.

The renderer output is stereo float32. Convolution latency and HRIR time-of-arrival are represented separately where the implementation exposes that distinction.

## Feature definitions

### Interaural time difference (ITD)

ITD is estimated using a declared method and frequency region. Candidate methods include onset/time-of-arrival difference, band-limited cross-correlation, and phase-based estimation. Every result records estimator, band, sign convention, confidence, and reference.

### Interaural level difference (ILD)

ILD is computed in declared frequency bands:

```text
ILD_band_dB = level_left_band_dB - level_right_band_dB
```

Broadband ILD may be reported but SHALL NOT replace band-wise ILD where head-shadow behavior is under test.

### Spectral coloration

Per-ear HRTF/HRIR magnitude is compared against the selected reference using declared bands, smoothing, floor, and optional level normalization. Normalization is disabled unless the test intends to ignore overall level.

### Trajectory continuity

For adjacent rendered directions, metrics include output jump, band-energy derivative, ITD/ILD step, and residual after expected interpolation. Intended rapid source motion and renderer transition semantics are encoded in the manifest.

## Requirements

### Dataset integrity

- **SPA-DATA-001:** Every SOFA asset SHALL have verified source, license/redistribution status, convention/version, and cryptographic digest.
- **SPA-DATA-002:** Unsupported SOFA convention, receiver count, sample rate, or malformed coordinate metadata SHALL fail explicitly.
- **SPA-DATA-003:** Ear/receiver order SHALL be derived from validated metadata or an explicit dataset adapter, never assumed silently.
- **SPA-DATA-004:** A minimal test subset SHALL preserve the metadata needed to interpret every retained HRIR.

### Coordinate behavior

- **SPA-COORD-001:** Canonical azimuth/elevation/distance conversion SHALL be independently testable.
- **SPA-COORD-002:** The report SHALL state original and canonical coordinates for every tested direction.
- **SPA-COORD-003:** Mirrored-direction tests SHALL use dataset-derived corresponding positions within an explicit angular tolerance.
- **SPA-COORD-004:** Out-of-grid positions SHALL follow a declared nearest, interpolation, or rejection policy.

### Rendering

- **SPA-REND-001:** A deterministic impulse render SHALL reproduce the selected HRIR according to the convolution/latency convention.
- **SPA-REND-002:** Channel order SHALL remain left/right according to the dataset adapter.
- **SPA-REND-003:** Renderer reset SHALL produce deterministic output.
- **SPA-REND-004:** Approved block partitions SHALL produce equivalent concatenated binaural output.
- **SPA-REND-005:** Interpolation method and neighbor directions SHALL be recorded for off-grid renders.

### ITD

- **SPA-ITD-001:** ITD SHALL record sign convention, estimator, frequency range, confidence, and units.
- **SPA-ITD-002:** ITD policy SHALL compare against the selected dataset/reference result, not a universal human-head constant.
- **SPA-ITD-003:** Center and mirrored-direction invariants SHALL be derived from the dataset and test configuration.
- **SPA-ITD-004:** Ambiguous or low-confidence ITD estimates SHALL be invalid rather than forced to a numeric pass.
- **SPA-ITD-005:** Renderer algorithmic latency SHALL be reported separately from relative left/right timing.

### ILD and spectral behavior

- **SPA-ILD-001:** ILD SHALL be available per configured frequency band.
- **SPA-ILD-002:** Broadband level SHALL NOT hide a failing band.
- **SPA-ILD-003:** Any level normalization SHALL be opt-in and raw per-ear levels remain available.
- **SPA-SPEC-001:** Per-ear spectral comparison SHALL declare window/FFT, smoothing/bands, normalization, and floor.
- **SPA-SPEC-002:** Spectral notch or coloration diagnostics SHALL report frequency regions rather than only one aggregate score.
- **SPA-SPEC-003:** Ear swap SHALL produce a targeted channel/coordinate diagnosis.

### Movement continuity

- **SPA-MOV-001:** Trajectory sample positions, update rate, interpolation rule, and source signal SHALL be deterministic.
- **SPA-MOV-002:** Adjacent-direction ITD, ILD, level, and spectral changes SHALL be reported as trajectories.
- **SPA-MOV-003:** Abrupt discontinuities exceeding manifest policy SHALL include direction/time and local audio context.
- **SPA-MOV-004:** Continuity policies SHALL distinguish a renderer transition defect from an intentionally discontinuous source path.

### Interpretation

- **SPA-INT-001:** Objective spatial metrics SHALL be described as conformance evidence, not proof of perceived localization quality.
- **SPA-INT-002:** Selected listening checks MAY complement automated results but SHALL NOT be required for deterministic CI pass/fail in M2.
- **SPA-INT-003:** Reports SHALL avoid claims about proprietary platform behavior.

## Initial spatial test grid

Subject to dataset availability:

- Center: azimuth 0 degrees, elevation 0 degrees.
- Horizontal mirrored pairs near +/-30, +/-60, and +/-90 degrees.
- At least one positive and one negative elevation pair.
- One short horizontal trajectory crossing center.

Exact positions use the nearest available matched dataset entries and are recorded in the manifest.

## Fault-injection catalog

- Swap left/right HRIRs.
- Negate azimuth sign.
- Exchange azimuth/elevation.
- Use degrees as radians or vice versa.
- Apply incorrect sample rate.
- Shift one ear by a known delay.
- Apply per-band gain corruption to one ear.
- Use nearest neighbor where interpolation is required.
- Reset convolution state during motion.

## Acceptance criteria

1. Direct impulse rendering reproduces selected HRIRs under the declared latency convention.
2. ITD and ILD results match dataset-derived references within estimator-specific tolerances.
3. Ear swap and azimuth-sign faults receive targeted diagnoses.
4. Band-limited ILD catches a frequency-localized fault that broadband energy can obscure.
5. A smooth trajectory passes continuity policy; injected state reset produces a localized failure.
6. Reported coordinates and ear order are sufficient to reproduce every spatial result.
7. No universal physiological range is used as the sole pass/fail oracle.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-SPA-001` | `SPA-DATA-001..004` | Load valid and malformed SOFA fixtures | Verified metadata or explicit failure |
| `T-SPA-002` | `SPA-COORD-001..004` | Convert canonical/mirrored/out-of-grid directions | Correct and declared mapping |
| `T-SPA-003` | `SPA-REND-001..004` | Impulse render across block sizes | Reference-equivalent binaural output |
| `T-SPA-004` | `SPA-ITD-001..005` | Estimate ITD for center/mirrored pairs | Reference match and complete metadata |
| `T-SPA-005` | `SPA-ILD-001..003`, `SPA-SPEC-001..002` | Inject one-band level fault | Band failure despite acceptable broadband aggregate |
| `T-SPA-006` | `SPA-SPEC-003` | Swap ears | Targeted channel/coordinate diagnosis |
| `T-SPA-007` | `SPA-MOV-001..004` | Smooth path and reset-state fault | Pass then localized discontinuity failure |
| `T-SPA-008` | `SPA-INT-001..003` | Render final report | Correctly scoped interpretation |

## Open questions

- [ ] Select an HRTF/SOFA dataset whose redistribution terms allow a small repository fixture.
- [ ] Select the primary M2 ITD estimator and its frequency bands.
- [ ] Choose fixed bands, third-octave bands, or ERB-like bands for ILD.
- [ ] Decide whether interpolation is implemented natively or exercised through a simple reference renderer first.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial spatial/HRTF contract | New specification |
