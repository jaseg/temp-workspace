"""Single-shot PHP 8.3 modernization of the 100 study files with Claude Opus 5.5 (effort: high).

Replicates the generation protocol of arXiv:2610.40269 (Sec. III-B):
- the authors' prompt (prompts.py, BASIC_PROMPT_TEMPLATE) verbatim, as one user turn,
- the complete target file and nothing else (no tools, no other files, no feedback),
- up to 64,000 output tokens; one request per file,
- a response is complete if it has both markers and was not cut off; incomplete
  responses are regenerated and the first complete one is kept unedited.

Requests go through the Claude Code CLI in print mode with every tool disabled, no
settings sources, no MCP servers and an empty working directory, so the model sees only
the prompt. Usage: generate_opus.py SUBJECTS_DIR OUT_DIR [--jobs N]
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODEL = "claude-opus-5-5"
EFFORT = "high"
MAX_OUTPUT_TOKENS = 64000  # (paper: 64,000)
TIMEOUT_S = 1200  # (paper: 600 s per request; doubled for high-effort thinking on long files)
MAX_ATTEMPTS = 5

# Verbatim from the replication package's prompts.py.
PROMPT = """You are a senior PHP developer with expertise in legacy code modernization.
Your task is to migrate this legacy PHP code up to PHP 8.3 standards while preserving functional equivalence. Preserve observable behavior,
including inputs, outputs, side effects, and call compatibility.


Please migrate the following PHP code up to PHP 8.3 standards:

{code}

Your response should follow this EXACT format:

// MIGRATION_START
[your migrated PHP code here]
// MIGRATION_END

CRITICAL FORMATTING REQUIREMENT:
- Place the MIGRATION_START marker BEFORE the opening <?php tag
- Place the MIGRATION_END marker AFTER the closing PHP code
- Do NOT place these markers inside the PHP code itself

Provide only the migrated PHP code with the markers placed correctly outside the PHP code block, no additional commentary."""

# Same extraction as the package's core/parser.py (both markers required here).
START_RE = re.compile(r"//\s*MIGRATION_START\s*\n", re.IGNORECASE)
END_RE = re.compile(r"\n//\s*MIGRATION_END", re.IGNORECASE)


def extract(text):
    s, e = START_RE.search(text), END_RE.search(text)
    if not (s and e) or e.start() < s.end():
        return None
    return text[s.end() : e.start()].strip()


def call_model(prompt, workdir, max_tokens=MAX_OUTPUT_TOKENS):
    env = dict(os.environ)
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_tokens)
    for k in ("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "MAX_THINKING_TOKENS"):
        env.pop(k, None)
    cmd = [
        "claude", "-p",
        "--model", MODEL,
        "--effort", EFFORT,
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--system-prompt", "",
        "--output-format", "json",
    ]  # fmt: skip
    p = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, cwd=workdir, env=env, timeout=TIMEOUT_S
    )
    return json.loads(p.stdout)


def migrate(src, out_dir, raw_dir, max_tokens=MAX_OUTPUT_TOKENS, tag=""):
    out_file = out_dir / src.name
    meta_file = raw_dir / (src.stem + tag + ".json")
    if out_file.exists() and meta_file.exists():
        return src.name, "cached"
    # (decoded like the package's core/utils.py: invalid UTF-8 bytes dropped)
    prompt = PROMPT.format(code=src.read_text(encoding="utf-8", errors="ignore"))
    attempts = []
    with tempfile.TemporaryDirectory() as wd:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            t0 = time.time()
            try:
                res = call_model(prompt, wd, max_tokens)
            except subprocess.TimeoutExpired:
                attempts.append({"attempt": attempt, "status": "timeout", "secs": time.time() - t0})
                continue
            except json.JSONDecodeError as exc:
                attempts.append({"attempt": attempt, "status": f"bad cli output: {exc}"})
                continue
            text = res.get("result") or ""
            code = extract(text)
            rec = {
                "attempt": attempt,
                "secs": round(time.time() - t0, 1),
                "stop_reason": res.get("stop_reason"),
                "is_error": res.get("is_error"),
                "usage": res.get("usage"),
                "model_usage": res.get("modelUsage"),
                "cost_usd": res.get("total_cost_usd"),
            }
            # Past the output cap the CLI continues in a further message and `result` holds
            # only the last one, so a cut-off answer lacks MIGRATION_START and fails here.
            complete = (
                not res.get("is_error") and res.get("stop_reason") == "end_turn" and bool(code)
            )
            rec["status"] = "complete" if complete else "incomplete"
            attempts.append(rec)
            (raw_dir / f"{src.stem}{tag}.attempt{attempt}.txt").write_text(text, encoding="utf-8")
            if complete:
                out_file.write_text(code + "\n", encoding="utf-8")
                break
    meta_file.write_text(json.dumps({"file": src.name, "attempts": attempts}, indent=1))
    return src.name, attempts[-1]["status"] if attempts else "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subjects", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--max-tokens", type=int, default=MAX_OUTPUT_TOKENS)
    ap.add_argument("--tag", default="", help="suffix for raw/ logs of a rerun")
    a = ap.parse_args()
    out_dir, raw_dir = a.out / "extracted", a.out / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(a.subjects.glob("[0-9][0-9][0-9]_*.php"))
    if a.only:
        files = [f for f in files if f.name in a.only]
    # Largest first so the long requests overlap.
    files.sort(key=lambda f: -f.stat().st_size)
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for name, status in ex.map(lambda f: migrate(f, out_dir, raw_dir, a.max_tokens, a.tag), files):
            print(f"{name}: {status}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
