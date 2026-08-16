# T-CMP-CAL-001 calibration evidence

- **Phase:** FASE A; human operating-point decision pending
- **SPEC-001 status:** `Review` (unchanged)
- **Source revision:** `7320d057fff64a9fd13f07e963db24328cd01bb7`
- **Dirty at execution:** `false`
- **Configuration SHA-256:** `f065613292b263a4a024d1b724a2be2e7a83d18b622222d560c690517aa25664`
- **Frozen candidate-set SHA-256:** `8c754de0823e06ef9f43cc24e07b168fa8c19ca26c3d19dcf4cbeac7a3e657b2`
- **Curated summary SHA-256:** `92c8baf2081741fc969b0c8ecc233399b7af4eae5d7911b3052672a41d8727c0`
- **Ignored full raw result SHA-256:** `173056eb1550ba46f9fb98387b578315dcf7fb27719c4a2198fedfa6051d822e`

The labels, formulas, tie/plateau/exclusion rules, error definitions,
sweep bounds, and leakage interpretation were frozen in
[`T-CMP-CAL-001-method.md`](../../calibration/T-CMP-CAL-001-method.md)
before evaluating holdout. No production comparator is included.

## Reproduction

```text
python tools/alignment_calibration.py --config configs/calibration/t_cmp_cal_001.json --output artifacts/t_cmp_cal_001
```

The command writes full lag observations under ignored `artifacts/`.
The checked-in summary omits those large curves but records their run digest.

## Corpus separation

Calibration cases: 28; holdout cases: 28.
Case IDs, seeds, concrete generator families, canonical parameter digests,
and generated PCM-pair digests have empty calibration/holdout intersections.
See `cases.csv` and `summary.json` for the recorded generator provenance.

## Frozen operating-point candidates

| Candidate | Split | False-valid | Wrong-lag valid | False-ambiguous | False-invalid | Matrix |
|---|---|---:|---:|---:|---:|---|
| OP-A-permissive | calibration | 0 | 0 | 0 | 1 | unique: V=18 A=0 I=1; ambiguous: V=0 A=5 I=0; invalid: V=0 A=0 I=4 |
| OP-A-permissive | holdout | 1 | 1 | 0 | 0 | unique: V=15 A=0 I=0; ambiguous: V=0 A=8 I=0; invalid: V=0 A=0 I=5 |
| OP-B-intermediate | calibration | 0 | 0 | 0 | 1 | unique: V=18 A=0 I=1; ambiguous: V=0 A=5 I=0; invalid: V=0 A=0 I=4 |
| OP-B-intermediate | holdout | 0 | 0 | 0 | 1 | unique: V=14 A=0 I=1; ambiguous: V=0 A=8 I=0; invalid: V=0 A=0 I=5 |
| OP-C-conservative | calibration | 0 | 0 | 0 | 2 | unique: V=17 A=0 I=2; ambiguous: V=0 A=5 I=0; invalid: V=0 A=0 I=4 |
| OP-C-conservative | holdout | 0 | 0 | 0 | 2 | unique: V=13 A=0 I=2; ambiguous: V=0 A=8 I=0; invalid: V=0 A=0 I=5 |

`false_valid` includes ambiguous-as-valid, invalid-as-valid, and wrong-lag
valid outcomes. It is therefore the safety count used by the owner's initial
zero-false-valid holdout criterion.

![Candidate tradeoff](tradeoff.svg)

## Holdout results by family

| Candidate | Family | Cases | False-valid | Wrong-lag | False-ambiguous | False-invalid | Correct ambiguous | Correct invalid |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| OP-A-permissive | harmonic-comb-v1 | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| OP-A-permissive | integer-chirp-v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| OP-A-permissive | near-silence-v1 | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| OP-A-permissive | rademacher-noise-v1 | 11 | 1 | 1 | 0 | 0 | 0 | 0 |
| OP-A-permissive | repeated-block-v1 | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| OP-A-permissive | short-sync-offset-v1 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| OP-A-permissive | tapered-plateau-v1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 |
| OP-B-intermediate | harmonic-comb-v1 | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| OP-B-intermediate | integer-chirp-v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | near-silence-v1 | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| OP-B-intermediate | rademacher-noise-v1 | 11 | 0 | 0 | 0 | 1 | 0 | 0 |
| OP-B-intermediate | repeated-block-v1 | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| OP-B-intermediate | short-sync-offset-v1 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| OP-B-intermediate | tapered-plateau-v1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 |
| OP-C-conservative | harmonic-comb-v1 | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| OP-C-conservative | integer-chirp-v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| OP-C-conservative | near-silence-v1 | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| OP-C-conservative | rademacher-noise-v1 | 11 | 0 | 0 | 0 | 2 | 0 | 0 |
| OP-C-conservative | repeated-block-v1 | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| OP-C-conservative | short-sync-offset-v1 | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| OP-C-conservative | tapered-plateau-v1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 |

