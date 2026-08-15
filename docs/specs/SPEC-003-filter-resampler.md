# SPEC-003: Filter and resampler conformance

- **Status:** Review
- **Owners:** DSP conformance subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-15
- **Target milestone:** M1 - Basic filter conformance; M2 - Resampler depth
- **Depends on:** SPEC-000, SPEC-001, SPEC-002, ADR-0005, ADR-0006

## Context

Filter and resampler tests often fail for reasons unrelated to the system under test: spectral leakage, random-noise variance, incorrect FFT scaling, comparing output spectrum without dividing by the input, or applying a slope expectation at a point where the asymptotic approximation is invalid.

This specification defines stimulus/oracle strategies and requires the test manifest to describe a tolerance envelope rather than relying on universal magic numbers.

## Goals

- Validate magnitude, phase, latency, stability, and streaming behavior of filters.
- Validate frequency mapping, passband, stopband, alias/image rejection, level, length, and latency of resamplers.
- Compare against analytical expectations or an approved high-quality offline oracle.
- Exercise multiple sample rates, ratios, block sizes, and signal levels.
- Make windowing and spectral normalization explicit.

## Non-goals

- Designing production filters or a state-of-the-art sample-rate converter in M1.
- Treating output-noise FFT magnitude as a direct transfer function.
- Injecting a discrete-time tone above the input Nyquist frequency.
- Defining one fixed passband/stopband requirement for every component.
- Claiming perceptual transparency from a single spectral metric.

## Milestone applicability

Requirement prefixes are the normative scope boundary:

| Prefix | Earliest implementation milestone | M1 disposition |
|---|---|---|
| `FIL-*` | M1 | Proposed stateful biquad conformance slice; blocked until this specification is accepted |
| `SRC-*` | M2 | Contract preserved, but no general resampler SUT, external oracle, dependency, or conformance claim in M1 |

An offline wrong-ratio signal generator used by SPEC-001 to test drift is not a
resampler SUT and does not satisfy any `SRC-*` requirement. The combined
specification remains in `Review` until `T-FIL-CAL-001` closes the M1 numerical
contract and maintainers either accept the M2 resampler contract/oracle
governance or move that contract to a dedicated specification without changing
its existing requirement IDs.

## Common definitions

- **Transfer function estimate:** ratio of output to input spectra under a valid excitation and numerical floor.
- **Passband ripple:** maximum specified deviation from target gain over the configured passband.
- **Stopband attenuation:** maximum admitted output relative to the declared reference in the configured stopband.
- **Group delay:** negative derivative of unwrapped phase with angular frequency, or an equivalent documented estimator.
- **Image:** unwanted spectral replica produced during interpolation.
- **Alias:** unwanted folded component caused by insufficient rejection before decimation or nonlinear/sample-rate behavior.
- **Oracle:** analytical model or versioned offline implementation with provenance.

## Stimulus families

### Impulse

Used for impulse response, integer latency, finite response length, channel routing, and direct frequency response of linear time-invariant systems.

### Coherent tones and multitone

Used for gain, frequency mapping, distortion, images, and targeted
passband/stopband points. Frequencies follow `SRC-CFG-002` and are selected to
avoid ambiguous bin leakage or use the window correction required by the
owning measurement contract.

### Sweep

Used for dense magnitude/phase coverage. Logarithmic sweep deconvolution MAY separate nonlinear harmonic responses when its algorithm is specified.

### Noise

Used only with an averaged transfer-function estimator such as Welch/cross-spectral analysis or sufficient ensemble averaging. A single output-noise FFT normalized by its maximum is not a valid conformance oracle.

## Filter requirements

### Initial M1 SUT

The initial SUT is a stateful float32 direct-form-II-transposed low-pass biquad
supporting mono and stereo streams. Coefficients are explicit, normalized to
`a0 = 1`, and stored with the manifest. The independent oracle evaluates the
same declared transfer-function coefficients in float64 and records its method
version. For each channel and frame, the sign/state convention is:

