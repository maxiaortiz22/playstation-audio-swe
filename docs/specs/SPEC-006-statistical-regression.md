# SPEC-006: Statistical regression detection

- **Status:** Draft
- **Owners:** Performance and trend analysis subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-14
- **Target milestone:** M2 - Trend analysis demonstration
- **Depends on:** SPEC-000, SPEC-004, ADR-0003

## Context

A static upper bound can miss gradual degradation, while a naive z-score can produce misleading results when the baseline is small, non-stationary, mixed across environments, contaminated by prior regressions, or has near-zero variance.

Performance and noisy hardware/runtime metrics require repeated measurements, explicit environment stratification, robust descriptive statistics, and separation between absolute requirements and relative change detection.

## Goals

- Preserve simple z-score analysis as an explainable diagnostic.
- Add robust location/scale estimates for outlier resistance.
- Detect small sustained drift with EWMA or CUSUM-style monitoring.
- Combine absolute guardrails with relative and trend policies.
- Make statistical assumptions and minimum evidence explicit.
- Demonstrate correct behavior using synthetic histories with known shifts, drift, and contamination.

## Non-goals

- Automatically proving causality for a regression.
- Mixing measurements from incomparable hardware/configurations.
- Treating repeated retries as independent evidence without accounting for selection.
- Using one universal `|z| > 3` rule for every metric.
- Updating approved historical baselines during candidate evaluation.
- Providing a full experiment-design or fleet-monitoring platform in M2.

## Measurement record

Every historical observation SHALL bind to:

- Metric and unit.
- Test/manifest ID and schema version.
- Source revision and timestamp.
- Platform/environment class.
- Build type and compiler.
- SUT configuration.
- Block size, sample rate, channels, and workload where relevant.
- Repetition/group identifier.
- Raw value and validity.
- Known quarantine or incident label.

## Policy layers

### Layer 1: Absolute requirement

An externally meaningful limit such as no deadline misses, finite output, or latency below an agreed budget. Absolute violations fail regardless of historical distribution.

### Layer 2: Relative-to-baseline change

Compare current grouped observations to an approved baseline using absolute/percentage change and uncertainty appropriate to the metric.

### Layer 3: Outlier diagnostic

Classical z-score and robust score identify unusual single observations. Directionality is explicit: for latency, positive change may be harmful while improvement should not fail a two-sided absolute z-score policy.

### Layer 4: Sustained trend

EWMA or CUSUM detects smaller persistent shifts that may not violate a single-run guardrail.

## Statistical definitions

### Classical z-score

```text
z = (x - mean_baseline) / standard_deviation_baseline
```

Valid only when baseline count, variance, environment comparability, and model assumptions satisfy the manifest policy.

### Robust score

```text
robust_z = scale_constant * (x - median_baseline) / MAD_baseline
```

The scale constant and zero-MAD fallback are declared. Robust scoring does not eliminate the need to investigate multimodality or environment mixing.

### EWMA

```text
ewma_t = lambda * x_t + (1 - lambda) * ewma_(t-1)
```

Initialization, lambda, control limits, burn-in, and missing data are manifest-defined.

### CUSUM

Positive and/or negative cumulative sums use a target mean, reference value, and decision interval. Parameters and directionality are recorded.

## Requirements

### Baseline eligibility

- **STAT-BASE-001:** Historical observations SHALL be grouped by a declared environment key before estimating a baseline.
- **STAT-BASE-002:** Invalid, quarantined, warm-up, debug/sanitizer, and incomparable observations SHALL be excluded with an auditable reason.
- **STAT-BASE-003:** A baseline SHALL have a manifest-defined minimum sample count.
- **STAT-BASE-004:** Baseline approval and candidate evaluation SHALL be separate operations.
- **STAT-BASE-005:** Distribution diagnostics SHOULD identify obvious multimodality, trend, or regime change before a stationary baseline is accepted.
- **STAT-BASE-006:** Baseline membership and digest SHALL be recorded in every statistical result.

### Repeated measurement

- **STAT-RUN-001:** Performance tests SHALL record warm-up and measured repetitions separately.
- **STAT-RUN-002:** The aggregation unit SHALL be explicit: per callback, per run, or grouped runs.
- **STAT-RUN-003:** Candidate and baseline SHALL use comparable workload and environment keys.
- **STAT-RUN-004:** Repetitions SHALL preserve all raw observations; aggregate-only storage is insufficient for diagnostic runs.
- **STAT-RUN-005:** Confirmation reruns SHALL retain the original failure and be labeled as confirmation evidence.

### Classical z-score

