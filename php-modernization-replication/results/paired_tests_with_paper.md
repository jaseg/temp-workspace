# Opus 5.5 against the paper's approaches (file-level, paired)

| Approach | Compatible | Gap to originals [95% CI] |
|---|--:|---|
| Unchanged originals | 83 | -- |
| Claude Sonnet 4 | 59 | 24 [12, 35] |
| Gemini 2.5 Flash | 50 | 33 [21, 45] |
| Gemini 2.5 Pro | 55 | 28 [15, 40] |
| GPT-5 Codex | 58 | 25 [13, 36] |
| Llama 3.3 70B | 33 | 50 [40, 60] |
| Rector | 82 | 1 [-6, 8] |
| Claude Opus 5.5 (high) | 94 | -11 [-18, -5] |

Exact McNemar, Holm-adjusted over all 28 pairs; pairs with Opus:

| Opus 5.5 vs | Opus better only | Other better only | p (Holm) |
|---|--:|--:|--:|
| Unchanged originals | 12 | 1 | 0.031 |
| Claude Sonnet 4 | 35 | 0 | 1.4e-09 |
| Gemini 2.5 Flash | 46 | 2 | 2.1e-10 |
| Gemini 2.5 Pro | 41 | 2 | 5e-09 |
| GPT-5 Codex | 37 | 1 | 6.2e-09 |
| Llama 3.3 70B | 61 | 0 | 2.4e-17 |
| Rector | 13 | 1 | 0.018 |
