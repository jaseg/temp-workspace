#!/usr/bin/env bash
# Download and unpack the test corpora, checking their hashes.
#  - NIST MBE PMI STEP files (public domain): 33 STEP files, 11 test parts by several CAD exporters.
#  - ABC dataset chunk 0000 (Koch et al., CVPR 2019; Onshape public models): 10,000 STEP files;
#    the benchmark uses the 550 listed in abc_sample.txt (500 drawn at random with seed 20261109,
#    plus the 50 largest files, listed in abc_large.txt).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p nist abc
if [ ! -d nist/x ]; then
  curl -sSL -o nist/nist.zip "https://www.nist.gov/document/nist-pmi-step-files"
  echo "8fa78429e6d8d9b0d7681d223b6aa9ec98c3772185c55b1a0e3679b21c181911  nist/nist.zip" | sha256sum -c -
  python3 -I -c "import zipfile; zipfile.ZipFile('nist/nist.zip').extractall('nist/x')"
fi
if [ ! -d abc/x ]; then
  curl -sSL -o abc/abc_0000_step_v00.7z "https://archive.nyu.edu/rest/bitstreams/88598/retrieve"
  echo "52e6dd1b6fa38e3cd99af59b662370829129540030975919c3e256dce6ad1dbe  abc/abc_0000_step_v00.7z" | sha256sum -c -
  7z x -y -bd abc/abc_0000_step_v00.7z -oabc/x @abc_sample.txt
fi
