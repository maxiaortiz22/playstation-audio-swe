# Repository Agent Instructions

## Scope and purpose

These instructions apply to the entire repository. A more specific `AGENTS.md`
or `AGENTS.override.md` in a descendant directory may refine them for that
subtree.

This repository is an independent, interview-oriented demonstration of an
audio validation system. It is not a PlayStation product and must not imply
access to Sony Interactive Entertainment source code, internal APIs, test
assets, requirements, or proprietary knowledge.

The repository is intentionally developed through Specification-Driven
Development (SDD). The objective is not merely to produce DSP code: each
observable behavior must have an explicit contract, traceable verification,
and actionable diagnostics.

## Required reading before work

Before proposing or implementing a change:

1. Read `README.md` for project scope, architecture, and the current milestone.
2. Read `docs/sdd/README.md` for lifecycle, authority, and completion rules.
3. Read every specification under `docs/specs/` affected by the request.
4. Read the relevant accepted decisions under `docs/adr/`.
5. Inspect the current Git status and preserve unrelated user changes.

Do not assume that a prior chat, external document, or verbal decision is part
of the repository contract. If it changes the design, encode it in a spec or
ADR before relying on it.

## Source-of-truth hierarchy

When repository documents disagree, use this order:

1. Accepted or verified feature specifications.
2. Accepted Architecture Decision Records.
3. Versioned schemas and test-manifest contracts.
4. `README.md` and supporting design notes.
5. Implementation comments.

An explicit new product decision must be reflected in the higher-authority
document before the implementation is treated as conforming.

## Specification-driven workflow

- Do not implement production behavior from a `Draft` specification.
- A task may refine a draft and then implement it only after its blocking open
  questions are resolved and its status is changed to `Accepted`.
- Amend the specification before code when implementation reveals an incorrect
  or ambiguous contract.
- Keep mandatory requirement IDs stable. Never silently reuse or renumber an
  accepted ID.
- Map every `SHALL` and `SHALL NOT` requirement to an automated test or an
  explicitly documented manual verification.
- Reference requirement IDs in test names, test metadata, or parameterization.
- Include positive, negative, boundary, and labeled fault-injection cases where
  the requirement permits them.
- Do not mark a specification `Verified` until all mandatory requirements have
  recorded evidence and no required work remains.
- Keep milestone and non-goal boundaries explicit. Do not turn documented
  future extensions into incidental scope.

When a threshold, estimator, policy, or preprocessing transform is not fully
specified, resolve and document it instead of selecting a convenient default.

## Architecture boundaries

- C++ owns bounded block processing, native DSP components, the simulated
  runtime, SPSC transport, and other performance-sensitive primitives.
- Python owns orchestration, configuration, offline analysis, policy
  evaluation, visualization, and reporting.
- `pybind11` exposes coarse-grained native operations. Avoid per-sample Python
  calls and chatty cross-language APIs.
- Buffer bindings must state dtype, shape, channel layout, mutability,
  contiguity, ownership, and lifetime behavior.
- Keep the native core directly testable without importing Python.
- Keep metric computation separate from pass/warn/fail policy.
- Keep raw observations separate from permitted alignment or compensation.
  Alignment must never erase the latency, gain, polarity, drift, or ambiguity
  evidence used to diagnose a regression.

## Audio and numerical contracts

Every audio-facing change must make the following explicit where applicable:

- Sample rate, frame count, time units, and rounding convention.
- PCM representation, dtype, scaling, and full-scale convention.
- Channel count, ordering, layout, and interleaving.
- Reference level and amplitude, power, or decibel convention.
- Window, FFT size, overlap, normalization, and amplitude correction.
- Alignment search limits, ambiguity handling, and allowed transforms.
- Treatment of silence, short overlap, denormals, clipping, NaN, and infinity.
- Deterministic seed, fixture provenance, and tolerance rationale.

Prefer deterministic synthetic fixtures for detector tests. A validator test
must prove that a labeled defect is detected, not just that the happy path
passes. Avoid universal thresholds without evidence; derive them from the
contract, numerical analysis, or a reproducible calibration experiment.

## Real-time safety

Code designated as real-time or callback-path code must have bounded work and
must not:

- Allocate or free dynamic memory.
- Acquire locks or wait on blocking synchronization.
- Perform file, console, network, or other blocking I/O.
- Call Python or perform logging and report generation.
- Throw exceptions across the callback boundary.

Preallocate resources, document ownership and overflow policy, and expose
telemetry through bounded non-blocking transport. Test wraparound, full/empty
transitions, overflow behavior, and long-running producer/consumer progress for
SPSC structures.

## Diagnostics and reproducibility

A bare pass/fail result is incomplete. Failures should identify what changed,
where it changed, by how much, which requirement was violated, what artifacts
support the diagnosis, and how to reproduce it.

Results must preserve relevant provenance such as manifest digest, random seed,
source revision, dependency revision, toolchain, platform, and configuration.
Generated output must be deterministic apart from explicitly documented
environmental measurements.

## Dependencies, fixtures, and submodules

- Treat `third_party/pybind11` as a pinned Git submodule.
- Do not edit files inside the submodule for repository features.
- Do not advance the pinned revision without the decision record and
  compatibility validation required by `ADR-0002`.
- Do not add a production dependency merely for convenience. Document the
  reason, alternatives, license implications, and reproducibility impact.
- Do not commit proprietary, confidential, or license-incompatible audio or
  HRTF data. Record the origin and redistribution terms of external fixtures.
- Keep generated build products, caches, large captures, and local reports out
  of version control unless a specification explicitly requires a small golden
  artifact.

## Verification expectations

Run the narrowest relevant checks during iteration and the complete applicable
suite before declaring the task complete. Once build and test entry points
exist, use the canonical commands documented in `README.md` rather than
inventing parallel workflows.

For documentation-only changes, at minimum:

- Run `git diff --check`.
- Verify local Markdown links and code fences.
- Confirm referenced requirement IDs and file paths exist.
- Run `git submodule status` when dependency documentation changes.

For implementation changes, also:

- Run the affected native, Python, and cross-language tests.
- Exercise the required labeled fault cases.
- Review generated diagnostics when report behavior changes.
- Report any skipped platform, sanitizer, stress, or nightly-tier checks.

Never claim a command passed unless it was run in the current worktree. If a
check cannot run, state the exact reason and leave the associated requirement
unverified.

## Change discipline

- Keep changes scoped to the requested specification or decision.
- Preserve unrelated user modifications and avoid destructive Git operations.
- Update docs, schemas, tests, and implementation together when a contract
  changes.
- Prefer small, reviewable commits with intent-focused messages.
- Summarize changed contracts, validation performed, and remaining risks when
  handing work back.
