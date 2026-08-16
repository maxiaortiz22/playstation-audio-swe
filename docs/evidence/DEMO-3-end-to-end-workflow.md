# DEMO-3 end-to-end workflow evidence

- **Profile:** Interview Demo Core, DEMO-3 only
- **Base:** `6b2d3f06811744cd13aa72a0af3b19515e36aa99`
- **Branch:** `codex/demo-end-to-end-workflow`
- **Date:** 2026-08-16
- **Specification status effect:** none; SPEC-000, SPEC-001, and SPEC-004
  remain `Accepted`, not `Verified`

## Implemented boundary

The canonical command is:

```text
avsys run --manifest <path> --output <directory>
```

[`python/avsys/workflow.py`](../../python/avsys/workflow.py) implements only the
DEMO-3 vertical slice:

```text
strict manifest -> deterministic PRBS15 -> native_passthrough -> optional
labeled fault -> structural validation -> OP-B integer alignment -> raw
latency policy -> declared compensation -> focused analysis/policies ->
result.json + report.html
```

The runner accepts exactly `native_passthrough/1`, stereo float32 input, the
explicit 127-frame block size, zero or one supported DEMO fault, one declared
integer time-alignment transform, and the six focused metric requests. Invalid
schema or semantic input returns `2` before the lazy native import/call. No
generic registry, plugin API, retry layer, or future-scenario scaffolding is
introduced.

The four manifests are:

- [`demo3-clean.json`](../../configs/manifests/demo3-clean.json)
- [`demo3-delay.json`](../../configs/manifests/demo3-delay.json)
- [`demo3-channel-swap.json`](../../configs/manifests/demo3-channel-swap.json)
- [`demo3-dropout.json`](../../configs/manifests/demo3-dropout.json)

Each manifest embeds the accepted M1-only OP-B identity, digest, seven values,
units through its metric contracts, and threshold rationale. There is no
implicit policy path, automatic selection, or universal fallback. The declared
`mean_all_channels` synchronization copy is invariant to stereo permutation;
measurement remains on the original two-channel buffers, so alignment cannot
erase mapping evidence.

## Deterministic result identity

The requested byte-deterministic JSON exposed an ambiguity between volatile
run timestamps and reproducible fixture results. SPEC-004 was clarified before
implementation: these deterministic manifests explicitly declare an RFC 3339
logical fixture timestamp in the selected SUT parameters, `run_id` is derived
from the exact manifest digest, and results label the timestamp basis and state
that no wall-clock time was recorded. No timestamp is silently invented for a
manifest that does not request this mode.

Two equivalent clean executions produced byte-identical `result.json` and
`report.html`. Serialization is sorted, finite, UTF-8 JSON and validates with
[`result.schema.json`](../../schemas/v1/result.schema.json). The package also
contains the exact input manifest and deterministic stimulus metadata.

## Policy and diagnostic outcomes

| Scenario | Exit/status | Intended evidence |
|---|---|---|
| Clean | `0` / `pass` | Raw lag `0` frames, identity mapping `(0, 1)`, null residual, no dropout |
| Delay | `1` / `fail` | Raw lag `16` frames (`0.3333333333333333` ms) fails before alignment; applied compensation is `16` frames and aligned residual peak is `0.0` linear FS |
| Channel swap | `1` / `fail` | Raw lag remains `0`; observed-to-expected mapping is `(1, 0)` with configured margin retained |
| Dropout | `1` / `fail` | One `exact_zero` event on `left` and `right`, interval `[320, 384)` frames / `[0.006666666666666667, 0.008)` seconds |

Policy evaluations retain the stable policy ID, actual value, inclusive/exact
expected condition, threshold, unit, severity, mandatory flag, rationale,
owner, and requirement IDs. Raw latency is serialized separately from named
integer-time compensation and residual metrics. Per-channel gain, polarity,
residual, channel scoring/margin, and dropout details remain independent
observations.

Dropout `confidence = 1.0` follows the clarified SPEC-001 meaning: every
declared deterministic rule condition matched for the interval. It is labeled
as deterministic rule evidence, not a probability estimate.

## HTML and dependency boundary

