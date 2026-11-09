# CAD kernel benchmark: SolidCore (SolidCraft) vs OpenCASCADE (FreeCAD) vs Parasolid (Onshape)

Two questions: how each kernel performs on **complex models**, and how stable it is under
**geometric corner cases**. Test cases come from public libraries, not from this repository.

**Status: in progress.** OCCT results are in; SolidCraft runs are being set up; Parasolid
(through Onshape's API) comes after the first two.

## Kernels

| Kernel | Through | Version |
|---|---|---|
| SolidCore (Rust; based on NVIDIA's SMLib) | `solidcraft-cli` | SolidCraft `b5716d0` (2026-11-09) |
| OpenCASCADE | FreeCAD's Part module (Python, headless) | FreeCAD 1.1.3, OCCT 7.9.3 (conda-forge) |
| Parasolid | Onshape REST API | pending |

## Test libraries

| Library | What it tests | Source |
|---|---|---|
| NIST MBE PMI STEP files | complex real parts (11 parts, 33 files from several exporters) | nist.gov, public domain |
| ABC dataset, chunk 0000 | breadth and odd real-world geometry (550 of 10,000 Onshape models: 500 random, the 50 largest) | Koch et al., CVPR 2019 |
| SolidCraft's kernel cases | corner cases (coincident and tangent faces, near-coaxial cylinders, fillets that consume faces, shells), each with an analytic or invariant answer | `tests/kernel-cases/` in tangency-labs/solidcraft, taken from public issue reports |

The kernel cases are bugs SolidCraft hit and has since fixed, so they are biased in its favour.
Read them as "does the other kernel survive SolidCraft's hard cases", not as a neutral score.

## What is measured

Per STEP model (`harness/occt/occt_model.py`, one process per model, timeout and memory cap):
import, validity check, volume and area, tessellation (chord 1e-3 of the bounding-box diagonal),
then booleans of the largest solid S with T = S moved by 5 % of its diagonal (union, intersection,
difference) and with an exact copy of itself (S ∪ S, S − S).

Boolean results are graded without trusting the kernel under test:

- inclusion-exclusion: V(S∪T) + V(S∩T) = 2V(S) and V(S−T) = V(S) − V(S∩T);
- a Monte Carlo reference for V(S∩T) from point classification against the *input* solid only
  (`harness/occt/ref_mc.py`), which catches results that are wrong but mutually consistent.

Kernel cases (`harness/kernelcases/`): an independent replay of each case's recipe in FreeCAD,
graded against the case's `expected.json`.

## Failure classes

- **Correct refusal**: the expected answer is that the geometry is impossible, and the kernel
  refuses. Counted as a pass.
- **Kernel fault**: a valid answer exists and the kernel errors, crashes, times out, returns an
  invalid shape, or returns a wrong one; or it builds a shape where it should refuse.
- **Bad input**: the imported model already fails the validity check; failures on it are listed
  apart.

## Reproducing

```sh
./setup.sh          # FreeCAD 1.1.3 into tools/, SolidCraft into src/ and its release CLI
corpus/fetch.sh     # NIST and ABC corpora, hash-checked
find corpus/nist/x -iname '*.stp' | sort > /tmp/nist.txt
python3 harness/occt/run_occt.py /tmp/nist.txt results/occt_nist.jsonl --timeout 600
python3 harness/kernelcases/run_cases.py --jobs 4 && python3 harness/kernelcases/build_report.py
```
