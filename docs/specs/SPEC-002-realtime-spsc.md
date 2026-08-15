# SPEC-002: Real-time harness and SPSC transport

- **Status:** Accepted
- **Owners:** Native runtime subsystem
- **Created:** 2026-08-14
- **Last updated:** 2026-08-15
- **Target milestone:** M1 - Native harness and required extended stress evidence
- **Depends on:** SPEC-000, ADR-0002, ADR-0006, ADR-0007

## Context

Audio callbacks execute against a deadline. Blocking, allocation, unbounded work, or unsafe cross-thread communication can create dropouts even when DSP output is mathematically correct.

This specification defines a portable host-side simulation of those constraints. It cannot prove hard real-time behavior on a general-purpose OS, but it can verify design invariants, collect deadline distributions, and expose concurrency defects under stress and sanitizers.

## Goals

- Process audio in fixed-size blocks without callback-time allocation or blocking.
- Transfer fixed-size audio/telemetry data from one producer to one consumer through an SPSC ring buffer.
- Make overflow behavior observable and non-blocking.
- Measure processing time relative to the audio deadline.
- Verify ordering, memory visibility, wraparound, and lifetime safety.
- Expose coarse native operations to Python without involving Python in the callback.

## Non-goals

- Implementing MPMC communication.
- Claiming wait-free behavior for arbitrary element types.
- Guaranteeing hard real-time scheduling on Windows/Linux/macOS.
- Writing files, rendering plots, or invoking Python from the callback.
- Using a microbenchmark as a substitute for device/runtime validation.
- Assuming a proprietary console timer or thread API.

## Real-time model

For `frames_per_block` at `sample_rate_hz`:

```text
deadline_seconds = frames_per_block / sample_rate_hz
load_ratio = processing_seconds / deadline_seconds
```

The harness processes a finite or streamed sequence of blocks. A callback
thread publishes captured audio and fixed-size telemetry to two independent
typed SPSC queues. A consumer thread drains both transports and performs
non-real-time aggregation. ADR-0007 owns the inline payload, loss, counter, and
cache-alignment decisions.

## Native data contracts

### AudioBlock

The M1 inline capture-block representation has:

- Compile-time or initialization-time maximum frame and channel capacity.
- Runtime frame and channel counts not exceeding capacity.
- Trivially destructible storage.
- No ownership of heap-allocating child objects.
- Sequence number and stream frame offset.
- Optional flags for injected faults or discontinuities.

### TelemetryPacket

The telemetry packet is fixed-size and trivially copyable, containing at minimum:

- Monotonic sequence number.
- Stream frame offset.
- Frames processed.
- Start/end clock readings or measured duration.
- Deadline load ratio or enough data to derive it.
- Status flags.
- Cumulative producer drop count snapshot.

## SPSC design contract

Each queue has exactly one producer and one consumer. Its capacity is a power
of two selected before concurrent use. Capture and telemetry queues may have
different capacities and drop counts; their stream offsets and sequence
numbers permit offline association.

The intended index model uses monotonically increasing unsigned counters with masking for slot selection:

```text
slot = counter & (capacity - 1)
size = write_counter - read_counter
```

The producer owns writes to `write_counter`; the consumer owns writes to `read_counter`. Element contents are published before the write counter becomes visible. A freed slot becomes reusable only after the consumer publishes its read counter.

## Requirements

### Construction and type constraints

- **RT-SPSC-001:** Capacity SHALL be a non-zero power of two and SHALL be fixed before concurrent access.
- **RT-SPSC-002:** The implementation SHALL expose its usable capacity without an undocumented sentinel-slot reduction.
- **RT-SPSC-003:** M1 queue elements SHALL use fixed-capacity inline, trivially copyable storage; a preallocated block pool requires a later ADR amendment.
- **RT-SPSC-004:** Construction MAY allocate; `try_push`, `try_pop`, and callback processing SHALL NOT allocate.
- **RT-SPSC-005:** The queue SHALL be non-copyable and non-movable after concurrent use begins.
- **RT-SPSC-006:** The producer/consumer cardinality contract SHALL be documented and debug builds SHOULD detect obvious misuse where practical.

### Memory ordering and visibility

- **RT-MEM-001:** The producer SHALL write element data before publishing the write counter with release semantics.
- **RT-MEM-002:** The consumer SHALL acquire the published write counter before reading element data.
- **RT-MEM-003:** The consumer SHALL complete reading before publishing the read counter with release semantics.
- **RT-MEM-004:** The producer SHALL acquire the published read counter before reusing a slot that may still be owned by the consumer.
- **RT-MEM-005:** Thread-owned counter loads MAY use relaxed ordering when no cross-thread visibility depends on that load.
- **RT-MEM-006:** Atomics with independent write ownership SHALL reside in separately aligned and padded destructive-interference regions using the validated standard value, x86_64 fallback, or explicit override defined by ADR-0007; the selected value SHALL be recorded.

