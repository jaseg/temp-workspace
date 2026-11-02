# Results (100 files, 630 checks, 511 findings)

## Table I: behavioural compatibility and resolution

| Approach | Compatible | Gap [95% CI] | Broken | Fixed | Preservation | Repair | Regressions | Resolution |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| Unchanged originals | 83 | -- | 0 | 0 | 100.0% | 0.0% | 0 | 0.0% |
| Claude Opus 5.5 (high) | 94 | -11 [-18, -5] | 1 | 12 | 99.8% | 87.9% | 1 | 67.9% |
| Rector | 82 | 1 [-6, 8] | 7 | 6 | 97.7% | 62.6% | 12 | -- |

Checks passing on the originals: 531 of 630.

## Table II: compatible files under the sensitivity analyses

| Approach | All checks | No fingerprint | Lint fallback |
|---|--:|--:|--:|
| Unchanged originals | 83 | 83 | 83 |
| Claude Opus 5.5 (high) | 94 | 95 | 94 |
| Rector | 82 | 82 | 82 |

## Table III: resolution by necessity (required n=37, deprecated n=85, optional n=389)

| Model | Required | Deprecated | Optional | New | Unparseable files |
|---|--:|--:|--:|--:|--:|
| Claude Opus 5.5 (high) | 62.2% | 38.8% | 74.8% | 22 | 0 |

## Files with / without a required finding (26 files with one)

| Approach | Fixed (req.) | Broken (req.) | Broken (no req.) / compatible no-req. | Fixed (no req.) |
|---|--:|--:|--:|--:|
| Claude Opus 5.5 (high) | 11 | 0 | 1 / 73 (1%) | 1 |
| Rector | 6 | 1 | 6 / 73 (8%) | 0 |

## Table IV: regression causes (checks)

| Cause | Claude Opus 5.5 (high) | Rector |
|---|--:|--:|
| Load-time rejection | 0 | 2 |
| Runtime type error | 0 | 2 |
| Interface change | 0 | 0 |
| Output mismatch | 1 | 8 |
| Other | 0 | 0 |
| Unclassified | 0 | 0 |
| Total regressions | 1 | 12 |
| Files with regressions | 1 | 9 |
| ... with load-time rejection | 0 | 2 |

## Pairwise exact McNemar on file compatibility (Holm over 3 pairs)

| A | B | compatible A | compatible B | p | p (Holm) |
|---|---|--:|--:|--:|--:|
| Claude Opus 5.5 (high) | Rector | 94 | 82 | 0.0018 | 0.0055 |
| Unchanged originals | Claude Opus 5.5 (high) | 83 | 94 | 0.0034 | 0.0068 |
| Unchanged originals | Rector | 83 | 82 | 1 | 1 |
