"""Small helpers: number formatting, natural sorting, component values."""

import re


def f2(v):
    return f'{v:.3f}'.rstrip('0').rstrip('.') or '0'


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


# ----------------------------------------------------------------------------
# Component values

SI = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'μ': 1e-6, 'm': 1e-3, '': 1,
      'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9, 'R': 1, 'r': 1}
VALUE = re.compile(r'^\s*(\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([pnuµμmkKMGRr]?)(\d*)')


def parse_si(s):
    """Parse component values: '100n', '100 nF', '0.1uF', '4u7', '4.7µF', '1e-7', '22u/6V3',
    '3k3', '10k 1%' ... Returns None for anything else ('?', 'DNP', 'C')."""
    m = VALUE.match(s or '')
    if not m:
        return None
    num, unit, frac = m.groups()
    if frac:
        if '.' in num or 'e' in num.lower():
            return None
        num = f'{num}.{frac}'
    return float(num) * SI[unit]