### Queue behavior

- **RT-QUE-001:** `try_push` SHALL return immediately with `false` when full.
- **RT-QUE-002:** `try_pop` SHALL return immediately with `false` when empty.
- **RT-QUE-003:** Successfully popped elements SHALL preserve producer order exactly.
- **RT-QUE-004:** A failed push SHALL NOT overwrite unread data.
- **RT-QUE-005:** A failed pop SHALL NOT modify the destination value.
- **RT-QUE-006:** Counter wraparound behavior SHALL be defined and tested with a reduced-width test implementation or controlled counter seeding.
- **RT-QUE-007:** Informational size/empty queries used across threads SHALL state whether they are snapshots and SHALL NOT be used as correctness preconditions for a later push/pop.

### Callback safety

- **RT-CB-001:** The callback SHALL NOT perform dynamic allocation or deallocation.
- **RT-CB-002:** The callback SHALL NOT acquire a blocking mutex, condition variable, semaphore, or file/network handle.
- **RT-CB-003:** The callback SHALL NOT perform file I/O, console I/O, formatting, or heavyweight logging.
- **RT-CB-004:** The callback SHALL NOT invoke Python, touch Python objects, or acquire the GIL.
- **RT-CB-005:** Exceptions SHALL NOT cross the callback boundary; recoverable native status is communicated through bounded flags/counters.
- **RT-CB-006:** Per-block work SHALL be bounded by configured channel/frame limits.
- **RT-CB-007:** Parameter changes visible to the callback SHALL use a documented atomic snapshot or preallocated command path.

### Overflow and loss

- **RT-OVR-001:** Audio processing SHALL continue when telemetry transport is full.
- **RT-OVR-002:** A full transport SHALL increment a lock-free drop counter and return without blocking.
- **RT-OVR-003:** Reports SHALL distinguish processing underruns/deadline misses from dropped telemetry.
- **RT-OVR-004:** Sequence gaps SHALL be observable by the consumer.
- **RT-OVR-005:** M1 capture and telemetry queues SHALL use drop-newest on full; a later overflow policy requires a specification and ADR amendment.

M1 uses drop-newest for both queues. A capture sequence gap invalidates
every metric whose required continuous measurement region spans that gap. A
metric may analyze the remaining contiguous segments independently only when
its manifest declares segmented semantics; segments are never concatenated as
if continuous. A telemetry-only gap preserves captured PCM validity but marks
runtime telemetry incomplete. Neither case is silently reconstructed.

### Timing

- **RT-TIME-001:** The portable harness SHALL use a monotonic steady clock for elapsed-time measurement.
- **RT-TIME-002:** Platform-specific cycle counters MAY be added only behind an abstraction that documents serialization, calibration, core migration, and fallback behavior.
- **RT-TIME-003:** Timing overhead SHALL be measured or bounded and recorded for performance claims.
- **RT-TIME-004:** The harness SHALL report count, p50, p95, p99, maximum, deadline misses, and maximum load ratio.
- **RT-TIME-005:** Warm-up iterations SHALL be excluded from reported steady-state metrics and their count recorded.
- **RT-TIME-006:** Performance results SHALL record build type, compiler, CPU, thread configuration, block size, sample rate, channel count, and competing-load profile.
- **RT-TIME-007:** A host timing result SHALL be described as a host benchmark, not a console or hard-real-time guarantee.

### Block-processing correctness

- **RT-BLK-001:** Stream frame offsets and sequence numbers SHALL be monotonic unless an injected discontinuity is declared.
- **RT-BLK-002:** For a component whose specification is chunking-invariant, processing the same stream with supported block sizes SHALL produce equivalent concatenated output.
- **RT-BLK-003:** Stateful components SHALL expose explicit reset semantics and deterministic state after reset.
- **RT-BLK-004:** Partial final blocks SHALL have explicit valid-frame counts; padding SHALL NOT appear as analyzed program material.
- **RT-BLK-005:** The harness SHALL support deliberate CPU-load and consumer-stall injection without adding blocking work to the callback.

### Python boundary

- **RT-PY-001:** Python SHALL configure and start the native harness outside callback execution.
- **RT-PY-002:** Native execution MAY release the GIL while no Python objects are accessed.
- **RT-PY-003:** Results SHALL cross into Python after native aggregation or in coarse batches.
- **RT-PY-004:** Python cancellation SHALL publish a non-blocking native stop request, the harness SHALL check it after the current block and before starting the next block, and Python SHALL join outside the callback.

## Verification strategy

### Functional queue tests

- Capacities 1, 2, and larger powers of two.
- Empty/full transitions.
- Multiple wraparounds.
- Destination preservation after failed pop.
- Unread-data preservation after failed push.
- Exact sequence ordering.

