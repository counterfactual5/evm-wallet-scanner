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


class TestDoctorPolicyFlag(unittest.TestCase):
    """`evm-scan doctor --policy` evaluates the policy file against the context."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        policy_data = {"evm-wallet-scanner": {"max_amount": 100, "allowed_chains": ["ethereum"]}}
        self._policy_path = os.path.join(self._tmpdir.name, "policy.json")
        with open(self._policy_path, "w", encoding="utf-8") as fh:
            json.dump(policy_data, fh)
        self._out_path = os.path.join(self._tmpdir.name, "report.json")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _fake_report(self):
        from evm_wallet_scanner.doctor.preflight import PreflightCheck, PreflightReport

        return PreflightReport(
            ok=True,
            chain="ethereum",
            chain_id=1,
            wallet="0xabc",
            rpc_url="https://rpc.example.com",
            checks=[PreflightCheck(name="rpc_reachable", status="ok", summary="ok")],
            started_at=0.0,
            finished_at=0.1,
        )

    def test_policy_rejects_over_limit(self) -> None:
        from unittest.mock import patch

        from evm_wallet_scanner.doctor.cli import doctor_main

        argv = [
            "--chain", "ethereum", "--wallet", "0xabc",
            "--policy", "--policy-file", self._policy_path,
            "--amount", "500", "--output", self._out_path,
            "--exit-code",
        ]
        with patch("evm_wallet_scanner.doctor.cli.run_preflight", return_value=self._fake_report()):
            rc = doctor_main(argv)

        with open(self._out_path, encoding="utf-8") as fh:
            payload = json.load(fh)

        self.assertIn("policy", payload)
        self.assertTrue(payload["policy"]["loaded"])
        self.assertFalse(payload["policy"]["allowed"])
        self.assertEqual(rc, 2, "policy rejection should drive exit code 2")

    def test_policy_allows_within_limit(self) -> None:
        from unittest.mock import patch

        from evm_wallet_scanner.doctor.cli import doctor_main

        argv = [
            "--chain", "ethereum", "--wallet", "0xabc",
            "--policy", "--policy-file", self._policy_path,
            "--amount", "10", "--output", self._out_path,
        ]
        with patch("evm_wallet_scanner.doctor.cli.run_preflight", return_value=self._fake_report()):
            doctor_main(argv)

        with open(self._out_path, encoding="utf-8") as fh:
            payload = json.load(fh)

        self.assertTrue(payload["policy"]["allowed"])
        self.assertEqual(payload["policy"]["violations"], [])


class TestPolicyGateE2E(unittest.TestCase):
    """End-to-end: a real policy file loaded through wallet_transfer.main blocks
    a transfer over the limit and never reaches sign_and_broadcast."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["STAGEFORGE_STATE_DIR"] = self._tmpdir.name
        self.run_id = "policy-gate-e2e-001"

        # Policy file that rejects any transfer above 0.05.
        policy_data = {"evm-wallet-scanner": {"max_amount": 0.05}}
        self._policy_path = os.path.join(self._tmpdir.name, "policy.json")
        with open(self._policy_path, "w", encoding="utf-8") as fh:
            json.dump(policy_data, fh)

        os.environ["POLICY_FILE"] = self._policy_path
        os.environ["AUDIT_RUN_ID"] = self.run_id

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        os.environ.pop("STAGEFORGE_STATE_DIR", None)
        os.environ.pop("POLICY_FILE", None)
        os.environ.pop("AUDIT_RUN_ID", None)

    def test_over_limit_transfer_blocked_before_broadcast(self) -> None:
        from argparse import Namespace
        from unittest.mock import patch

        from evm_wallet_scanner import state_machine

        args = Namespace(
            chain="ethereum",
            sender="0x1111111111111111111111111111111111111111",
            receiver="0x2222222222222222222222222222222222222222",
            token="NATIVE",
            token_address=None,
            token_decimals=None,
            amount="0.1",  # exceeds policy max_amount 0.05
            amount_raw=None,
            send_all=False,
            rpc_url="https://rpc.example.com",
            gas_limit=None,
            gas_price="1",
            private_key="0x" + "11" * 32,
            broadcast=True,
            confirm="TRANSFER ethereum ETH 0.1 TO 0x2222222222222222222222222222222222222222",
            receipt_confirmations=1,
            output=None,
        )

        with (
            patch("evm_wallet_scanner.transfer.wallet_transfer.normalize_chain") as mock_chain,
            patch("evm_wallet_scanner.transfer.wallet_transfer.resolve_rpc_url",
                  return_value=("https://rpc.example.com", [])),
            patch("evm_wallet_scanner.transfer.wallet_transfer.resolve_transfer_token",
                  return_value={"symbol": "ETH", "address": "NATIVE", "decimals": 18}),
            patch("evm_wallet_scanner.transfer.wallet_transfer.query_native_balance",
                  return_value=10**19),
            patch("evm_wallet_scanner.transfer.wallet_transfer.estimate_transaction_gas",
                  return_value=21000),
            patch("evm_wallet_scanner.transfer.wallet_transfer.sign_and_broadcast") as mock_broadcast,
            patch("evm_wallet_scanner.transfer.wallet_transfer.dump_json"),
            patch("evm_wallet_scanner.transfer.wallet_transfer.capture_balances",
                  return_value={"senderNative": 10**19, "receiverNative": 0,
                                "senderAsset": 10**19, "receiverAsset": 0}),
        ):
            mock_chain.return_value = type("Chain", (), {"key": "ethereum", "chain_id": 1})()
            from evm_wallet_scanner.transfer import wallet_transfer

            # main() catches the RuntimeError and exits non-zero.
            with self.assertRaises(SystemExit):
                wallet_transfer.main(args)

            mock_broadcast.assert_not_called()

        # State machine should have recorded the rejection as terminal FAILED.
        state = state_machine.load_state(self.run_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["current_state"], state_machine.STATE_FAILED)


if __name__ == "__main__":
    unittest.main()
