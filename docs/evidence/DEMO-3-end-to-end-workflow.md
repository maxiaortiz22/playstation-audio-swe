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
integer time-alignment transform, and the six focused metric requests. Each
request is bound to its implemented ID, method, version, unit, and exact
aggregate scope. OP-B is bound to accepted decision version `1.0.0` and source
SHA-256 `67b6d1be69196074986da4b20f274d8aec33ab92f65e5a0d672ac0561faaacab`
in addition to its existing parameter digest and values. Invalid schema or
semantic input returns `2` before the lazy native import/call. No generic
registry, plugin API, retry layer, or future-scenario scaffolding is introduced.

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
| `RPT-ART-006` | Mandatory files are serialized and validated before staged publication; failed reuse retains the prior complete package unchanged, while successful reuse replaces it completely |
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
| `python -m pytest tests/python --basetemp build/pytest-review-final` | `264` passed |
| `python -m build --wheel --no-isolation` | CPython 3.12 Windows wheel built |
| `python -m pytest tests/integration --basetemp build/pytest-review-integration` from `%TEMP%` | `17` passed against the installed wheel |
| `python -m pytest tests/e2e/test_demo3_installed_wheel.py --basetemp build/pytest-review-wheel-e2e` from `%TEMP%` | `1` passed; all four scenarios and deterministic repeat |
| installed-package import from `%TEMP%` | package/native `0.1.0`, Jinja2 `3.1.6` |

The focused DEMO-3 module contributes `51` passing cases after review. Negative
cases mutate every canonical metric field across all six requests and alter the
OP-B decision/source identity while asserting no native invocation. Reused
output tests force both result serialization and HTML reporting failures after
a prior successful run, assert no mixed package or success summary, and also
exercise successful complete replacement.

Direct installed-wheel CLI execution from `%TEMP%` produced the four expected
exit/status pairs: clean `0/pass`, delay `1/fail`, channel swap `1/fail`, and
dropout `1/fail`. The installed-wheel E2E asserts that a second equivalent
clean execution produces byte-identical `result.json`.

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
