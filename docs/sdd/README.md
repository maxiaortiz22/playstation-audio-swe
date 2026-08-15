# Specification-Driven Development

This repository uses Specification-Driven Development (SDD): observable behavior and verification criteria are designed before production implementation.

SDD is used here to solve three risks common in audio validation systems:

- A mathematically correct metric can still measure the wrong property.
- An allowed preprocessing step can accidentally hide the regression being measured.
- A test can be repeatable while still producing unhelpful or misleading diagnostics.

## Source-of-truth hierarchy

When documents disagree, authority is resolved in this order:

1. An accepted or verified feature specification.
2. An accepted Architecture Decision Record.
3. Versioned JSON schema and test manifest contracts.
4. The README and supporting design notes.
5. Implementation comments.

Implementation behavior that is not supported by a specification is treated as accidental behavior until documented.

## Specification states

| State | Meaning |
|---|---|
| `Draft` | Open for design changes; implementation should not depend on unstable details. |
| `Review` | Scope and contracts are proposed; reviewers validate ambiguity and testability. |
| `Accepted` | Requirements are approved and may drive implementation. |
| `Implemented` | Code exists, but full requirement verification may still be incomplete. |
| `Verified` | All acceptance criteria have traceable evidence. |
| `Superseded` | A newer specification replaces this document. |

## Requirement language

- `SHALL`: mandatory, testable behavior.
- `SHALL NOT`: prohibited, testable behavior.
- `SHOULD`: expected default with documented exceptions.
- `MAY`: optional behavior that must not be assumed by consumers.

Every mandatory requirement receives a stable identifier:

```text
<SPEC>-<CATEGORY>-<NUMBER>

Examples:
CMP-ALIGN-001
RT-SPSC-004
RPT-SCHEMA-002
```

Requirement IDs remain stable after acceptance. If behavior is removed, the ID is retained and marked obsolete rather than silently reused.

## Required specification sections

Each feature specification contains:

1. Metadata and status.
2. Context and problem statement.
3. Goals and non-goals.
4. Definitions and assumptions.
5. Inputs and outputs.
6. Functional requirements.
7. Numerical or real-time behavior.
8. Failure behavior and diagnostics.
9. Acceptance criteria.
10. Planned test traceability.
11. Dependencies and open questions.

Use [spec-template.md](spec-template.md) for new specifications.

## Lifecycle

### 1. Draft

The author defines the observable contract and explicitly identifies assumptions. Algorithms may be proposed, but a requirement should describe externally verifiable behavior rather than an implementation detail unless that detail is itself part of the contract.

### 2. Review

Reviewers challenge:

- What exact property is being measured?
- What transformations are allowed before measurement?
- Can the proposed metric hide another defect?
- Are units, reference levels, channel conventions, and coordinate systems explicit?
- Is the threshold tied to a requirement or merely convenient?
- Can the validator be tested using a labeled synthetic fault?
- Does failure output make the issue reproducible?

### 3. Acceptance

A specification moves to `Accepted` when all Milestone 1 blocking decisions are resolved, all `SHALL` statements are testable, and its dependencies are compatible with other accepted specifications.

### 4. Implementation

Implementation proceeds requirement by requirement. Tests reference requirement IDs in their names, metadata, or parameterization. A change that discovers an incorrect contract amends the specification first.

### 5. Verification

Verification records:

- Automated test identifiers and results.
- Environment and toolchain.
- Generated artifacts where visual or auditory evidence matters.
- Known limitations.
- Any accepted deviations.

The status changes to `Verified` only when no mandatory requirement remains unverified.

## Change control

Changes are classified as:

- **Clarification:** no observable behavior changes; wording only.
- **Compatible extension:** adds optional behavior without invalidating existing manifests or results.
- **Breaking change:** changes units, semantics, defaults, schemas, thresholds, or existing behavior.

Breaking changes require:

1. A spec revision note.
2. A schema/version decision where serialized data changes.
3. Migration guidance.
4. Updated test vectors and compatibility coverage.

## Test traceability

Specifications list planned test IDs before implementation. The future test suite will emit a machine-readable traceability report mapping:

```text
requirement -> test -> result -> artifact
```

Coverage means requirement coverage, not merely source-line coverage. Source coverage remains useful but cannot prove that the measurement contract is correct.

## Audio-specific review checklist

Before accepting a metric specification, verify:

- Sample rate and time units.
- PCM representation, dtype, scaling, and full-scale convention.
- Channel count, layout, ordering, and interleaving.
- Treatment of silence, denormals, NaN, and infinity.
- Window type, FFT size, overlap, and amplitude correction.
- Reference level and dB convention.
- Alignment search range and ambiguity handling.
- Whether delay, gain, polarity, drift, or phase compensation is permitted.
- Behavior when overlap is too short.
- Statistical assumptions and minimum sample count.
- Deterministic seed and test-vector provenance.
- Diagnostic artifact retention and reproduction instructions.

## Definition of done

A feature is done only when the repository contains:

- An accepted specification.
- An implementation satisfying every mandatory requirement.
- Positive, negative, boundary, and fault-injection tests.
- User-facing documentation.
- Actionable failure diagnostics.
- CI coverage appropriate to its execution cost and determinism.
