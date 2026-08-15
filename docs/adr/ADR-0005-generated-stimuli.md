# ADR-0005: Generate deterministic M1 stimuli at runtime

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

Detector tests need labeled, reproducible audio whose provenance and fault
parameters are auditable. Committed WAV inputs would exercise container I/O,
but would obscure how the signal was made and create binary golden assets
before WAV decoding is itself part of the M1 product contract.

## Decision

M1 normative input stimuli are generated at runtime from a versioned generator
identifier, parameters, and an explicit seed where stochastic state exists.
The result records those fields plus the SHA-256 digest of the generated
float32 PCM bytes.

Core conformance cases prefer signals with deterministic constructions such as
impulses, constant sequences, channel-identification sequences, and a specified
integer PRBS. Signals that depend on transcendental library implementations are
compared through documented metric tolerances rather than cross-platform PCM
hash equality.

M1 does not commit normative input WAV fixtures. WAV files may be generated as
diagnostic artifacts or temporary I/O test outputs. Any quantization or format
conversion applied for listening is recorded and never replaces the float32
buffer used for analysis.

Calibration data and holdout data use disjoint declared generator seeds and
parameter sets. A detector is not accepted using only the cases that selected
its operating point.

## Consequences

### Positive

- Every labeled fault is reproducible from reviewable parameters.
- The repository avoids unnecessary binary assets and provenance questions.
- Tests can cover boundary cases without maintaining many golden files.

### Costs and risks

- Generator algorithms and PRNG behavior become versioned contracts.
- Runtime generation is not automatically bit-exact across math libraries.
- A future WAV decoder contract will still need small, licensed or generated
  container fixtures.

## Alternatives considered

- **Committed WAV fixtures:** simple playback input, but weak generator
  provenance and poor reviewability for parameter sweeps.
- **Both generated and WAV inputs in M1:** broader coverage, but adds an I/O
  contract unrelated to the first end-to-end validation demonstration.
