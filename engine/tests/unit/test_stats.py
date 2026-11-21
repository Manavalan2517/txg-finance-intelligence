"""Task C2: normal ranges, signals, the false-alarm limit, ranking and statuses (§10.3–§10.4, §12.2–§12.4)."""
from decimal import Decimal

import pytest

from txg.stats.fdr import SignalTest, benjamini_hochberg
from txg.stats.rank import rank_signals
from txg.stats.status import Status, level_status, trend
from txg.stats.xmr import normal_range, signal_p


def test_normal_range_is_xmr_on_the_baseline_excluding_the_latest_three():
    series = [10.0] * 21 + [12.0, 10.0, 12.0] + [30.0, 30.0, 30.0]  # 24 baseline points, then 3 latest
    nr = normal_range(series)
    assert nr.n == 24
    assert nr.centre == pytest.approx(sum(series[:24]) / 24)
    mr = [abs(a - b) for a, b in zip(series[1:24], series[:23])]
    assert nr.mr_bar == pytest.approx(sum(mr) / len(mr))
    assert nr.upper == pytest.approx(nr.centre + 2.66 * nr.mr_bar)
    assert nr.lower == pytest.approx(nr.centre - 2.66 * nr.mr_bar)


def test_normal_range_needs_twelve_baseline_months():
    assert normal_range([1.0] * 14) is None          # only 11 baseline points before the latest 3
    assert normal_range([1.0] * 15).n == 12


def test_rule_a_p_value_is_one_sided_normal_tail():
    series = [10.0, 11.0] * 12 + [10.5, 10.5, 30.0]
    nr = normal_range(series)
    p, rule = signal_p(series, nr, bad_side="high")
    assert rule == "A" and p < 0.001


def test_rule_b_eight_points_one_side_has_p_of_one_in_256():
    series = [10.0, 11.0] * 12 + [10.0, 11.0, 10.0] + [10.6] * 8
    nr = normal_range(series[:27] + [10.6] * 3)
    p, rule = signal_p(series, nr, bad_side="high")
    assert rule == "B" and p == pytest.approx(0.5 ** 8)


def test_no_signal_on_the_good_side_counts_for_bad_side_tests():
    series = [10.0, 11.0] * 12 + [10.5, 10.5, -10.0]
    p, _ = signal_p(series, normal_range(series), bad_side="high")
    assert p == 1.0


def test_false_alarm_limit_hand_example():
    """§18.2: 1,000 tests; the five smallest p are 0.00002, 0.0001, 0.0002, 0.004, 0.02 → keep 3 at q = 10%."""
    small = [0.00002, 0.0001, 0.0002, 0.004, 0.02]
    tests = [SignalTest(f"t{i}", p) for i, p in enumerate(small)] + \
            [SignalTest(f"n{i}", 0.5) for i in range(995)]
    kept, suppressed = benjamini_hochberg(tests, q=0.10)
    assert [t.test_id for t in kept] == ["t0", "t1", "t2"]
    assert len(suppressed) == 997
    assert all(t.reason == "false-alarm limit" for t in suppressed if t.test_id in {"t3", "t4"})
    assert kept[0].q_value == pytest.approx(0.00002 * 1000 / 1)


def test_ranking_is_by_riyals_at_stake_weighted_by_confidence():
    from txg.stats.rank import Candidate
    cands = [Candidate("a", q_value=0.05, impact_sar=Decimal(1_000_000), distance=1.0),
             Candidate("b", q_value=0.50, impact_sar=Decimal(3_000_000), distance=2.0),
             Candidate("c", q_value=0.01, impact_sar=Decimal(100_000), distance=3.0)]
    ranked = rank_signals(cands, materiality=Decimal(250_000))
    assert [c.signal_id for c in ranked.attention] == ["b", "a"]
    assert [c.signal_id for c in ranked.below_materiality] == ["c"]


@pytest.mark.parametrize(("value", "expected"), [(0.5, Status.HEALTHY), (1.05, Status.WATCH), (0.9, Status.ACT)])
def test_hurdle_status_with_watch_tolerance(value, expected):
    """Book-to-bill hurdle 1.0: act below 0.95, watch below 1.10 (configured tolerances)."""
    yardstick = {"type": "hurdle", "hurdle": 1.0, "act_below": 0.95, "watch_below": 1.10, "direction": "higher_better"}
    assert level_status(value if value != 0.5 else 1.2, yardstick, history=[]) == expected


def test_own_normal_act_needs_three_bad_months_in_a_row():
    yardstick = {"type": "own_normal", "direction": "lower_better"}
    base = [10.0, 11.0] * 12
    assert level_status(10.5, yardstick, history=base + [10.5, 10.5]) == Status.HEALTHY
    assert level_status(20.0, yardstick, history=base + [10.5, 10.5]) == Status.WATCH
    assert level_status(20.0, yardstick, history=base + [20.0, 20.0]) == Status.ACT


def test_trend_from_kept_signals():
    assert trend(kept_bad=True, kept_good=False) == "slipping"
    assert trend(kept_bad=False, kept_good=True) == "improving"
    assert trend(kept_bad=False, kept_good=False) == "steady"


def test_group_trends_keep_only_signals_inside_the_false_alarm_limit():
    """§12.3 worked example: 1,000 tests, five smallest p-values 0.00002, 0.0001, 0.0002, 0.004, 0.02 → keep 3.
    A per-reading threshold (p < 0.01) would also keep the fourth."""
    from txg.stats.fdr import group_trends

    small = [0.00002, 0.0001, 0.0002, 0.004, 0.02]
    tests = {("EH-01", f"K{i}"): (small[i] if i < 5 else 0.5, 0.5) for i in range(500)}  # 500 KPIs × 2 sides
    trends = group_trends(tests)
    assert [trends[("EH-01", f"K{i}")] for i in range(5)] == ["slipping", "slipping", "slipping", "steady", "steady"]
    assert trends[("EH-01", "K7")] == "steady"


def test_group_trends_report_a_good_side_signal_as_improving():
    from txg.stats.fdr import group_trends

    trends = group_trends({("EH-01", "A"): (0.9, 0.00001), ("EH-02", "A"): (0.4, 0.6)})
    assert trends == {("EH-01", "A"): "improving", ("EH-02", "A"): "steady"}


def test_a_rolling_12_month_measure_keeps_its_false_alarm_rate_near_nominal_with_lag_12_ranges():
    """Margins are 12-month figures: consecutive values share 11 months, so month-to-month moving ranges understate
    the variation and quiet companies breach their limits. Ranges at the window's lag (non-overlapping windows) keep
    the XmR false-alarm rate close to the 2.66 limits' nominal level (about 1%)."""
    import random

    from txg.stats.xmr import normal_range
    rng = random.Random(7)
    hits_lag1 = hits_lag12 = trials = 0
    for _ in range(400):
        monthly = [0.08 + rng.gauss(0, 0.01) for _ in range(12 + 27)]
        rolling = [sum(monthly[i - 12:i]) / 12 for i in range(12, len(monthly))]
        for window, counter in ((1, "lag1"), (12, "lag12")):
            nr = normal_range(rolling, window=window)
            hit = not (nr.lower <= rolling[-1] <= nr.upper)
            if counter == "lag1":
                hits_lag1 += hit
            else:
                hits_lag12 += hit
        trials += 1
    assert hits_lag1 / trials > 0.15       # the old limits: well over one false alarm in seven quiet months
    assert hits_lag12 / trials < 0.05      # lag-12 ranges: close to nominal
