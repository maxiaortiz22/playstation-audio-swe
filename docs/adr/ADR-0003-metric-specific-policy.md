# ADR-0003: Use metric-specific validation policy

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

Audio equivalence is not one concept. A deterministic format converter may require bit-exact output, while a cross-platform floating-point renderer may permit small numerical differences. Latency, spectral response, dropouts, and long-term performance trends also have different units and risk profiles.

A single global threshold would either miss meaningful regressions or produce chronic false positives.

## Decision

Validation policy will be declared per test and per metric. Each policy records:

- Metric definition and units.
- Directionality: higher, lower, or two-sided.
- Absolute requirement or tolerance.
- Optional relative-to-baseline threshold.
- Minimum evidence or repeat count.
- Severity: informational, warning, or failure.
- Any permitted preprocessing or compensation.
- Rationale and owner.

No transform or threshold is implicitly inherited merely because another test uses it.

## Consequences

- Manifests are more verbose but auditable.
- Reports can explain the exact violated requirement.
- Baseline changes require review rather than automatic acceptance.
- The policy engine must detect contradictory or dimensionally invalid rules.

## Alternatives considered

- **One residual dBFS threshold:** simple but content-level dependent and unable to model latency or categorical failures.
- **Golden-file equality everywhere:** too brittle across intended floating-point or platform variation.
- **Perceptual score only:** may hide structural defects such as swapped channels, NaNs, or timing changes.
