# SPEC-003: Filter and resampler conformance

- **Status:** Draft
- **Owners:** DSP conformance subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-14
- **Target milestone:** M1 - Basic filter conformance; M2 - Resampler depth
- **Depends on:** SPEC-000, SPEC-001, SPEC-002

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

Used for gain, frequency mapping, distortion, images, and targeted passband/stopband points. Frequencies SHALL be below input Nyquist and selected to avoid ambiguous bin leakage or use a documented window correction.

### Sweep

Used for dense magnitude/phase coverage. Logarithmic sweep deconvolution MAY separate nonlinear harmonic responses when its algorithm is specified.

### Noise

Used only with an averaged transfer-function estimator such as Welch/cross-spectral analysis or sufficient ensemble averaging. A single output-noise FFT normalized by its maximum is not a valid conformance oracle.

## Filter requirements

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

1. A known biquad or FIR matches its analytical response inside a manifest-defined envelope.
2. A filter implementation that resets state at block boundaries fails chunking invariance and identifies boundary locations.
3. A wrong coefficient produces a frequency-localized magnitude failure with worst-frequency evidence.
4. A correct resampler preserves expected tone frequency, duration convention, and passband level.
5. Missing anti-alias filtering produces measurable folded energy and a targeted diagnosis.
6. Ratio and output-length faults are distinguished from fixed latency.
7. All response reports state FFT/window/oracle configuration.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-FIL-001` | `FIL-CFG-001..004`, `FIL-MET-001..006` | Analytical low-pass response | Envelope pass and complete evidence |
| `T-FIL-002` | `FIL-MET-003` | White noise through known filter | Averaged input/output transfer estimate |
| `T-FIL-003` | `FIL-STR-002`, `FIL-STR-006` | Stateful filter across block sizes and reset | Equivalent stream; reset deterministic |
| `T-FIL-004` | `FIL-STR-004` | Long stability stress | Finite bounded output |
| `T-FIL-005` | `FIL-STR-002` | Inject reset-per-block bug | Boundary-localized failure |
| `T-SRC-001` | `SRC-CFG-001..004`, `SRC-TIME-001..003` | 48 kHz -> 44.1 kHz impulse/tone | Correct length, latency, and frequency |
| `T-SRC-002` | `SRC-MET-003` | Downsample with out-of-output-band input energy | Folded energy below policy |
| `T-SRC-003` | `SRC-MET-004` | Upsample controlled multitone | Images below policy |
| `T-SRC-004` | `SRC-STR-002`, `SRC-TIME-004..005` | Partition stream and flush | Equivalent output and tail convention |
| `T-SRC-005` | `SRC-STR-005` | Inject incorrect ratio | Drift/ratio diagnosis, not fixed-delay-only |
| `T-SRC-006` | `SRC-MET-006` | Independent stereo tones | No swap or excess crosstalk |

## Open questions

- [ ] Choose the initial filter SUT: biquad low-pass, FIR, or both.
- [ ] Choose the high-quality resampler oracle and record its license/version.
- [ ] Define M1 frequency-grid density and extended-tier sweep density.
- [ ] Decide whether THD+N belongs in this specification or a future nonlinear/audio-quality specification.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial filter/resampler contract | New specification |