- **STAT-Z-001:** Z-score SHALL be invalid when baseline count is insufficient or standard deviation is zero/below configured floor.
- **STAT-Z-002:** One-sided versus two-sided interpretation SHALL be explicit.
- **STAT-Z-003:** Z-score SHALL be reported as a diagnostic alongside raw and baseline values, not as a unit-bearing metric.
- **STAT-Z-004:** A z-score policy SHALL document why normal/stationary approximation is acceptable for that metric and grouping.

### Robust score

- **STAT-RZ-001:** Robust scoring SHALL report median, MAD, scale constant, sample count, and fallback state.
- **STAT-RZ-002:** Zero or near-zero MAD SHALL trigger an explicit absolute-tolerance fallback or invalid result.
- **STAT-RZ-003:** Robust and classical scores MAY disagree; reports SHALL preserve both without silently selecting the passing result.

### Trend detection

- **STAT-TREND-001:** EWMA/CUSUM state SHALL be computed only from ordered eligible observations.
- **STAT-TREND-002:** Algorithm parameters, initialization, control limits, and target SHALL be versioned policy inputs.
- **STAT-TREND-003:** Missing/invalid observations SHALL follow a declared skip/reset policy.
- **STAT-TREND-004:** A trend alert SHALL identify the earliest triggering observation and the sequence contributing to it.
- **STAT-TREND-005:** Historical recomputation with the same inputs and policy SHALL produce the same alert sequence.

### Multiple metrics and interpretation

- **STAT-MULTI-001:** Each metric SHALL retain an independent policy and directionality.
- **STAT-MULTI-002:** If many simultaneous statistical tests are used for a blocking gate, the project SHALL document family-wise/false-discovery handling or justify why it is unnecessary.
- **STAT-MULTI-003:** Statistical significance SHALL NOT be presented as engineering significance; raw effect size and absolute requirement remain visible.
- **STAT-MULTI-004:** Environment or workload changes SHALL be diagnosed before being labeled an SUT regression where evidence supports that distinction.

### Diagnostics

- **STAT-DIAG-001:** Reports SHALL show raw observations, eligible baseline, excluded points/reasons, and current candidate values.
- **STAT-DIAG-002:** Trend charts SHALL distinguish raw points, center/target, control limits, and triggered state.
- **STAT-DIAG-003:** Every alert SHALL include effect size in the metric's unit in addition to statistical score.
- **STAT-DIAG-004:** Insufficient history SHALL be visible as `insufficient_data`, not pass.

## Synthetic validation scenarios

The statistical subsystem is tested with deterministic generated histories:

1. Stable Gaussian-like baseline with no shift.
2. One isolated outlier.
3. Constant step shift.
4. Slow linear drift.
5. Variance increase without mean shift.
6. Contaminated baseline containing a large outlier.
7. Zero-variance baseline.
8. Two mixed environment modes.
9. Sparse missing/invalid observations.
10. Directional improvement that should not fail a harmful-regression policy.

Expected alert ranges are specified statistically with deterministic seeds rather than tuned from the same single sequence used for implementation.

## Acceptance criteria

1. Simple z-score works on an eligible stable baseline and becomes invalid for zero variance or insufficient count.
2. Robust score is less affected by a single contaminated baseline point and reports its fallback behavior.
3. Absolute guardrail catches a critical violation regardless of favorable historical statistics.
4. EWMA/CUSUM detects a configured small sustained shift earlier than a single-point 3-sigma policy in the selected synthetic scenario.
5. Environment mixing is rejected or separated rather than modeled as one broad distribution.
6. A performance improvement does not fail a one-sided harmful-regression policy.
7. The chart and JSON reproduce the exact baseline membership and triggering sequence.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-STAT-001` | `STAT-BASE-001..006` | Mixed eligible/ineligible history | Correct grouping, exclusion, and digest |
| `T-STAT-002` | `STAT-RUN-001..005` | Warm-up, measured, and confirmation runs | Raw observations retained and labeled |
| `T-STAT-003` | `STAT-Z-001..004` | Stable, insufficient, and zero-variance baselines | Valid score then explicit invalid states |
| `T-STAT-004` | `STAT-RZ-001..003` | One contaminated point and zero MAD | Robust result and declared fallback |
| `T-STAT-005` | `STAT-TREND-001..005` | Deterministic slow drift | Reproducible trigger sequence |
| `T-STAT-006` | `STAT-MULTI-001..004` | Multiple metrics and environment change | Independent policies and scoped diagnosis |
| `T-STAT-007` | `STAT-DIAG-001..004` | Render stable and alert histories | Complete evidence and insufficient-data visibility |

## Open questions

- [ ] Choose EWMA, CUSUM, or both for the first M2 demonstration.
- [ ] Set initial minimum baseline count through simulation and benchmark cost, not convenience.
- [ ] Select the robust-score scale convention and document it in the result schema.
- [ ] Decide whether performance histories live as small repository fixtures in M2 or are generated deterministically during tests.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial statistical regression contract | New specification |
