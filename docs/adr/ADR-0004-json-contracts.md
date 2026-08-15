# ADR-0004: Use strict JSON for M1 serialized contracts

- **Status:** Accepted
- **Date:** 2026-08-15

## Context

M1 needs one authoring and interchange format for manifests, metric policies,
and machine-readable results. Supporting JSON and YAML simultaneously would
add parser behavior, type coercion, duplicate-key handling, and digest
semantics before the first vertical validation slice exists.

## Decision

M1 manifests, embedded policies, and results use UTF-8 JSON validated with
versioned JSON Schema Draft 2020-12 schemas.

Under `SYS-EXE-007`, M1 readers:

- Reject duplicate object keys, non-standard comments, trailing commas, and
  non-finite number tokens.
- Reject unknown authoring fields unless a schema explicitly defines an
  extension point.
- Avoid implicit string, Boolean, or numeric coercion.
- Report schema failures with the document path and schema path.

The manifest digest is SHA-256 over the exact bytes of the original manifest.
The report package preserves that byte-identical manifest. M1 does not support
manifest includes or externally referenced policy files, so there is no second
ambiguous "resolved document" digest.

JSON outputs are serialized deterministically for testability, but their
semantic identity is the recorded schema version plus content, not an
undocumented canonical-JSON algorithm.

## Consequences

### Positive

- One parser and schema system covers authoring and results.
- Digests identify the exact input used by a run.
- JSON Schema maps directly to validation errors and CI checks.
- No YAML parser is required in M1.

### Costs and risks

- JSON is more verbose than YAML for hand-authored policies.
- Standard Python JSON parsing must be configured explicitly to reject
  duplicate keys and non-finite values.
- Schema evolution and additive extension points must remain intentional.

## Alternatives considered

- **YAML authoring with JSON results:** more concise authoring, but introduces
  aliases, implicit typing, duplicate-key differences, and another dependency.
- **Support both formats:** convenient for users but doubles M1 parser and
  conformance surface without improving the demonstration.
- **Canonical JSON digest:** useful for semantic signing, but unnecessary when
  the original manifest bytes are packaged and hashed directly.
