"""Console output for benchmark and research portfolio."""

import argparse
from pathlib import Path

from .model import calculate, load_input


def main() -> None:
    parser = argparse.ArgumentParser(description="Black-Litterman research optimizer")
    parser.add_argument("input", nargs="?", type=Path, default=Path(__file__).resolve().parents[2] / "examples" / "small.json")
    args = parser.parse_args()
    try:
        data = load_input(args.input)
        result = calculate(data)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(2, f"Entrada inválida: {exc}\n")
    print(f"Frequência: {data.frequency}; retorno simples decimal por período")
    print(f"Covariância: {data.covariance_source}; aversão λ={data.risk_aversion:g}; tau={data.tau:g}; livre de risco={data.risk_free_rate:.2%}")
    print("Benchmark = referência de equilíbrio, não posições atuais. Pesos finais sem restrições e sem normalização.")
    print("Ativo                 Equilíbrio exc.  Posterior exc.  Benchmark  Resultado  Mudança pp")
    for name, prior, post, base, final in zip(data.assets, result.prior_excess, result.posterior_excess, data.benchmark_weights, result.weights):
        print(f"{name:<21} {prior:>14.3%} {post:>15.3%} {base:>10.2%} {final:>10.2%} {(final-base)*100:>10.2f}")
    print(f"Soma dos pesos: benchmark={data.benchmark_weights.sum():.2%}; resultado={result.weights.sum():.2%}")
    for view, omega in zip(result.active_views, result.omega):
        row = [view.coefficients.get(asset, 0.0) for asset in data.assets]
        implied = sum(coef * prior for coef, prior in zip(row, result.prior_excess))
        target = view.expected_return - (data.risk_free_rate * sum(row) if view.return_type == "total" else 0)
        direction = "acima" if target > implied else "abaixo" if target < implied else "igual ao"
        print(f"Opinião {view.name}: confiança={view.confidence:.0%}; incerteza ω={omega:.8g}; alvo excedente={target:.3%}, equilíbrio da opinião={implied:.3%} ({direction} equilíbrio)")
    for warning in result.warnings:
        print(f"Aviso: {warning}")


if __name__ == "__main__":
    main()
