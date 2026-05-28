"""Tests for the risk-control policy engine."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from decimal import Decimal

from evm_wallet_scanner.policy import (
    CheckResult,
    Policy,
    Violation,
    check,
    load_policy,
)


class TestPolicyPermissiveDefault(unittest.TestCase):
    """No policy file → all trades allowed."""

    def test_no_policy_file_allows_everything(self) -> None:
        pol = load_policy("/nonexistent/path/policy.json")
        result = check(pol, {"amount": "999999", "chain": "ethereum"})
        self.assertTrue(result.allowed)
        self.assertEqual(result.violations, [])

    def test_empty_policy_allows_everything(self) -> None:
        pol = Policy()
        result = check(pol, {"amount": "50000", "chain": "whatever"})
        self.assertTrue(result.allowed)


class TestMaxAmount(unittest.TestCase):
    """max_amount hard limit."""

    def test_under_limit(self) -> None:
        pol = Policy(max_amount=Decimal("1000"))
        result = check(pol, {"amount": "500"})
        self.assertTrue(result.allowed)
        self.assertEqual(result.violations, [])

    def test_at_limit(self) -> None:
        pol = Policy(max_amount=Decimal("1000"))
        result = check(pol, {"amount": "1000"})
        self.assertTrue(result.allowed)

    def test_over_limit(self) -> None:
        pol = Policy(max_amount=Decimal("1000"))
        result = check(pol, {"amount": "1001"})
        self.assertFalse(result.allowed)
        self.assertEqual(len(result.violations), 1)
        self.assertEqual(result.violations[0].rule, "max_amount")


class TestAllowedChains(unittest.TestCase):
    """allowed_chains filter."""

    def test_allowed(self) -> None:
        pol = Policy(allowed_chains=["ethereum", "polygon"])
        result = check(pol, {"chain": "ethereum"})
        self.assertTrue(result.allowed)

    def test_not_allowed(self) -> None:
        pol = Policy(allowed_chains=["ethereum", "polygon"])
        result = check(pol, {"chain": "arbitrum"})
        self.assertFalse(result.allowed)
        self.assertEqual(result.violations[0].rule, "allowed_chains")

    def test_case_insensitive(self) -> None:
        pol = Policy(allowed_chains=["Ethereum"])
        result = check(pol, {"chain": "ethereum"})
        self.assertTrue(result.allowed)


class TestBlacklist(unittest.TestCase):
    """blacklist_addresses hard block."""

    def test_clean_address(self) -> None:
        pol = Policy(blacklist_addresses=["0xbad"])
        result = check(pol, {"sender": "0xgood"})
        self.assertTrue(result.allowed)

    def test_blocked_sender(self) -> None:
        pol = Policy(blacklist_addresses=["0xbad"])
        result = check(pol, {"sender": "0xBAD"})
        self.assertFalse(result.allowed)
        self.assertEqual(result.violations[0].rule, "blacklist_addresses")

    def test_blocked_receiver(self) -> None:
        pol = Policy(blacklist_addresses=["0xbad"])
        result = check(pol, {"receiver": "0xBaD"})
        self.assertFalse(result.allowed)


class TestWhitelist(unittest.TestCase):
    """whitelist_addresses soft warning."""

    def test_in_whitelist(self) -> None:
        pol = Policy(whitelist_addresses=["0xgood"])
        result = check(pol, {"sender": "0xGOOD"})
        self.assertTrue(result.allowed)
        self.assertEqual(result.warnings, [])

    def test_not_in_whitelist_is_warning(self) -> None:
        pol = Policy(whitelist_addresses=["0xgood"])
        result = check(pol, {"sender": "0xunknown"})
        self.assertTrue(result.allowed, "whitelist miss is a warning, not a rejection")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].rule, "whitelist_addresses")


class TestMaxSlippage(unittest.TestCase):
    """max_slippage_bps hard limit."""

    def test_under(self) -> None:
        pol = Policy(max_slippage_bps=50)
        result = check(pol, {"slippage_bps": 30})
        self.assertTrue(result.allowed)

    def test_over(self) -> None:
        pol = Policy(max_slippage_bps=50)
        result = check(pol, {"slippage_bps": 100})
        self.assertFalse(result.allowed)
        self.assertEqual(result.violations[0].rule, "max_slippage_bps")


class TestMaxGasPrice(unittest.TestCase):
    """max_gas_price_gwei soft warning."""

    def test_under(self) -> None:
        pol = Policy(max_gas_price_gwei=Decimal("30"))
        result = check(pol, {"gas_price_gwei": "25"})
        self.assertTrue(result.allowed)
        self.assertEqual(result.warnings, [])

    def test_over_is_warning_not_rejection(self) -> None:
        pol = Policy(max_gas_price_gwei=Decimal("30"))
        result = check(pol, {"gas_price_gwei": "100"})
        self.assertTrue(result.allowed, "gas price warning should not block trade")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.warnings[0].rule, "max_gas_price_gwei")


class TestMultipleViolations(unittest.TestCase):
    """Multiple rules fire at once."""

    def test_amount_and_chain(self) -> None:
        pol = Policy(max_amount=Decimal("100"), allowed_chains=["ethereum"])
        result = check(pol, {"amount": "500", "chain": "avalanche"})
        self.assertFalse(result.allowed)
        rules = {v.rule for v in result.violations}
        self.assertIn("max_amount", rules)
        self.assertIn("allowed_chains", rules)


class TestLoadPolicyFromJSON(unittest.TestCase):
    """Load from a JSON policy file with project overlay."""

    def test_global_and_project(self) -> None:
        data = {
            "global": {
                "max_amount": 1000,
                "allowed_chains": ["ethereum", "polygon"],
            },
            "evm-wallet-scanner": {
                "max_amount": 500,
            },
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        try:
            pol = load_policy(path, project="evm-wallet-scanner")
            self.assertEqual(pol.max_amount, Decimal("500"))
            self.assertEqual(pol.allowed_chains, ["ethereum", "polygon"])

            pol_other = load_policy(path, project="uniswap-autopilot")
            self.assertEqual(pol_other.max_amount, Decimal("1000"))
        finally:
            os.unlink(path)

    def test_env_var_resolution(self) -> None:
        data = {"global": {"max_amount": 200}}
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(data, f)
            f.flush()
            path = f.name

        try:
            os.environ["POLICY_FILE"] = path
            pol = load_policy()
            self.assertEqual(pol.max_amount, Decimal("200"))
        finally:
            os.environ.pop("POLICY_FILE", None)
            os.unlink(path)


class TestCheckResultSerialization(unittest.TestCase):
    """to_dict() produces JSON-serializable output."""

    def test_to_dict(self) -> None:
        result = CheckResult(
            allowed=False,
            violations=[Violation(rule="max_amount", message="too much")],
            warnings=[Violation(rule="whitelist_addresses", message="unknown", severity="warn")],
        )
        d = result.to_dict()
        self.assertFalse(d["allowed"])
        self.assertEqual(len(d["violations"]), 1)
        self.assertEqual(len(d["warnings"]), 1)
        json.dumps(d)


if __name__ == "__main__":
    unittest.main()