```text
y[n]  = b0 * x[n] + s1
s1'   = b1 * x[n] - a1 * y[n] + s2
s2'   = b2 * x[n] - a2 * y[n]
H(z)  = (b0 + b1*z^-1 + b2*z^-2) / (1 + a1*z^-1 + a2*z^-2)
```

Reset sets both state values to positive zero. A configuration is eligible only
when coefficients are finite, `a0` has already been normalized to one, both
poles lie strictly inside the unit circle, and a declared analytical bound for
the configured input/duration fits the float32 domain. Other configurations
fail before streaming. Tests cover reset, state carryover, two block
partitions, partial final blocks, and labeled wrong-sign/coefficient,
reset-per-block, and channel-stride faults.

M1 does not prescribe one fixed FFT point count. For impulse measurement, the
manifest selects the impulse length from the reviewed analytical tail-bound
method and its numerical floor, then uses an FFT length large enough to avoid
circular truncation on the reported grid. All valid rFFT bins are evaluated
against the declared passband/transition/stopband regions. A sparse
coherent-tone set is an independent boundary check, not the source of a
universal frequency-density number. `T-FIL-CAL-001` must approve the bound
method and the float32-versus-float64 envelopes before the M1 filter slice can
be accepted.

### Configuration and oracle

- **FIL-CFG-001:** Every filter test SHALL declare sample rate, channels, topology or black-box identity, coefficients/parameters, expected response, and reset state.
- **FIL-CFG-002:** Expected magnitude and phase SHALL come from an analytical model or versioned oracle with provenance.
- **FIL-CFG-003:** Passband, transition band, stopband, and excluded singular/undefined regions SHALL be explicit.
- **FIL-CFG-004:** Tolerances SHALL be defined as an envelope or region-specific policy, not inferred solely from nominal order.

### Response measurement

- **FIL-MET-001:** Impulse-response FFT measurement SHALL use sufficient FFT length to prevent circular truncation from corrupting the configured frequency grid.
- **FIL-MET-002:** If a window is applied, the report SHALL record window, coherent-gain correction, and scaling.
- **FIL-MET-003:** Noise-based measurement SHALL estimate `H(f)` from input/output information and SHALL NOT treat output spectrum alone as the filter response.
- **FIL-MET-004:** Magnitude error SHALL be evaluated only where oracle magnitude and numerical floor make the comparison valid.
- **FIL-MET-005:** Phase and group-delay evaluation SHALL unwrap phase consistently and exclude bins whose magnitude is below the configured reliability floor.
- **FIL-MET-006:** The report SHALL provide worst-case error and its frequency, plus region aggregates.

### Streaming and numerical behavior

- **FIL-STR-001:** Reset output SHALL be deterministic for the same state and input.
- **FIL-STR-002:** Approved block partitions SHALL produce equivalent concatenated output.
- **FIL-STR-003:** Silence input SHALL produce the behavior specified by the component: exact silence, denormal-safe silence, or declared noise/dither.
- **FIL-STR-004:** Long bounded input SHALL not produce NaN, infinity, or unbounded growth for a filter declared stable.
- **FIL-STR-005:** Extreme but valid coefficients/parameters SHALL either process within contract or fail configuration explicitly.
- **FIL-STR-006:** State reset and state carryover between streams SHALL be independently testable.

### Filter acceptance metrics

- Passband magnitude error.
- Stopband maximum and integrated energy.
- Transition-band diagnostics without an implied pass unless policy defines it.
- Phase/group-delay error where required.
- Impulse latency and response-tail behavior.
- Stability/non-finite event count.
- Chunking-invariance error.

## Resampler requirements

### Configuration