### Concurrent stress

- Millions of monotonically numbered packets.
- Random producer/consumer yielding and stalls.
- Consumer verifies no duplicate, reordering, or corruption.
- Expected gaps only when overflow injection is enabled.
- A short deterministic producer/consumer stress case on pull requests.
- A longer ThreadSanitizer job on Ubuntu 24.04 x86_64 with Clang 18 in the
  extended scheduled/manual tier.

### Callback-contract checks

- Test-only allocation instrumentation around the callback loop.
- Static/code-review checks for disallowed operations.
- Fault injection for full queue and slow consumer.
- Sanitizer builds separate from timing claims.

### Performance evidence

Benchmarks compare processing duration to deadline rather than asserting one universal microsecond limit. CI may enforce a broad safety guardrail on controlled runners, while trend policy belongs to SPEC-006.

## Acceptance criteria

1. The queue preserves all values and order in a no-overflow million-packet stress test.
2. Deliberate consumer stalls create only declared drops and never block the callback.
3. The callback allocation counter remains zero after initialization.
4. ThreadSanitizer reports no race in supported CI environments.
5. Timing reports include distribution, audio deadline, load ratio, and environment provenance.
6. A stateful native processor produces equivalent concatenated output across approved block-size partitions.

## Planned test traceability

| Test ID | Requirement IDs | Scenario | Expected result |
|---|---|---|---|
| `T-RT-001` | `RT-SPSC-001`, `RT-SPSC-002`, `RT-SPSC-003`, `RT-SPSC-004`, `RT-SPSC-005`, `RT-SPSC-006` | Construct valid/invalid capacities, inspect inline type behavior, and exercise debug ownership checks | Contract enforced before concurrency |
| `T-RT-002` | `RT-QUE-001`, `RT-QUE-002`, `RT-QUE-003`, `RT-QUE-004`, `RT-QUE-005`, `RT-QUE-007` | Empty/full boundary sequence plus stale snapshot queries | Immediate failure without corruption; snapshots not used as preconditions |
| `T-RT-003` | `RT-QUE-003`, `RT-MEM-001`, `RT-MEM-002`, `RT-MEM-003`, `RT-MEM-004`, `RT-MEM-005` | Concurrent ordered run with randomized yields and static memory-order review | Exact ordered delivery and recorded acquire/release evidence |
| `T-RT-004` | `RT-QUE-006` | Seed counters near wrap | Correct wrap behavior |
| `T-RT-005` | `RT-CB-001`, `RT-CB-002`, `RT-CB-003`, `RT-CB-004`, `RT-CB-005`, `RT-CB-006`, `RT-CB-007` | Separately instrument allocation, blocking calls, I/O/logging, exceptions, work bounds, and parameter snapshots | Zero callback-contract violations |
| `T-RT-006` | `RT-OVR-001`, `RT-OVR-002`, `RT-OVR-003`, `RT-OVR-004`, `RT-OVR-005` | Stall audio and telemetry consumers independently until full | Processing continues; validity, gaps, and independent drop counts agree |
| `T-RT-007` | `RT-TIME-001`, `RT-TIME-002`, `RT-TIME-003`, `RT-TIME-004`, `RT-TIME-005`, `RT-TIME-006`, `RT-TIME-007` | Benchmark multiple block sizes outside sanitizers | Complete provenance and deadline distribution without hard-real-time claims |
| `T-RT-008` | `RT-BLK-001`, `RT-BLK-002`, `RT-BLK-003`, `RT-BLK-004`, `RT-BLK-005` | Partition identical streams, partial final block, reset, CPU load, and consumer stall | Monotonic metadata, equivalent valid output, bounded injected behavior |
| `T-RT-009` | `RT-PY-001`, `RT-PY-002`, `RT-PY-003`, `RT-PY-004` | Execute and cancel the harness through pybind11 | No Python callback access; stop observed before another block; coarse result returned |
| `T-RT-010` | `RT-MEM-006` | Compile forced standard, fallback, and override alignment paths; inspect adjacent wrappers | Valid layout/provenance or explicit configuration failure |

## Open questions

No question blocks M1 implementation. ADR-0007 selects inline typed queues and
the validated x86_64 alignment fallback. ADR-0006 selects Ubuntu 24.04 x86_64
with Clang 18 for TSan. Cancellation has a block-boundary semantic bound; a
wall-clock SLO may be proposed only after the harness supplies reproducible
measurements on a controlled runner.

## Revision history

| Date | Change | Classification |
|---|---|---|
| 2026-08-14 | Initial real-time/SPSC contract | New specification |
| 2026-08-15 | Resolve payload, overflow, alignment, TSan, cancellation, and traceability decisions; accept contract | Compatible clarification |
