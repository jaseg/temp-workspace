#!/usr/bin/env python3
"""Stitch the PNG tiles written by finish.js:  python stitch.py out.png"""
import json
import os
import sys

from PIL import Image

out = sys.argv[1]
meta = json.load(open(out + '.tiles.json'))
img = Image.new('RGB', (meta['width'], meta['height']), 'white')
for t in meta['tiles']:
    with Image.open(t['file']) as tile:
        img.paste(tile.convert('RGB'), (t['tx'], t['ty']))
    os.remove(t['file'])
os.remove(out + '.tiles.json')
img.save(out, optimize=True)
print(f'wrote {out} {img.size}')