[`python/avsys/reporting.py`](../../python/avsys/reporting.py) uses Jinja2 3.1.6
with autoescaping, as required by SPEC-004 and permitted by ADR-0006. The exact
direct/transitive versions, hashes, source, licenses, and purpose are recorded
in the runtime lock and
[`dependency inventory`](../dependency-inventory.md). The report has embedded
CSS, no hosted resource, CDN, web framework, required JavaScript, plot, or
binary asset. Text labels accompany status color.

The first view shows status, test/baseline/candidate identity, policy findings,
and reproduction. Later sections explicitly label raw observations,
compensated/aligned observations, localized events, and provenance. The
copy-pastable command targets the packaged byte-identical `manifest.json`.

## Automated evidence

| Requirements | Evidence |
|---|---|
| `SYS-EXE-001`, `SYS-EXE-006..007` | Exact supported SUT/fault set, strict/schema/semantic validation before native execution, and invalid-manifest mock proving no native call |
| `SYS-DIAG-001..004` | Values, expected conditions, units, requirement IDs, localized frame/second intervals, distinct raw/compensated sections, and reproduction |
| `POL-EVAL-001..006` | Immutable observations, unit/operator/scope validation, independent latency/residual results, correct fail/invalid precedence |
| `RPT-SCHEMA-003..004` | Structured metrics/policies and full result-schema validation for every scenario |
| `RPT-HTML-001..004`, `RPT-HTML-008..009` | Offline autoescaped HTML, text status, raw/aligned distinction, and frame/second event detail |
| `RPT-REP-001` | Display command plus structured argument vector against packaged exact manifest |
| `CI-RUN-001..002`, `CI-RUN-004`, `CI-RUN-009..010` | Same runner/manifests locally and in one existing Linux/GCC wheel row; exits `0/1/2/3`; no network assets |

Python evidence is in
[`test_demo3_workflow.py`](../../tests/python/test_demo3_workflow.py). The real
installed-wheel flow is in
[`test_demo3_installed_wheel.py`](../../tests/e2e/test_demo3_installed_wheel.py)
and executes from a temporary working directory. The workflow adds one
conditional step to the existing Linux GCC wheel job only; it does not add or
expand a matrix.

## Local verification

The final Windows current-worktree verification used the locked Python 3.12
environment and the Visual Studio 2022 v143 x64 environment:

| Command | Result |
|---|---|
| `cmake --fresh --preset native-debug -DCMAKE_CXX_COMPILER=cl.exe` | configured |
| `cmake --build --preset native-debug` | built |
| `ctest --preset native-debug` | `14/14` passed |
| `python -m pytest tests/python --basetemp build/pytest-final` | `228` passed |
| `python -m build --wheel --no-isolation` | CPython 3.12 Windows wheel built |
| `python -m pytest tests/integration --basetemp build/pytest-integration-final` from `%TEMP%` | `17` passed against the installed wheel |
| `python -m pytest tests/e2e/test_demo3_installed_wheel.py --basetemp build/pytest-e2e-final` from `%TEMP%` | `1` passed; all four scenarios and deterministic repeat |
| installed-package import from `%TEMP%` | package/native `0.1.0`, Jinja2 `3.1.6` |

Direct installed-wheel CLI execution from `%TEMP%` produced the four expected
exit/status pairs: clean `0/pass`, delay `1/fail`, channel swap `1/fail`, and
dropout `1/fail`. A second equivalent clean execution produced the same
`result.json` SHA-256,
`60184c1423d44f9e6315b60a191e473640d14ea4da96bfb24dae0b472492198a`.

The HTML assertions exercise self-containment, text status and severity,
autoescaping, raw/aligned section placement, and localized event evidence.
Browser visual inspection of a local `file:` report was unavailable because
the controlled browser blocks local-file navigation; no hosted resource or
alternate browser was introduced. Linux/GCC and sanitizer execution remain
hosted-CI evidence rather than local Windows evidence.

## Explicit limits

DEMO-3 does not implement or claim spectral aggregation, drift, click,
clipping, crosstalk, repeated-block/DC detectors, a callback harness,
benchmarks, dashboard, artifact upload/retention service, complete baseline
integration, or a generic plugin architecture. No SPEC is marked `Verified`.
Full M1 filter behavior, extended CI evidence, exhaustive artifacts, and all
requirements outside the Interview Demo Core coverage matrix remain pending.
