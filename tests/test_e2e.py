from e2e_test import run_e2e


def test_live_polymarket_e2e() -> None:
    payload = run_e2e()
    assert payload["status"] == "E2E Passed: 5 markets, 2+ decisions, no timeouts"
