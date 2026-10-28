import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from black_litterman import calculate, load_input


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "small.json"


def from_dict(document):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return load_input(path)


class ModelTests(unittest.TestCase):
    def test_no_views_recovers_benchmark(self):
        doc = json.loads(EXAMPLE.read_text())
        doc["views"] = []
        data = from_dict(doc)
        result = calculate(data)
        np.testing.assert_allclose(result.prior_excess, data.risk_aversion * data.covariance @ data.benchmark_weights)
        np.testing.assert_allclose(result.weights, data.benchmark_weights)

    def test_idzorek_confidence_interpolates_isolated_weight_tilt(self):
        doc = json.loads(EXAMPLE.read_text())
        doc["views"] = [doc["views"][0]]
        base = from_dict(doc)
        doc["views"][0]["confidence"] = 1.0
        full = calculate(from_dict(doc))
        for confidence in (0.0, 0.25, 0.6, 1.0):
            doc["views"][0]["confidence"] = confidence
            result = calculate(from_dict(doc))
            np.testing.assert_allclose(result.weights - base.benchmark_weights,
                                       confidence * (full.weights - base.benchmark_weights), atol=1e-10)

    def test_absolute_total_converts_to_excess_and_exact_view_is_satisfied(self):
        doc = json.loads(EXAMPLE.read_text())
        doc["views"] = [doc["views"][1]]
        doc["views"][0]["confidence"] = 1.0
        data = from_dict(doc)
        result = calculate(data)
        self.assertAlmostEqual(result.posterior_excess[2], doc["views"][0]["expected_return"] - doc["risk_free_rate"])
        self.assertAlmostEqual(result.omega[0], 0)

    def test_conflicting_exact_views_rejected(self):
        doc = json.loads(EXAMPLE.read_text())
        doc["views"] = [
            {"coefficients": {"Titulos": 1}, "expected_return": 0.01, "confidence": 1},
            {"coefficients": {"Titulos": 1}, "expected_return": 0.02, "confidence": 1},
        ]
        with self.assertRaisesRegex(ValueError, "incompatíveis"):
            calculate(from_dict(doc))

    def test_finite_conflict_gives_warning_and_finite_result(self):
        doc = json.loads(EXAMPLE.read_text())
        doc["views"] = [
            {"coefficients": {"Titulos": 1}, "expected_return": 0.01, "confidence": 0.5},
            {"coefficients": {"Titulos": 1}, "expected_return": 0.02, "confidence": 0.5},
        ]
        result = calculate(from_dict(doc))
        self.assertTrue(result.warnings)
        self.assertTrue(np.isfinite(result.weights).all())

    def test_bad_covariance_rejected(self):
        doc = json.loads(EXAMPLE.read_text())
        del doc["historical_returns"]
        doc["covariance"] = [[1, 0, 0], [0, 0, 0], [0, 0, 1]]
        with self.assertRaisesRegex(ValueError, "definida positiva"):
            from_dict(doc)

    def test_tau_scaling_does_not_change_posterior_with_idzorek_omega(self):
        doc = json.loads(EXAMPLE.read_text())
        first = calculate(from_dict(doc))
        doc["tau"] = 0.4
        second = calculate(from_dict(doc))
        np.testing.assert_allclose(first.posterior_excess, second.posterior_excess, atol=1e-12)
        np.testing.assert_allclose(first.weights, second.weights, atol=1e-10)
        np.testing.assert_allclose(second.omega, first.omega * 8, atol=1e-12)

    def test_idzorek_table_1_equilibrium_example(self):
        # Idzorek (2004 draft), Tables 1, 2 and 5: eight-asset rounded
        # covariance and market-cap weights; lambda is approximately 3.07.
        covariance = [
            [.001005,.001328,-.000579,-.000675,.000121,.000128,-.000445,-.000437],
            [.001328,.007277,-.001307,-.000610,-.002237,-.000989,.001442,-.001535],
            [-.000579,-.001307,.059852,.027588,.063497,.023036,.032967,.048039],
            [-.000675,-.000610,.027588,.029609,.026572,.021465,.020697,.029854],
            [.000121,-.002237,.063497,.026572,.102488,.042744,.039943,.065994],
            [.000128,-.000989,.023036,.021465,.042744,.032056,.019881,.032235],
            [-.000445,.001442,.032967,.020697,.039943,.019881,.028355,.035064],
            [-.000437,-.001535,.048039,.029854,.065994,.032235,.035064,.079958],
        ]
        doc = {"assets": [f"Asset{i}" for i in range(8)], "frequency": "annual",
               "covariance": covariance,
               "benchmark_weights": [.1934,.2613,.1209,.1209,.0134,.0134,.2418,.0349],
               "risk_aversion": 3.07, "tau": .025, "risk_free_rate": 0, "views": []}
        data = from_dict(doc)
        result = calculate(data)
        # Table 1 publishes 2-decimal percentage returns; input values are rounded too.
        published = np.array([.0008,.0067,.0641,.0408,.0743,.0370,.0480,.0660])
        np.testing.assert_allclose(result.prior_excess, published, atol=0.0002)
        np.testing.assert_allclose(result.weights, data.benchmark_weights, atol=1e-10)


if __name__ == "__main__":
    unittest.main()
