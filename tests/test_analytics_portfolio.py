from apps.analytics.portfolio import (
    global_min_variance,
    tangency_portfolio,
    portfolio_point,
    efficient_frontier_sampler,
    placement_vs_benchmark,
    rebalance_hint,
)


def test_min_var_and_tangency():
    means = [0.08, 0.06, 0.10]
    cov = [
        [0.04, 0.01, 0.015],
        [0.01, 0.03, 0.012],
        [0.015, 0.012, 0.05],
    ]
    w_min = global_min_variance(cov)
    assert abs(sum(w_min) - 1.0) < 1e-6
    w_tan = tangency_portfolio(means, cov, 0.02)
    assert abs(sum(w_tan) - 1.0) < 1e-6
    sigma, mu = portfolio_point(w_min, means, cov)
    assert sigma >= 0


def test_frontier_and_placement():
    means = [0.08, 0.06]
    cov = [
        [0.04, 0.01],
        [0.01, 0.03],
    ]
    fr = efficient_frontier_sampler(means, cov, 10)
    assert len(fr) == 10
    w = [0.5, 0.5]
    place = placement_vs_benchmark(w, means, cov, benchmark_sigma=0.15, benchmark_mu=0.07)
    assert set(place.keys()) == {"portfolio_sigma", "portfolio_mu", "benchmark_sigma", "benchmark_mu"}


def test_rebalance_hint():
    corr = [
        [1.0, 0.9, 0.2],
        [0.9, 1.0, 0.1],
        [0.2, 0.1, 1.0],
    ]
    msg = rebalance_hint([0.6, 0.3, 0.1], corr)
    assert isinstance(msg, str) and msg