- **SRC-CFG-001:** Every resampler test SHALL declare input rate, output rate, rational or effective ratio, channel count, quality mode, expected latency convention, and length convention.
- **SRC-CFG-002:** Test tones SHALL lie below input Nyquist; expected mapped content SHALL be evaluated against output Nyquist and the configured transition policy.
- **SRC-CFG-003:** The oracle SHALL be an approved versioned offline resampler or an analytical expectation suitable for the metric.
- **SRC-CFG-004:** Passband, transition band, and rejection regions SHALL be defined in physical Hz and, where helpful, normalized frequency.

### Length and time

- **SRC-TIME-001:** Output length SHALL follow the documented rounding/latency convention for the requested ratio.
- **SRC-TIME-002:** Duration error SHALL be reported independently from leading/trailing filter latency.
- **SRC-TIME-003:** Impulse or sync-sequence analysis SHALL measure declared algorithmic delay before alignment.
- **SRC-TIME-004:** Streaming across blocks SHALL preserve ratio state without dropped or duplicated frames.
- **SRC-TIME-005:** Flush behavior SHALL explicitly return or discard filter tail according to configuration.

### Spectral behavior

- **SRC-MET-001:** Passband tones SHALL map to their expected physical frequencies within estimator tolerance.
- **SRC-MET-002:** Passband level error and ripple SHALL be evaluated against the oracle across the configured band.
- **SRC-MET-003:** Downsampling tests SHALL place controlled energy inside and outside the output passband as represented validly at the input rate, then measure unwanted folded energy.
- **SRC-MET-004:** Upsampling tests SHALL measure spectral images in configured rejection regions.
- **SRC-MET-005:** Sweep/multitone tests SHALL avoid attributing stimulus/window artifacts to the resampler.
- **SRC-MET-006:** Channel-independent input SHALL remain independent within crosstalk tolerance.
- **SRC-MET-007:** DC and near-Nyquist edge cases SHALL have explicit expected behavior.

### Numerical and streaming behavior

- **SRC-STR-001:** Output SHALL contain no NaN or infinity for finite valid input.
- **SRC-STR-002:** Approved block partitions SHALL produce equivalent output after accounting for the documented flush convention.
- **SRC-STR-003:** Identical channels SHALL remain equivalent within numerical tolerance.
- **SRC-STR-004:** A round-trip test MAY provide diagnostics but SHALL NOT be the sole oracle because two resampling passes compound behavior.
- **SRC-STR-005:** Drift caused by an intentionally incorrect ratio SHALL be diagnosed distinctly from fixed latency.

## Fault-injection catalog

The conformance suite will include deliberately defective variants:

- Wrong filter coefficient or sign.
- State reset on every block.
- Incorrect channel stride.
- Missing/insufficient anti-alias stage.
- Wrong resampling ratio.
- Off-by-one output-length rounding.
- Lost filter tail.
- Duplicated or skipped frame at a block boundary.
- Precision-reduced accumulator.

Each variant maps to at least one expected detector and report explanation.

## Acceptance criteria

### M1 filter slice

1. The selected DF2T low-pass biquad matches its analytical response inside a manifest-defined, calibration-backed envelope.
2. A filter implementation that resets state at block boundaries fails chunking invariance and identifies boundary locations.
3. A wrong coefficient produces a frequency-localized magnitude failure with worst-frequency evidence.
4. Every filter response report states FFT/window/oracle configuration.

### M2 resampler slice

