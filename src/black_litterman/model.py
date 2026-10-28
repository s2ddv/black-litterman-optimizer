"""Unconstrained Black-Litterman model with Idzorek tilt calibration."""

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class View:
    name: str
    coefficients: dict[str, float]
    expected_return: float
    confidence: float  # fraction, 0..1
    return_type: str = "excess"


@dataclass(frozen=True)
class InputData:
    assets: tuple[str, ...]
    benchmark_weights: np.ndarray
    covariance: np.ndarray
    risk_aversion: float
    tau: float
    risk_free_rate: float
    frequency: str
    views: tuple[View, ...]
    covariance_source: str


@dataclass(frozen=True)
class Result:
    prior_excess: np.ndarray
    posterior_excess: np.ndarray
    weights: np.ndarray
    omega: np.ndarray
    active_views: tuple[View, ...]
    warnings: tuple[str, ...]


def _finite_array(value, name):
    try:
        result = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name}: valores numéricos necessários") from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name}: valores devem ser finitos")
    return result


def load_input(path: str | Path) -> InputData:
    """Read a JSON input. All returns and covariance refer to the same period."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assets = tuple(data["assets"])
    if not assets or any(not isinstance(a, str) or not a for a in assets) or len(set(assets)) != len(assets):
        raise ValueError("assets: nomes não vazios e únicos necessários")
    n = len(assets)
    frequency = data["frequency"]
    if frequency not in ("monthly", "annual"):
        raise ValueError("frequency deve ser monthly ou annual")
    weights = _finite_array(data["benchmark_weights"], "benchmark_weights")
    if weights.shape != (n,) or np.any(weights < 0) or not np.isclose(weights.sum(), 1, atol=1e-8):
        raise ValueError("benchmark_weights: vetor não negativo que soma 1")
    if ("historical_returns" in data) == ("covariance" in data):
        raise ValueError("forneça exatamente um de historical_returns ou covariance")
    if "historical_returns" in data:
        history = _finite_array(data["historical_returns"], "historical_returns")
        if history.ndim != 2 or history.shape[1] != n or history.shape[0] < max(3, n + 1):
            raise ValueError("historical_returns: amostras cronológicas x ativos; pelo menos max(3, N+1) linhas")
        covariance = np.atleast_2d(np.cov(history, rowvar=False, ddof=1))
        source = f"sample covariance (ddof=1; {history.shape[0]} observations)"
    else:
        covariance = _finite_array(data["covariance"], "covariance")
        source = "provided covariance"
    if covariance.shape != (n, n) or not np.allclose(covariance, covariance.T, atol=1e-12):
        raise ValueError("covariance: matriz simétrica N x N necessária")
    if np.linalg.eigvalsh(covariance).min() <= 1e-12:
        raise ValueError("covariance deve ser definida positiva; aumente a amostra ou regularize fora da biblioteca")
    risk_aversion = float(data["risk_aversion"])
    tau = float(data["tau"])
    risk_free_rate = float(data["risk_free_rate"])
    if not all(np.isfinite(x) for x in (risk_aversion, tau, risk_free_rate)) or risk_aversion <= 0 or tau <= 0:
        raise ValueError("risk_aversion e tau devem ser positivos e todos os escalares finitos")
    views = []
    for index, item in enumerate(data.get("views", []), 1):
        name = item.get("name", f"View {index}")
        coeff = item["coefficients"]
        if not isinstance(coeff, dict) or not coeff or any(a not in assets for a in coeff):
            raise ValueError(f"{name}: coefficients devem citar ativos conhecidos")
        row = _finite_array(list(coeff.values()), f"{name}.coefficients")
        if np.allclose(row, 0):
            raise ValueError(f"{name}: opinião sem exposição")
        if not (np.isclose(row.sum(), 0, atol=1e-10) or np.isclose(row.sum(), 1, atol=1e-10)):
            raise ValueError(f"{name}: coeficientes devem somar 0 (relativa) ou 1 (absoluta)")
        return_type = item.get("return_type", "excess")
        if return_type not in ("excess", "total"):
            raise ValueError(f"{name}: return_type deve ser excess ou total")
        expectation = float(item["expected_return"])
        confidence = float(item["confidence"])
        if not np.isfinite(expectation) or not np.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"{name}: retorno finito e confidence entre 0 e 1 necessários")
        views.append(View(str(name), {a: float(v) for a, v in coeff.items()}, expectation, confidence, return_type))
    return InputData(assets, weights, covariance, risk_aversion, tau, risk_free_rate, frequency, tuple(views), source)


def _view_row(view: View, assets: tuple[str, ...]) -> np.ndarray:
    return np.array([view.coefficients.get(a, 0.0) for a in assets])


def _excess_target(view: View, row: np.ndarray, risk_free_rate: float) -> float:
    # For a relative view sum(row)=0, so total and excess spreads coincide.
    return view.expected_return - (risk_free_rate * row.sum() if view.return_type == "total" else 0.0)


def calculate(data: InputData) -> Result:
    """Use formulas (1), (2), (3) and Idzorek's isolated-view tilt calibration."""
    sigma = data.covariance
    prior = data.risk_aversion * sigma @ data.benchmark_weights
    active = tuple(v for v in data.views if v.confidence > 0)
    warnings = []
    if not active:
        return Result(prior, prior.copy(), data.benchmark_weights.copy(), np.empty(0), active, tuple(warnings))
    p = np.vstack([_view_row(v, data.assets) for v in active])
    q = np.array([_excess_target(v, row, data.risk_free_rate) for v, row in zip(active, p)])
    confidence = np.array([v.confidence for v in active])
    # With one view, w(omega)-w_b = [tau*p*Sigma*p'/(tau*p*Sigma*p'+omega)] * (w_100-w_b).
    # Solving the paper's least-squares target exactly yields this diagonal Omega.
    variance = np.einsum("ij,jk,ik->i", p, sigma, p)
    omega = data.tau * variance * (1 - confidence) / confidence
    exact = confidence == 1
    if np.any(exact):
        solution, *_ = np.linalg.lstsq(p[exact], q[exact], rcond=None)
        if not np.allclose(p[exact] @ solution, q[exact], atol=1e-10, rtol=1e-8):
            raise ValueError("opiniões com 100% de confiança são incompatíveis")
    for i in range(len(active)):
        for j in range(i):
            if np.linalg.norm(p[i] - p[j]) < 1e-10 and not np.isclose(q[i], q[j], atol=1e-10):
                warnings.append(f"{active[i].name} e {active[j].name}: opiniões divergentes; resultado é compromisso ponderado pela confiança")
    prior_cov = data.tau * sigma
    system = p @ prior_cov @ p.T + np.diag(omega)
    innovation = q - p @ prior
    # Consistent duplicate exact views can make this singular. Pseudoinverse
    # gives the same posterior as deduplicating those exact observations.
    update = np.linalg.pinv(system, hermitian=True) @ innovation
    posterior = prior + prior_cov @ p.T @ update
    if np.any(exact) and not np.allclose(p[exact] @ posterior, q[exact], atol=1e-9, rtol=1e-8):
        raise ValueError("opiniões exatas não puderam ser satisfeitas numericamente")
    weights = np.linalg.solve(sigma, posterior) / data.risk_aversion
    return Result(prior, posterior, weights, omega, active, tuple(warnings))
