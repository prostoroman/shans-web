"""
Mean-variance analytics utilities: min-var, tangency, efficient frontier, placement, rebalance hint.
Pure functions to keep unit-testable.
"""

from __future__ import annotations

from typing import Dict, List, Tuple
import math


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _mv_vol(weights: List[float], cov: List[List[float]]) -> float:
    n = len(weights)
    var = 0.0
    for i in range(n):
        for j in range(n):
            var += weights[i] * weights[j] * cov[i][j]
    return math.sqrt(max(var, 0.0))


def portfolio_point(weights: List[float], means: List[float], cov: List[List[float]]) -> Tuple[float, float]:
    mu = _dot(weights, means)
    sigma = _mv_vol(weights, cov)
    return sigma, mu


def efficient_frontier_sampler(means: List[float], cov: List[List[float]], samples: int = 60) -> List[Dict[str, float]]:
    import random
    n = len(means)
    frontier: List[Dict[str, float]] = []
    for _ in range(samples):
        w = [random.random() for _ in range(n)]
        s = sum(w) or 1.0
        w = [x / s for x in w]
        sigma, mu = portfolio_point(w, means, cov)
        frontier.append({"vol": sigma, "ret": mu})
    frontier.sort(key=lambda x: x["vol"])  # pragmatic ordering for charting
    return frontier


def global_min_variance(cov: List[List[float]]) -> List[float]:
    n = len(cov)
    # Simple heuristic: inverse-variance weights, normalized
    inv_var = [1.0 / cov[i][i] if cov[i][i] > 0 else 0.0 for i in range(n)]
    s = sum(inv_var) or 1.0
    return [x / s for x in inv_var]


def tangency_portfolio(means: List[float], cov: List[List[float]], rf: float) -> List[float]:
    # Heuristic: maximize (mu - rf)/sigma over random samples
    import random
    n = len(means)
    best_w: List[float] = [1.0 / n] * n
    best_sr = float("-inf")
    for _ in range(400):
        w = [random.random() for _ in range(n)]
        s = sum(w) or 1.0
        w = [x / s for x in w]
        sigma, mu = portfolio_point(w, means, cov)
        if sigma > 0:
            sr = (mu - rf) / sigma
            if sr > best_sr:
                best_sr = sr
                best_w = w
    return best_w


def placement_vs_benchmark(weights: List[float], means: List[float], cov: List[List[float]], benchmark_sigma: float, benchmark_mu: float) -> Dict[str, float]:
    sigma, mu = portfolio_point(weights, means, cov)
    return {"portfolio_sigma": sigma, "portfolio_mu": mu, "benchmark_sigma": benchmark_sigma, "benchmark_mu": benchmark_mu}


def rebalance_hint(weights: List[float], corr: List[List[float]]) -> str:
    # Identify the most correlated pair and suggest trimming the larger weight
    n = len(weights)
    max_pair = (0, 1)
    max_corr = -1.0
    for i in range(n):
        for j in range(i + 1, n):
            if corr[i][j] > max_corr:
                max_corr = corr[i][j]
                max_pair = (i, j)
    i, j = max_pair
    target = i if weights[i] >= weights[j] else j
    return "Consider trimming the overweight, highly correlated asset to improve Sharpe."

