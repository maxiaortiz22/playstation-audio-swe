# T-CMP-CAL-001 alignment-ambiguity calibration method

- **Status:** Frozen method for the FASE A spike
- **Specification status:** SPEC-001 remains `Review`
- **Production comparator:** Out of scope
- **Configuration:** [`t_cmp_cal_001.json`](../../configs/calibration/t_cmp_cal_001.json)

This document fixes the labels, score conventions, corpus separation, and
error accounting before either calibration or holdout is evaluated. Numeric
values explored here are candidates for the studied M1 stimulus class, not
repository-wide defaults.

## Oracle labels and errors

Every case is generated with one oracle class:

- `unique`: exactly one physical correspondence is intended inside the
  inclusive reported-lag search bounds, its declared evidence is sufficient
  for at least one explored operating point, and `oracle_lag_frames` is an
  exact integer.
- `ambiguous`: two or more equivalent correspondences exist inside the search
  bounds, or the construction deliberately produces a contiguous primary
  plateau. It has no single correct lag.
- `invalid`: the construction provides no trustworthy synchronization
  evidence because of silence/near-silence or because every eligible overlap
  is shorter than the smallest explored minimum. It has no correct lag.

The spike emits `valid`, `ambiguous`, or `invalid`. Energy/overlap rejection,
no eligible lag, a weak primary score, and degenerate numerical evidence emit
`invalid`. An exact equivalent competing maximum, excessive primary-plateau
width, or an insufficient primary/secondary ratio emits `ambiguous`. This
diagnostic split is fixed for the experiment; SPEC-001's normative statement
is that all of these conditions invalidate *automatic alignment*.

`correct_lag` means exact equality between the selected reported integer lag
and `oracle_lag_frames`; M1 has no fractional tolerance. Error counts are:

- `wrong_lag_valid`: oracle `unique`, output `valid`, wrong reported lag.
- `ambiguous_as_valid`: oracle `ambiguous`, output `valid`.
- `invalid_as_valid`: oracle `invalid`, output `valid`.
- `false_valid`: the sum of those three safety failures. The wrong-lag subtype
  is also reported separately.
- `false_ambiguous`: oracle `unique`, output `ambiguous`.
- `false_invalid`: oracle `unique`, output `invalid`.
- `correct_ambiguous` and `correct_invalid`: exact diagnostic matches. A safe
  but mislabeled `ambiguous -> invalid` or `invalid -> ambiguous` remains a
  separate matrix cell and is not called correct.

The global and per-family 3-by-3 classification matrices retain the valid
cell for unique cases, while the separate wrong-lag count prevents that cell
from hiding an incorrect delay.

## Correlation and lag conventions

For local sync lag `q`, the valid baseline-sync interval is

```text
[a, z) = [max(0, -q), min(N_bs, N_cs - q))
```

and only pairs `b_sync[i]`, `c_sync[i + q]` in that interval participate.
There is no score zero-padding. The inclusive search bounds apply after
conversion to the reported full-buffer lag:

```text
l = o_c + q - o_b
q_correct = l_correct + o_b - o_c
```

Positive `l` means that candidate occurs after baseline. At each lag the
float64 accumulations are:

```text
rho = sum(b*c) / sqrt(sum(b^2) * sum(c^2))
rms_b = sqrt(sum(b^2) / overlap_frames)
rms_c = sqrt(sum(c^2) / overlap_frames)
```

A lag is ineligible when `overlap_frames < minimum_overlap_frames` or either
RMS is `<= sync_rms_floor`. Synchronization-copy transforms, if a future case
declares one, operate on new copies. The generated float32 measurement buffers
are digested before and after every estimate and must remain byte-identical.

Selection maximizes `abs(rho)` and returns signed `rho`. Exact score ties use
the smallest `abs(l)`, then the lowest signed `l`, solely as deterministic
diagnostic representation. Any second exactly equivalent global maximum makes
automatic alignment ambiguous even when the accepted ratio is `1.0` or an
exclusion radius would otherwise hide it.