1. A correct resampler preserves expected tone frequency, duration convention, and passband level.
2. Missing anti-alias filtering produces measurable folded energy and a targeted diagnosis.
3. Ratio and output-length faults are distinguished from fixed latency.
4. Every resampler response report states FFT/window/oracle configuration.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-FIL-CAL-001` | `FIL-CFG-002`, `FIL-CFG-004`, `FIL-MET-001`, `FIL-MET-004`, `FIL-MET-005`, `FIL-STR-002`, `FIL-STR-004`, `FIL-STR-005` | Calibrate tail bound and numerical envelopes across toolchains/coefficients, then evaluate disjoint holdout cases | Reviewed bound method and manifest envelopes without tuning leakage |
| `T-FIL-001` | `FIL-CFG-001`, `FIL-CFG-002`, `FIL-CFG-003`, `FIL-CFG-004`, `FIL-MET-001`, `FIL-MET-002`, `FIL-MET-003`, `FIL-MET-004`, `FIL-MET-005`, `FIL-MET-006` | Analytical low-pass response with tail-bound grid and region envelopes | Envelope pass and complete worst-frequency evidence |
| `T-FIL-002` | `FIL-MET-003` | White noise through known filter | Averaged input/output transfer estimate |
| `T-FIL-003` | `FIL-STR-001`, `FIL-STR-002`, `FIL-STR-006` | Stateful filter across block sizes, reset, and state carryover | Equivalent stream and deterministic independent reset behavior |
| `T-FIL-004` | `FIL-STR-004` | Long stability stress | Finite bounded output |
| `T-FIL-005` | `FIL-STR-002` | Inject reset-per-block bug | Boundary-localized failure |
| `T-FIL-006` | `FIL-STR-003`, `FIL-STR-005` | Silence/denormal cases and invalid versus extreme-valid coefficients | Declared silence behavior or explicit configuration rejection |
| `T-SRC-001` | `SRC-CFG-001`, `SRC-CFG-002`, `SRC-CFG-003`, `SRC-CFG-004`, `SRC-TIME-001`, `SRC-TIME-002`, `SRC-TIME-003` | M2 48 kHz -> 44.1 kHz impulse/tone | Correct length, latency, and frequency |
| `T-SRC-002` | `SRC-MET-003` | Downsample with out-of-output-band input energy | Folded energy below policy |
| `T-SRC-003` | `SRC-MET-004` | Upsample controlled multitone | Images below policy |
| `T-SRC-004` | `SRC-STR-002`, `SRC-TIME-004`, `SRC-TIME-005` | Partition stream and flush | Equivalent output and tail convention |
| `T-SRC-005` | `SRC-STR-005` | Inject incorrect ratio | Drift/ratio diagnosis, not fixed-delay-only |
| `T-SRC-006` | `SRC-MET-006` | Independent stereo tones | No swap or excess crosstalk |
| `T-SRC-007` | `SRC-MET-001`, `SRC-MET-002`, `SRC-MET-005`, `SRC-MET-007` | M2 coherent passband, artifact-resistant sweep/multitone, DC, and near-Nyquist cases | Correct mapped frequency/level and explicit edge validity |
| `T-SRC-008` | `SRC-STR-001`, `SRC-STR-003`, `SRC-STR-004` | M2 finite input, identical channels, and diagnostic round trip | Finite/equivalent channels; round trip never used as sole oracle |

## Open questions

- [x] Use a stateful float32 DF2T low-pass biquad with a float64 analytical oracle for the proposed M1 filter slice.
- [x] Derive the M1 FFT grid from an analytical response-tail bound and declared numerical floor instead of a universal point count.
- [x] Defer THD+N to a future nonlinear/audio-quality specification.
- [ ] Execute `T-FIL-CAL-001` across supported compilers, representative pole radii/coefficient sets, block partitions, and disjoint holdout cases; approve the analytical tail-bound method plus float32-versus-float64 magnitude, phase, and chunking envelopes.
- [ ] For M2, select and approve the general resampler oracle, version, license, ratio/flush conventions, and calibration corpus before any `SRC-*` implementation.
- [ ] Decide whether to accept the combined M1/M2 contract or move `SRC-*` unchanged to a dedicated specification.

The unchecked filter calibration and M2 contract-governance items keep the
combined specification in `Review`. They do not add resampler work to M1 and
do not supply universal numerical tolerances.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial filter/resampler contract | New specification |
| 2026-08-15 | Select the M1 biquad, derive frequency-grid rules, defer resampler/THD+N scope, and complete planned traceability | Compatible clarification |
