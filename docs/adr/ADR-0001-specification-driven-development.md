# ADR-0001: Use Specification-Driven Development

- **Status:** Accepted
- **Date:** 2026-08-14

## Context

Audio validation tools can produce precise numbers while measuring the wrong behavior. Alignment, normalization, windowing, threshold selection, and statistical preprocessing can each hide a real defect when their intent is not explicit.

The project also spans native real-time-style code, Python analysis, serialized manifests, reports, and CI. Implementing these pieces independently before agreeing on their contracts would create incompatible assumptions.

## Decision

The project will use Specification-Driven Development. Mandatory behavior is defined with stable requirement IDs before implementation. Tests and diagnostics will trace back to those IDs.

Specifications are authoritative for behavior. Architecture Decision Records capture durable cross-cutting decisions and their consequences.

## Consequences

### Positive

- Measurement intent and allowed transformations are reviewable.
- C++ and Python can share explicit boundary contracts.
- Test coverage can be evaluated against requirements.
- Breaking changes become visible before they corrupt baselines or reports.
- Interview discussions can focus on engineering decisions rather than undocumented implementation details.

### Costs

- Initial implementation begins later.
- Specifications require maintenance when behavior changes.
- Review must distinguish useful precision from unnecessary design lock-in.

## Alternatives considered

- **Implementation-first prototypes:** faster initial feedback but too likely to encode accidental metric semantics.
- **README-only design:** insufficient for requirement traceability and schema evolution.
- **Test-driven development alone:** valuable during implementation, but tests still need an agreed statement of what should be measured.
