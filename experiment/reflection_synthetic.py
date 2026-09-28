"""Deterministic synthetic reflection profiles for offline experiments and tests.

Author: Yuxin Jiang
Email: yj546@cornell.edu
"""

from math import isfinite, tanh
from random import Random


def synthetic_profile(positions_um, *, edges_um=(30.0, 70.0), baseline=1.0,
                      amplitude=1.0, noise_std=0.0, transition_um=0.0, seed=0):
    """Return a bright/dark plateau with optional rounded edges and seeded noise.

    This is a numerical fixture, not a physical detector or positioning model.
    """
    left, right = edges_um
    if not all(isfinite(v) for v in (left, right, baseline, amplitude, noise_std, transition_um)):
        raise ValueError("Synthetic parameters must be finite")
    if left >= right or noise_std < 0 or transition_um < 0:
        raise ValueError("Invalid edge order/noise/transition")
    random = Random(seed)
    result = []
    for position in positions_um:
        if not isfinite(position):
            raise ValueError("Positions must be finite")
        if transition_um:
            fraction = (tanh((position - left) / transition_um) - tanh((position - right) / transition_um)) / 2
        else:
            fraction = float(left <= position <= right)
        result.append(baseline + amplitude * fraction + random.gauss(0, noise_std))
    return result