## Parameters and tradeoffs

### OP-A-permissive

Preserve more unique low-level/noisy alignments while rejecting exact ties.

- `plateau_epsilon=1e-06` unitless absolute score difference
- `maximum_primary_plateau_width_frames=4` frames
- `secondary_exclusion_radius_frames=2` frames
- `minimum_primary_abs_correlation=0.35` unitless
- `minimum_accepted_peak_ratio=1.05` unitless
- `sync_rms_floor_linear_fs=1e-07` linear FS RMS
- `minimum_overlap_frames=32` frames
- Holdout: false-valid=1, false-ambiguous=0, false-invalid=0.

### OP-B-intermediate

Middle profile for ambiguity rejection and usable low-level evidence.

- `plateau_epsilon=1e-05` unitless absolute score difference
- `maximum_primary_plateau_width_frames=2` frames
- `secondary_exclusion_radius_frames=4` frames
- `minimum_primary_abs_correlation=0.5` unitless
- `minimum_accepted_peak_ratio=1.1` unitless
- `sync_rms_floor_linear_fs=1e-05` linear FS RMS
- `minimum_overlap_frames=64` frames
- Holdout: false-valid=0, false-ambiguous=0, false-invalid=1.

### OP-C-conservative

Reject weak, broad, or moderately competing evidence at higher false-ambiguous risk.

- `plateau_epsilon=0.0001` unitless absolute score difference
- `maximum_primary_plateau_width_frames=1` frames
- `secondary_exclusion_radius_frames=8` frames
- `minimum_primary_abs_correlation=0.7` unitless
- `minimum_accepted_peak_ratio=1.25` unitless
- `sync_rms_floor_linear_fs=0.001` linear FS RMS
- `minimum_overlap_frames=128` frames
- Holdout: false-valid=0, false-ambiguous=0, false-invalid=2.

## Holdout sensitivity strata

