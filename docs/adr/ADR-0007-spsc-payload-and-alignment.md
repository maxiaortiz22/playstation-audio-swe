# ADR-0007: Use inline SPSC payloads and explicit cache-line separation

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

M1 needs loss behavior that is simple to reason about in a callback while
keeping captured audio distinct from timing telemetry. A preallocated block
pool would reduce large-value copies but adds reclamation and lifetime states
that must themselves be proved. Independently written queue indices can also
share a cache line unless their storage is separated deliberately.

## Decision

M1 uses two typed SPSC queues with storage allocated before concurrent use:

- The capture queue stores fixed-capacity inline float32 `AudioBlock` values
  with valid frame/channel counts, sequence, stream offset, and status flags.
- The telemetry queue stores fixed-size, trivially copyable
  `TelemetryPacket` values.

Each queue uses drop-newest independently. A capture gap invalidates comparison
of the missing interval. A telemetry-only gap preserves the PCM comparison but
marks runtime telemetry incomplete. Sequence gaps and independent cumulative
drop counters make both cases observable.

Queue counters are unsigned 64-bit values. Capacity is a non-zero power of two
and is constrained below `2^63`, so unsigned subtraction distinguishes the
bounded live queue distance across wraparound. Required queue atomics must be
lock-free on supported M1 targets or configuration fails before streaming.

Producer- and consumer-owned counters use internal wrapper types aligned and
padded to a project compile-time destructive-interference value:

1. Use `std::hardware_destructive_interference_size` when the compiler exposes
   it as a valid power of two not smaller than `alignof(max_align_t)`.
2. Otherwise use the documented 64-byte fallback on supported x86_64 targets.
3. An explicit build override must be a power of two and meet the same minimum.
4. An unreviewed architecture without a valid standard value or override fails
   configuration instead of silently assuming 64 bytes.

The selected value is recorded in test provenance. Static assertions verify
wrapper alignment and size, while tests verify that adjacent counter objects
occupy distinct interference regions. This is a best-effort false-sharing
control, not a universal cache-topology guarantee, and it is not exposed as a
public ABI layout.

## Consequences

### Positive

- Queue ownership and overflow semantics remain direct and bounded.
- Audio loss is distinguishable from telemetry loss.
- M1 avoids block-pool reclamation and borrowed-pointer lifetime hazards.
- The fallback is explicit and testable on the selected x86_64 platforms.

### Costs and risks

- Inline audio blocks may increase copy cost and queue memory.
- `std::hardware_destructive_interference_size` can vary by compiler flags, so
  it remains an internal, provenance-recorded build value.
- Functional tests and TSan cannot prove that a cache layout is optimal.

If extended benchmarks show material callback load from inline copies, a later
ADR may introduce producer reservation/commit or a preallocated pool without
changing the observable overflow and ownership contracts silently.

## Alternatives considered

- **Indices into a block pool:** lower copying, but more complex reclamation,
  generation, and shutdown behavior.
- **One combined audio/telemetry queue:** preserves one sequence but couples
  small telemetry retention to large audio-capture pressure.
- **No explicit separation:** simpler layout but avoidable false-sharing risk.
- **Unconditional 64-byte alignment on every architecture:** not a portable
  claim beyond the x86_64 M1 scope.
