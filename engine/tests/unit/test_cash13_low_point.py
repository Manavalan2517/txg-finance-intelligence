"""HL-7 is the median of the simulated low points (§12.8, B-04), not the mean: a few very bad paths must not drag
the headline figure."""
import numpy as np

from txg.stats.cash13 import median_low_point


def test_the_low_point_is_the_median_of_the_paths_not_the_mean():
    lows = np.array([10.0, 11.0, 12.0, 13.0, -500.0])  # one disastrous path
    assert median_low_point(lows) == 11.0
    assert float(np.mean(lows)) < 0  # the mean would show a crisis the median does not