| Candidate | Factor | Category | Cases | False-valid | Wrong-lag | False-ambiguous | False-invalid |
|---|---|---|---:|---:|---:|---:|---:|
| OP-A-permissive | polarity | inverted | 2 | 0 | 0 | 0 | 0 |
| OP-A-permissive | polarity | normal | 26 | 1 | 1 | 0 | 0 |
| OP-A-permissive | level | low | 7 | 0 | 0 | 0 | 0 |
| OP-A-permissive | level | near_silence | 3 | 0 | 0 | 0 | 0 |
| OP-A-permissive | level | nominal | 17 | 1 | 1 | 0 | 0 |
| OP-A-permissive | level | very_low | 1 | 0 | 0 | 0 | 0 |
| OP-A-permissive | lag_position | lower_boundary | 2 | 0 | 0 | 0 | 0 |
| OP-A-permissive | lag_position | negative | 3 | 0 | 0 | 0 | 0 |
| OP-A-permissive | lag_position | not_applicable | 13 | 0 | 0 | 0 | 0 |
| OP-A-permissive | lag_position | positive | 7 | 1 | 1 | 0 | 0 |
| OP-A-permissive | lag_position | upper_boundary | 2 | 0 | 0 | 0 | 0 |
| OP-A-permissive | lag_position | zero | 1 | 0 | 0 | 0 | 0 |
| OP-A-permissive | noise | high_snr | 1 | 0 | 0 | 0 | 0 |
| OP-A-permissive | noise | low_snr | 1 | 0 | 0 | 0 | 0 |
| OP-A-permissive | noise | medium_snr | 1 | 0 | 0 | 0 | 0 |
| OP-A-permissive | noise | none | 25 | 1 | 1 | 0 | 0 |
| OP-A-permissive | energy | active | 25 | 1 | 1 | 0 | 0 |
| OP-A-permissive | energy | near_silence | 3 | 0 | 0 | 0 | 0 |
| OP-A-permissive | overlap | normal | 26 | 1 | 1 | 0 | 0 |
| OP-A-permissive | overlap | short | 2 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | polarity | inverted | 2 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | polarity | normal | 26 | 0 | 0 | 0 | 1 |
| OP-B-intermediate | level | low | 7 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | level | near_silence | 3 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | level | nominal | 17 | 0 | 0 | 0 | 1 |
| OP-B-intermediate | level | very_low | 1 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | lag_position | lower_boundary | 2 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | lag_position | negative | 3 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | lag_position | not_applicable | 13 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | lag_position | positive | 7 | 0 | 0 | 0 | 1 |
| OP-B-intermediate | lag_position | upper_boundary | 2 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | lag_position | zero | 1 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | noise | high_snr | 1 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | noise | low_snr | 1 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | noise | medium_snr | 1 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | noise | none | 25 | 0 | 0 | 0 | 1 |
| OP-B-intermediate | energy | active | 25 | 0 | 0 | 0 | 1 |
| OP-B-intermediate | energy | near_silence | 3 | 0 | 0 | 0 | 0 |
| OP-B-intermediate | overlap | normal | 26 | 0 | 0 | 0 | 1 |
| OP-B-intermediate | overlap | short | 2 | 0 | 0 | 0 | 0 |
| OP-C-conservative | polarity | inverted | 2 | 0 | 0 | 0 | 0 |
| OP-C-conservative | polarity | normal | 26 | 0 | 0 | 0 | 2 |
| OP-C-conservative | level | low | 7 | 0 | 0 | 0 | 0 |
| OP-C-conservative | level | near_silence | 3 | 0 | 0 | 0 | 0 |
| OP-C-conservative | level | nominal | 17 | 0 | 0 | 0 | 1 |
| OP-C-conservative | level | very_low | 1 | 0 | 0 | 0 | 1 |
| OP-C-conservative | lag_position | lower_boundary | 2 | 0 | 0 | 0 | 0 |
| OP-C-conservative | lag_position | negative | 3 | 0 | 0 | 0 | 1 |
| OP-C-conservative | lag_position | not_applicable | 13 | 0 | 0 | 0 | 0 |
| OP-C-conservative | lag_position | positive | 7 | 0 | 0 | 0 | 1 |
| OP-C-conservative | lag_position | upper_boundary | 2 | 0 | 0 | 0 | 0 |
| OP-C-conservative | lag_position | zero | 1 | 0 | 0 | 0 | 0 |
| OP-C-conservative | noise | high_snr | 1 | 0 | 0 | 0 | 0 |
| OP-C-conservative | noise | low_snr | 1 | 0 | 0 | 0 | 0 |
| OP-C-conservative | noise | medium_snr | 1 | 0 | 0 | 0 | 0 |
| OP-C-conservative | noise | none | 25 | 0 | 0 | 0 | 2 |
| OP-C-conservative | energy | active | 25 | 0 | 0 | 0 | 2 |
| OP-C-conservative | energy | near_silence | 3 | 0 | 0 | 0 | 0 |
| OP-C-conservative | overlap | normal | 26 | 0 | 0 | 0 | 2 |
| OP-C-conservative | overlap | short | 2 | 0 | 0 | 0 | 0 |

## Sensitivity and limitations

`summary.json` records candidate sensitivity strata for polarity, level, lag
position/boundary, noise, energy, overlap, sync origins, and duration. Positive
gain and polarity should not change `abs(rho)` except through sign or RMS-floor
crossings; the evidence tests those invariants rather than claiming sensitivity
where the normalized metric has none.

This deterministic corpus demonstrates known-case coverage; it does not estimate
a population error rate. OFAT does not cover all parameter interactions, variants
from one construction are correlated, and reusing this holdout after changing a
candidate would turn it into tuning data. Large per-lag score observations remain
outside source control.

## Decision required

No candidate is selected automatically. The owner must apply the stated risk
criterion, review family-level behavior, and explicitly choose an operating point
before FASE B may record rationale or change SPEC-001 from `Review`.
