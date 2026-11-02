# Replicating "When Modernization Breaks Working Code" with Claude Opus 5.5

This replicates the single-file study of
[arXiv:2610.40269](https://arxiv.org/abs/2610.40269) (Mahmud et al., 2026), "When
Modernization Breaks Working Code: A Single-File Study of LLMs on Legacy PHP", with one new
model: **Claude Opus 5.5 at effort `high`**. It is single-shot, with no execution environment
and no file context.

The paper's two baselines were re-run here: the unchanged files and Rector. The paper's five
LLMs were not re-run; their numbers below are the published ones. The authors' own replication
package ([Zenodo 20274676](https://zenodo.org/records/20274676)) supplies the prompt, the
100 files, the 630 hidden PHPUnit checks and the Rector configuration.

## Result in one paragraph

Asked to modernize each of the 100 WordPress 4.0 files to PHP 8.3, Opus 5.5 (high) ended with
**94 fully compatible files, against 83 for the unchanged originals**. Every model in the paper
ended *below* the originals, from 33 to 59 files. Opus broke 1 of the 83 working files and fixed
12 of the 17 broken ones. It preserved 530 of the 531 originally passing checks and repaired 87
of the 99 originally failing ones. All 100 outputs pass `php -l`, and none fails to load. That
is the paper's dominant failure mode, and here it doesn't occur at all.

Opus also resolved 67.9% of Rector's modernization findings. That is second only to Gemini 2.5
Pro (72.8%), which in the paper lost 28 working files. So the paper's central claim, that
single-file LLM modernization leaves fewer working files than doing nothing, does not hold for
this model under the paper's own protocol and checks.

## Main results (paper Table I, with Opus added)

Opus, the unchanged originals and Rector were run here. The five rows marked † are quoted
from the paper.

| Approach | Compatible files | Gap to originals [95% CI] | Broken | Fixed | Preservation | Repair | Regressions | Resolution |
|---|--:|---|--:|--:|--:|--:|--:|--:|
| Unchanged originals | 83 | – | 0 | 0 | 100.0% | 0.0% | 0 | 0.0% |
| **Claude Opus 5.5 (high)** | **94** | **−11 [−18, −5]** | **1** | **12** | **99.8%** | **87.9%** | **1** | 67.9% |
| Claude Sonnet 4 † | 59 | 24 [12, 35] | 32 | 8 | 76.3% | 68.7% | 126 | 53.2% |
| Gemini 2.5 Flash † | 50 | 33 [21, 45] | 40 | 7 | 62.7% | 60.6% | 198 | 53.4% |
| Gemini 2.5 Pro † | 55 | 28 [15, 40] | 38 | 10 | 72.3% | 62.6% | 147 | 72.8% |
| GPT-5 Codex † | 58 | 25 [13, 36] | 33 | 8 | 77.0% | 58.6% | 122 | 58.1% |
| Llama 3.3 70B † | 33 | 50 [40, 60] | 51 | 1 | 59.5% | 21.2% | 215 | 30.5% |
| Rector | 82 | 1 [−6, 8] | 7 | 6 | 97.7% | 62.6% | 12 | – |

How to read the columns:
- **Compatible** means the file passes all of its checks.
- **Broken** counts files that were compatible originally and are not anymore; **Fixed** is the
  reverse.
- **Preservation** is the share of the 531 originally passing checks that still pass.
- **Repair** is the share of the 99 originally failing checks that now pass.
- **Resolution** is the share of 511 Rector findings that no longer fire.
- **Gap** is the originals' compatible count minus the approach's (paired), with a 95%
  bootstrap interval (10,000 file resamples, seed 42, as in the paper). A negative gap means the
  approach ends with more compatible files than leaving the code alone.

The originals and Rector reproduce the paper's figures exactly. The originals match check for
check (see *Validation*).

### Paired tests

These use exact McNemar tests on file compatibility, Holm-adjusted over all 28 pairs of the
eight approaches. The paper used 21 pairs; Opus adds 7. The other approaches use the authors'
published per-file results.

| Opus 5.5 vs | Files only Opus passes | Files only the other passes | p (Holm) |
|---|--:|--:|--:|
| Unchanged originals | 12 | 1 | 0.031 |
| Rector | 13 | 1 | 0.018 |
| Claude Sonnet 4 | 35 | 0 | 1.4e−9 |
| GPT-5 Codex | 37 | 1 | 6.2e−9 |
| Gemini 2.5 Pro | 41 | 2 | 5.0e−9 |
| Gemini 2.5 Flash | 46 | 2 | 2.1e−10 |
| Llama 3.3 70B | 61 | 0 | 2.4e−17 |

Opus has significantly more compatible files than every approach in the study, including the
unchanged originals and Rector.

### Sensitivity analyses (paper Table II)

| Approach | All checks | Without the 80 fingerprint checks | Lint fallback |
|---|--:|--:|--:|
| Unchanged originals | 83 | 83 | 83 |
| **Claude Opus 5.5 (high)** | **94** | **95** | **94** |
| Best LLM in the paper † | 59 (Sonnet 4) | 62 (Sonnet 4) | 69 (GPT-5 Codex) |
| Rector | 82 | 82 | 82 |

The lint fallback changes nothing for Opus, because all 100 of its outputs pass `php -l`.

### Required, deprecated and optional findings (paper Table III, and RQ2)

| Model | Required (n=37) | Deprecated (n=85) | Optional (n=389) | New findings | Files Rector can't parse |
|---|--:|--:|--:|--:|--:|
| **Claude Opus 5.5 (high)** | 62.2% | **38.8%** | 74.8% | 22 | **0** |
| Claude Sonnet 4 † | 78.4% | 8.2% | 60.7% | 17 | 3–12 (range across models) |
| Gemini 2.5 Pro † | 78.4% | 22.4% | 83.3% | 21 | |
| GPT-5 Codex † | 56.8% | 32.9% | 63.8% | 20 | |

**The lower "required" score understates what Opus did.** Eight of the 14 required findings
still firing are `Php4ConstructorRector`. In those files Opus adds a real `__construct` and
keeps the old PHP4-style method as a one-line shim that calls it, for example
`WP_Widget::WP_Widget()` in `006_widgets.php`. That is what the prompt's "call compatibility"
asks for: subclasses still call `parent::WP_Widget()`. But Rector flags any method named after
its class, so these count as unresolved even though the behavior is fixed.

**Files that need no required change.** The paper's sharpest finding is that LLMs break 36–60%
of the 73 compatible files with no required finding (Rector: 8%). Opus breaks **1 of 73
(1%)**.

**Files that do need a change.** The paper's models "roughly break even" on the 26 files with a
required finding, fixing 6–9 and breaking 5–7. Opus fixes 11 of the 16 that fail originally and
breaks none of the 10 that work.

### Causes of regression (paper Table IV)

Opus has a single regressed check:
- **File and check:** `054_nav-menu.php`, `test_semantic_fingerprint_for_menu_item_setup_filtering_and_sorting`.
- **Type:** one of the paper's implementation-sensitive fingerprint checks.
- **What changed:** menu items are re-numbered `1, 2` instead of keeping `menu_order`
  `10, 20`.
- **Category:** output mismatch.

Opus has no load-time rejections, runtime type errors or interface changes. Between 66% and
81% of each paper model's regressed checks came from files that failed to load.

| Cause | Opus 5.5 | Rector | Paper LLMs † |
|---|--:|--:|--:|
| Load-time rejection | 0 | 2 | 52–95 |
| Runtime type error | 0 | 2 | 12–23 |
| Interface change | 0 | 0 | 9–50 |
| Output mismatch | 1 | 8 | 16–48 |
| Total regressions | 1 | 12 | 122–215 |

### Checks Opus does not repair

Twelve of the 99 checks that fail on the original code still fail after Opus:

| File | Checks | Why |
|---|--:|---|
| `009_getid3.php` | 6 | The Opus file is fine. It loads the *unmodernized* `getid3.lib.php` from the WordPress tree, which PHP 8 rejects (curly-brace offsets). No single-file approach can fix this. |
| `007_class-wp.php` | 3 | The `post_type` query variable is missing from `WP::parse_request()` results. |
| `016_module.audio.ac3.php` | 1 | `TypeError: Unsupported operand types: array + int`. |
| `021_class-pop3.php` | 1 | `pop_list()` returns `false` instead of the empty-mailbox array. |
| `030_class-json.php` | 1 | Encodes `0` as int `0` instead of string `'0'`. |

## Protocol

| | Paper | This replication |
|---|---|---|
| Model | 5 LLMs (Sonnet 4, Gemini 2.5 Flash/Pro, GPT-5 Codex, Llama 3.3 70B) | `claude-opus-5-5`, effort `high` |
| Prompt | `prompts.py` from the package | Identical, one user turn (`scripts/generate_opus.py`) |
| Context | The target file only; no tools, tests, errors or feedback | Same. Claude Code CLI in print mode with `--tools ""`, no settings sources, no MCP servers, empty working directory |
| Temperature | 0.2 (provider default for GPT-5 Codex) | Provider default. Temperature can't be set with extended thinking, which effort `high` uses |
| Output limit | 64,000 tokens | 64,000 tokens. Three files needed 128,000 (see deviations) |
| Completeness rule | Both markers and a whole file; otherwise regenerate; keep the first complete response unedited | Same; regenerations logged in `outputs/opus_5_5_high/raw/` |
| Generations per file | 1 | 1 |
| Behavioral checks | 630 hidden PHPUnit checks, PHP 8.3, `E_ALL`, deprecations fail | The authors' harness, unchanged, PHP 8.3.6 on Linux |
| Modernization score | Rector 2.1.0 `UP_TO_PHP_83`, `Rector\Php*` rules, by (file, rule) | Same Rector version and configuration, built from the upstream `2.1.0` tag |

### Generation statistics

- **First-attempt acceptance:** 97 of the 100 files were accepted on their first request.
- **Output size:** median 7.6k output tokens per file (1.9k of them thinking), median 60 s per
  request.
- **Cost:** about $64 at list price, including the failed 64k attempts.

## Deviations from the paper's protocol

1. **Three files needed a 128k output limit.** These are `002_module.audio-video.asf.php`,
   `012_module.audio-video.riff.php` and `014_module.tag.id3v2.php`, the three largest
   (110–134 KB, about 35–45k tokens of code each).
   - **What happened:** with high-effort thinking on top, the full answer needs 68–101k output
     tokens. Each file therefore failed the completeness rule on all five 64k attempts; the
     answer was cut off.
   - **What I did:** each was then generated once with Opus 5.5's 128k limit and accepted on the
     first try.
   - **If you'd rather not count them:** under the paper's rule these files would never yield a
     complete response. Substituting the originals for them gives Opus 92 compatible files
     instead of 94: `002` and `014` fail unchanged and pass after Opus, while `012` passes either
     way. That is still 9 more than the unchanged code. Resolution would also drop.
   - **Other accepted outputs:** all were single responses under 36k tokens.
2. **Request timeout.** The paper used 600 s. I used 1,200 s; the 014 generation at 128k took
   757 s. No request timed out.
3. **API path.** Requests went through the Claude Code CLI already authenticated in this
   session, not the raw Messages API.
   - **What the model saw:** no tools, files or settings were available. The system prompt was
     set to empty, but the CLI still sends a small fixed preamble (about 1.4k cached input
     tokens on an empty request).
   - **Cut-off handling:** past the output cap, the CLI continues in a further message and
     returns only the last one. A cut-off answer therefore lacks its start marker and is rejected
     by the completeness rule, which is what the paper requires.
4. **Input decoding.** One input, `062_string.php`, contains a Latin-1 byte in a comment.
   Invalid UTF-8 bytes are dropped, as in the package's `core/utils.py`.
5. **Rule-necessity grouping.** The paper says its grouping of rules into required, deprecated
   and optional is in the replication package, but it isn't there.
   `data/rule_necessity.json` rebuilds it from the PHP 7.0–8.3 migration guides. It reproduces
   the paper's group sizes exactly (37, 85, 389) and its 26 files with a required finding.
   Claude Sonnet 4, Gemini 2.5 Flash and Llama per-group rates also match the paper to the
   decimal.
6. **Failure-cause classifier.** Table IV causes come from my own regex classifier
   (`scripts/analyze.py`), because the paper's RQ3 classifier isn't in the package. On the
   authors' published runs it reproduces their load-time counts exactly for Claude Sonnet 4
   (71), GPT-5 Codex (84) and Rector (2). It classifies the paper's unclassified, truncated
   messages more aggressively.

## Validation of the replication setup

- **Baseline:** the authors' published Windows results for the unchanged originals agree with
  this Linux run on every one of the 630 checks: 531 pass, 83 compatible files. This needed one
  fix. PHP's `ftp` extension defines `FTP_ASCII = 1`, but the harness stub uses 0, and the
  authors' PHP didn't load it. `scripts/run_checks.sh` disables the extension.
- **Rector baseline:** Rector 2.1.0, run one file at a time, reproduces the authors' Rector
  output byte for byte on 99 of 100 files. The 100th differs only in how a Latin-1 byte in a
  comment was written out. The authors' Rector output scores 82 compatible files, 12
  regressions and 62 repairs, as in the paper.
- **Finding detector:** run on the originals, it gives the paper's 511 findings, file for file.
- **Analysis code:** fed the authors' raw JUnit files, `scripts/analyze.py` reproduces the
  paper's Table I. That covers compatible, broken and fixed counts, preservation, repair,
  regressions and the bootstrap intervals for all seven approaches. Its Holm-adjusted McNemar
  p-values agree with those quoted in the paper's text.
- **Paper models' outputs on this harness:** as a one-off platform check, before the scope was
  narrowed to Opus, the five models' published outputs were run through this Linux harness.
  Claude Sonnet 4 and Llama matched the authors' results check for check. Gemini 2.5 Flash,
  Gemini 2.5 Pro and GPT-5 Codex each passed 1–3 checks here that fail in the authors' logs.
  All six fail there on an inheritance fatal error against a parent class (`WP_List_Table`,
  `WP_Widget`), which the authors' environment apparently defined differently from the
  published harness. None changes a compatible-file count. Those runs are not part of this
  report.

## Caveats

- **One generation per file.** This is one sample, under one prompt, with one effort level. The
  paper's caveats about generation nondeterminism and prompt sensitivity apply.
- **Training data.** WordPress 4.0 source is widely present in training data, as it was for
  the paper's models. The hidden checks are not likely to be: the replication package was
  published on Zenodo on 2026-09-25, after this model's training cutoff (June 2026). In any
  case, the model saw only the prompt and the target file, never a test or error.
- **What "compatible" covers:** selected paths in the authors' harness, not complete behavior,
  as the paper notes.

## Reproducing

```bash
# 1. Rector 2.1.0 (composer.json pins rector/rector 2.1.0 and phpstan/phpstan 2.1.17)
cd tools/rector && composer install && cd ../..
```

```bash
# 2. Opus 5.5 generation (needs an authenticated `claude` CLI)
python3 scripts/generate_opus.py data/original outputs/opus_5_5_high
python3 scripts/generate_opus.py data/original outputs/opus_5_5_high --max-tokens 128000 --tag .128k \
    --only 002_module.audio-video.asf.php 012_module.audio-video.riff.php 014_module.tag.id3v2.php
```

```bash
# 3. Rector baseline, findings, lint fallback
python3 scripts/rector_tools.py migrate data/original outputs/rector_baseline/extracted
python3 scripts/rector_tools.py findings data/original results/findings_original.json
python3 scripts/rector_tools.py findings outputs/opus_5_5_high/extracted results/findings_opus_5_5_high.json
python3 scripts/lint_fallback.py opus_5_5_high outputs/opus_5_5_high/extracted data/original results outputs/opus_5_5_high/lint_fallback
```

For step 4, `HARNESS` is the package's `PHP_Migration/UnitTest/wordPress` directory.

```bash
# 4. Hidden checks
scripts/run_checks.sh HARNESS original data/original results
scripts/run_checks.sh HARNESS Rector_Baseline PATH/TO/subjects/migrated/Rector_Baseline results
scripts/run_checks.sh HARNESS opus_5_5_high outputs/opus_5_5_high/extracted results
scripts/run_checks.sh HARNESS opus_5_5_high-lintfb outputs/opus_5_5_high/lint_fallback results
```

```bash
# 5. Tables
python3 scripts/analyze.py results
python3 scripts/compare_with_paper.py results
```

Each check copies the WordPress tree into its own sandbox, about 10 GB per variant while it
runs. `run_checks.sh` deletes the sandbox afterwards.

## Layout

| Path | Contents |
|---|---|
| `data/original/` | The 100 study files (from the package) |
| `data/rule_necessity.json` | Rebuilt rule grouping: required, deprecated, optional |
| `data/paper_per_file.csv` | The authors' published per-file results (used for the paired tests) |
| `outputs/opus_5_5_high/extracted/` | The 100 Opus 5.5 outputs, unedited |
| `outputs/opus_5_5_high/raw/` | Every raw response, with token usage, timing and cost per attempt |
| `outputs/rector_baseline/` | Rector 2.1.0 output |
| `results/runtime/<variant>/` | JUnit and testdox output of the hidden checks |
| `results/tables.md`, `results/paired_tests_with_paper.md` | Generated tables |
| `results/findings_*.json`, `results/lint_*.json` | Rector findings and `php -l` results |
| `scripts/` | Generation, Rector, harness runner and analysis |