The primary plateau is the integer-contiguous component around the exact
representative maximum whose absolute score difference from the maximum is at
most `plateau_epsilon`. An invalid or missing lag breaks contiguity. Its width
is `maximum_lag - minimum_lag + 1` frames. A local peak is not smaller than its
existing immediate valid neighbors at `l-1` and `l+1`; invalid neighbors are
not skipped. The secondary peak is the largest local peak strictly outside
the inclusive interval formed by expanding the primary plateau by
`secondary_exclusion_radius_frames`. A point at exactly the radius is
excluded; radius plus one is eligible.

The peak ratio is primary score divided by secondary score. No-secondary is
the only positive-infinity state allowed by SPEC-001; JSON records it as a
null numeric value plus `peak_ratio_kind = positive_infinity_no_secondary`.
A zero-valued secondary is recorded as degenerate and rejects alignment rather
than inventing the same infinity state.

## Corpus and leakage controls

Calibration and holdout use different case IDs, generator-family IDs, seeds,
durations, lags, levels, SNR values, synchronization origins, frequencies,
block lengths, and transient locations. Runtime assertions require empty
intersections for case IDs, seeds, generator-family IDs, canonical
generator-parameter digests, and generated PCM-pair digests.

The broad diagnostic strata (polarity, level, lag boundary, noise, low energy,
and overlap) intentionally exist in both splits so their generalization can be
reported. The concrete generator families that populate those strata are
disjoint: for example uniform noise/PRBS in calibration and Rademacher
noise/chirp in holdout. This is the experiment's explicit interpretation of
the acceptance review's disjoint-family requirement and ADR-0005's disjoint
seed/parameter requirement.

The complete deterministic corpus covers broadband noise, PRBS and chirp,
periodic and harmonic signals, repeated blocks, multi-transients, silence and
near-silence, differing durations and sync regions, negative/zero/positive and
search-boundary lags, polarity inversion, level changes, controlled noise,
equivalent separated peaks, and artificial plateaus. Each result records
generator ID/version, seed, canonical parameters, and SHA-256 digests of the
float32 baseline, candidate, and sync copies.

## Bounded sweep and frozen candidates

The sweep is one-factor-at-a-time around the recorded reference. It evaluates
the reference once, then every non-reference value on each of the seven axes.
That is 24 unique OFAT configurations rather than the 25,600-point Cartesian
product. The three named risk profiles were frozen in the input configuration
before holdout execution and are evaluated in addition to the OFAT set.

Ranges are deliberately broad enough to expose boundary behavior:

- `plateau_epsilon`: exact through `1e-3` absolute score difference.
- maximum plateau width: one through eight integer lag frames.
- secondary exclusion radius: zero through 16 frames, below the 128-frame
  inclusive-bound span.
- minimum primary absolute correlation: `0.35` through `0.90`.
- accepted peak ratio: `1.00` through `1.25`.
- RMS floor: zero through `1e-3` linear FS, including near-float32-noise and
  low-audio regions.
- minimum overlap: 16 through 256 frames across short and medium sync slices.

This OFAT design does not estimate every parameter interaction. The three full
candidates exercise coherent permissive, intermediate, and conservative
combinations over all calibration cases. Holdout is never used to invent or
replace a candidate. The evidence presents all three, including failures, and
does not choose a winner.

## Outputs and decision rule

The runner writes full per-case/per-configuration observations under ignored
`artifacts/`. Small deterministic JSON, CSV, Markdown, and SVG summaries may be
published under `docs/evidence/T-CMP-CAL-001/`; lag-score curves and other
large artifacts remain outside source control.

The owner's initial risk rule is applied only as a presentation filter:

1. A candidate is eligible only with zero `false_valid` on deterministic
   holdout, including zero wrong-lag valid cases.
2. Among eligible candidates, compare `false_ambiguous` globally and by
   family.
3. A human chooses the operating point and rationale. FASE A does not update
   SPEC-001 from `Review`.
