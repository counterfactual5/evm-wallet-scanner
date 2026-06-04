"""Tests for evm_wallet_scanner — import checks and mocked RPC tests."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch


class TestImports(unittest.TestCase):
    """Verify all modules import cleanly."""

    def test_import_package(self):
        import evm_wallet_scanner
        # Mirror whatever pyproject claims rather than hard-coding; the
        # version moves faster than this test.
        self.assertRegex(evm_wallet_scanner.__version__, r"^\d+\.\d+\.\d+")

    def test_import_chains(self):
        from evm_wallet_scanner.chains import CHAINS, CHAIN_BY_ID
        self.assertIn("ethereum", CHAINS)
        self.assertEqual(CHAINS["ethereum"].chain_id, 1)
        self.assertEqual(CHAIN_BY_ID[1].key, "ethereum")

    def test_import_common(self):
        from evm_wallet_scanner.common import (
            validate_address,
        )
        self.assertTrue(callable(validate_address))

    def test_import_balances(self):
        from evm_wallet_scanner.balances import balance_main
        self.assertTrue(callable(balance_main))

    def test_import_history(self):
        from evm_wallet_scanner.history import history_main
        self.assertTrue(callable(history_main))

    def test_import_transfer(self):
        from evm_wallet_scanner.transfer import transfer_main
        self.assertTrue(callable(transfer_main))

    def test_import_portfolio(self):
        from evm_wallet_scanner.portfolio import portfolio_main
        self.assertTrue(callable(portfolio_main))

    def test_import_status(self):
        from evm_wallet_scanner.status import tx_status_main
        self.assertTrue(callable(tx_status_main))


class TestChainResolution(unittest.TestCase):
    def test_normalize_chain_case_insensitive(self):
        from evm_wallet_scanner.chains import normalize_chain
        self.assertEqual(normalize_chain("Ethereum").key, "ethereum")
        self.assertEqual(normalize_chain("BASE").key, "base")

    def test_normalize_chain_aliases(self):
        from evm_wallet_scanner.chains import normalize_chain
        self.assertEqual(normalize_chain("eth").key, "ethereum")
        self.assertEqual(normalize_chain("arb").key, "arbitrum")
        self.assertEqual(normalize_chain("op").key, "optimism")

    def test_normalize_chain_unknown_raises(self):
        from evm_wallet_scanner.chains import normalize_chain
        with self.assertRaises(ValueError):
            normalize_chain("unknown_chain")


class TestValidateAddress(unittest.TestCase):
    def test_valid_address(self):
        from evm_wallet_scanner.common import validate_address
        addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
        result = validate_address(addr)
        self.assertEqual(result, addr.lower())

    def test_invalid_address_raises(self):
        from evm_wallet_scanner.common import validate_address
        with self.assertRaises(ValueError):
            validate_address("0xinvalid", "test")

    def test_empty_address_raises(self):
        from evm_wallet_scanner.common import validate_address
        with self.assertRaises(ValueError):
            validate_address("", "test")


class TestFormatUnits(unittest.TestCase):
    def test_zero(self):
        from evm_wallet_scanner.common import format_units
        self.assertEqual(format_units(0, 18), "0")

    def test_one_eth(self):
        from evm_wallet_scanner.common import format_units
        self.assertEqual(format_units(10**18, 18), "1")

    def test_usdc_six_decimals(self):
        from evm_wallet_scanner.common import format_units
        self.assertEqual(format_units(1_000_000, 6), "1")

    def test_fractional(self):
        from evm_wallet_scanner.common import format_units
        self.assertEqual(format_units(5 * 10**17, 18), "0.5")


class TestNormalizeDirection(unittest.TestCase):
    def test_outgoing(self):
        from evm_wallet_scanner.common import normalize_direction
        self.assertEqual(normalize_direction("0xAAA", "0xAAA", "0xBBB"), "out")

    def test_incoming(self):
        from evm_wallet_scanner.common import normalize_direction
        self.assertEqual(normalize_direction("0xBBB", "0xAAA", "0xBBB"), "in")

    def test_self(self):
        from evm_wallet_scanner.common import normalize_direction
        self.assertEqual(normalize_direction("0xAAA", "0xAAA", "0xAAA"), "self")


class TestIsoTimestamp(unittest.TestCase):
    def test_valid_timestamp(self):
        from evm_wallet_scanner.common import iso_from_timestamp
        result = iso_from_timestamp("1609459200")
        self.assertIn("2021", result)

    def test_none_returns_none(self):
        from evm_wallet_scanner.common import iso_from_timestamp
        self.assertIsNone(iso_from_timestamp(None))

    def test_zero_returns_none(self):
        from evm_wallet_scanner.common import iso_from_timestamp
        self.assertIsNone(iso_from_timestamp("0"))


class TestResolveRpcUrl(unittest.TestCase):
    def test_explicit_url(self):
        from evm_wallet_scanner.common import resolve_rpc_url
        url, candidates = resolve_rpc_url("https://example.com", 1)
        self.assertEqual(url, "https://example.com")
        self.assertEqual(candidates, [])

    def test_fallback_to_public_rpc(self):
        from evm_wallet_scanner.common import resolve_rpc_url
        with patch.dict(os.environ, {}, clear=True):
            url, _ = resolve_rpc_url(None, 1)
            self.assertEqual(url, "https://eth.llamarpc.com")

    def test_env_var_preferred(self):
        from evm_wallet_scanner.common import resolve_rpc_url
        with patch.dict(os.environ, {"ETH_RPC_URL": "https://my-rpc.com"}, clear=False):
            url, _ = resolve_rpc_url(None, 1)
            self.assertEqual(url, "https://my-rpc.com")


class TestRpcQueries(unittest.TestCase):
    """Test on-chain query functions with mocked JSON-RPC."""

    @patch("evm_wallet_scanner.common._json_rpc")
    def test_query_native_balance(self, mock_rpc):
        from evm_wallet_scanner.common import query_native_balance
        mock_rpc.return_value = "0xde0b6b3a7640000"  # 1 ETH
        result = query_native_balance("0xAAA", "https://rpc.example.com")
        self.assertEqual(result, 10**18)

    @patch("evm_wallet_scanner.common._json_rpc")
    def test_query_erc20_balance(self, mock_rpc):
        from evm_wallet_scanner.common import query_erc20_balance
        mock_rpc.return_value = "0x00000000000000000000000000000000000000000000000000000000000003e8"  # 1000
        result = query_erc20_balance("0xOWNER", "0xTOKEN", "https://rpc.example.com")
        self.assertEqual(result, 1000)

    @patch("evm_wallet_scanner.common._json_rpc")
    def test_query_gas_price(self, mock_rpc):
        from evm_wallet_scanner.common import query_gas_price
        mock_rpc.return_value = "0x3b9aca00"  # 1 gwei
        result = query_gas_price("https://rpc.example.com")
        self.assertEqual(result, 10**9)

    @patch("evm_wallet_scanner.common._json_rpc")
    def test_estimate_gas(self, mock_rpc):
        from evm_wallet_scanner.common import estimate_transaction_gas
        mock_rpc.return_value = "0x5208"  # 21000
        result = estimate_transaction_gas(
            {"to": "0xBBB", "data": "0x", "value": "0", "from": "0xAAA"},
            "https://rpc.example.com",
        )
        self.assertEqual(result, 21000)


class TestReceiptSucceeded(unittest.TestCase):
    def test_hex_success(self):
        from evm_wallet_scanner.common import receipt_succeeded
        self.assertTrue(receipt_succeeded({"status": "0x1"}))

    def test_int_success(self):
        from evm_wallet_scanner.common import receipt_succeeded
        self.assertTrue(receipt_succeeded({"status": 1}))

    def test_hex_failure(self):
        from evm_wallet_scanner.common import receipt_succeeded
        self.assertFalse(receipt_succeeded({"status": "0x0"}))


class TestEtherscanRequest(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_successful_request(self, mock_urlopen):
        from evm_wallet_scanner.common import etherscan_request
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "status": "1", "message": "OK", "result": [{"hash": "0x123"}],
        }).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = etherscan_request(
            chain_id=1, module="account", action="txlist",
            api_key="test-key",
            extra_params={"address": "0xAAA"},
        )
        self.assertEqual(len(result["result"]), 1)

    @patch("urllib.request.urlopen")
    def test_empty_result(self, mock_urlopen):
        from evm_wallet_scanner.common import etherscan_request
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "status": "0", "message": "No transactions found",
            "result": "No transactions found",
        }).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = etherscan_request(
            chain_id=1, module="account", action="txlist",
            api_key="test-key",
            extra_params={"address": "0xAAA"},
        )
        self.assertEqual(result["result"], [])


class TestTransferNonceHandling(unittest.TestCase):
    """Regression: signer must convert hex-string nonce → int."""

    def test_fetch_pending_nonce_decodes_hex(self):
        from evm_wallet_scanner.transfer.wallet_transfer import _fetch_pending_nonce

        with patch("evm_wallet_scanner.transfer.wallet_transfer._json_rpc") as mock_rpc:
            mock_rpc.return_value = "0x2a"  # 42
            self.assertEqual(_fetch_pending_nonce("0xabc", "https://rpc.example.com"), 42)
            args, _ = mock_rpc.call_args
            self.assertEqual(args[0], "eth_getTransactionCount")
            self.assertEqual(args[1], ["0xabc", "pending"])

    def test_fetch_pending_nonce_accepts_int(self):
        from evm_wallet_scanner.transfer.wallet_transfer import _fetch_pending_nonce

        with patch("evm_wallet_scanner.transfer.wallet_transfer._json_rpc") as mock_rpc:
            mock_rpc.return_value = 7
            self.assertEqual(_fetch_pending_nonce("0xabc", "https://rpc.example.com"), 7)

    def test_fetch_pending_nonce_rejects_invalid(self):
        from evm_wallet_scanner.transfer.wallet_transfer import _fetch_pending_nonce

        with patch("evm_wallet_scanner.transfer.wallet_transfer._json_rpc") as mock_rpc:
            mock_rpc.return_value = None
            with self.assertRaises(RuntimeError):
                _fetch_pending_nonce("0xabc", "https://rpc.example.com")


class TestTransferArgCoercion(unittest.TestCase):
    """Regression: ``transfer_main`` accepts a partial namespace from cli.py."""

    def test_coerce_args_fills_defaults(self):
        from argparse import Namespace
        from evm_wallet_scanner.transfer.wallet_transfer import _coerce_args

        partial = Namespace(chain="ethereum", sender="0xa", receiver="0xb", token="NATIVE")
        coerced = _coerce_args(partial)
        self.assertFalse(coerced.broadcast)
        self.assertIsNone(coerced.confirm)
        self.assertFalse(coerced.send_all)
        self.assertEqual(coerced.receipt_confirmations, 1)


class TestReceiptConfirmations(unittest.TestCase):
    def test_wait_for_transaction_receipt_respects_confirmations(self):
        from evm_wallet_scanner.common import wait_for_transaction_receipt

        with patch("evm_wallet_scanner.common._json_rpc") as mock_rpc, patch("evm_wallet_scanner.common.time.sleep"):
            # First call: eth_getTransactionReceipt -> mined at block 0x10
            # Then two head polls: 0x10 (1 conf) then 0x11 (2 conf) => done for confirmations=2
            mock_rpc.side_effect = [
                {"blockNumber": "0x10", "status": "0x1"},
                "0x10",
                "0x11",
            ]
            receipt = wait_for_transaction_receipt(
                "0xabc",
                "https://rpc.example.com",
                confirmations=2,
                poll_interval=0,
                timeout_seconds=1,
            )
            self.assertEqual(receipt["status"], "0x1")

    def test_wallet_transfer_uses_receipt_confirmations_argument(self):
        from argparse import Namespace
        from evm_wallet_scanner.transfer import wallet_transfer

        args = Namespace(
            chain="ethereum",
            sender="0x1111111111111111111111111111111111111111",
            receiver="0x2222222222222222222222222222222222222222",
            token="NATIVE",
            token_address=None,
            token_decimals=None,
            amount="0.1",
            amount_raw=None,
            send_all=False,
            rpc_url="https://rpc.example.com",
            gas_limit=None,
            gas_price="1",
            private_key="0x" + "11" * 32,
            broadcast=True,
            confirm="TRANSFER ethereum ETH 0.1 TO 0x2222222222222222222222222222222222222222",
            receipt_confirmations=3,
            output=None,
        )

        with (
            patch("evm_wallet_scanner.transfer.wallet_transfer.normalize_chain") as mock_chain,
            patch("evm_wallet_scanner.transfer.wallet_transfer.resolve_rpc_url", return_value=("https://rpc.example.com", [])),
            patch("evm_wallet_scanner.transfer.wallet_transfer.resolve_transfer_token", return_value={"symbol": "ETH", "address": "NATIVE", "decimals": 18}),
            patch("evm_wallet_scanner.transfer.wallet_transfer.query_native_balance", return_value=10**19),
            patch("evm_wallet_scanner.transfer.wallet_transfer.estimate_transaction_gas", return_value=21000),
            patch("evm_wallet_scanner.transfer.wallet_transfer.sign_and_broadcast", return_value={"transactionHash": "0xabc"}),
            patch("evm_wallet_scanner.transfer.wallet_transfer.wait_for_transaction_receipt", return_value={"status": "0x1"}) as mock_wait,
            patch("evm_wallet_scanner.transfer.wallet_transfer.dump_json"),
        ):
            mock_chain.return_value = type("Chain", (), {"key": "ethereum", "chain_id": 1})()
            wallet_transfer.main(args)
            _, kwargs = mock_wait.call_args
            self.assertEqual(kwargs["confirmations"], 3)


class TestPreflightDoctor(unittest.TestCase):
    """Aggregator-level checks for the preflight doctor.

    The individual RPC primitives are covered by ``TestRpcQueries`` and
    ``TestReceiptConfirmations``; here we focus on the aggregation rules:
    skip when inputs missing, severity escalation, and exit-code mapping.
    """

    _GOOD_WALLET = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
    _GOOD_TOKEN = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"  # USDC mainnet
    _GOOD_SPENDER = "0xe592427a0aece92de3edee1f18e0157c05861564"

    def _rpc_side_effect(self, *, chain_id="0x1", native_balance="0xde0b6b3a7640000", nonce="0x5", gas_price="0x3b9aca00", token_balance="0xff", allowance="0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", decimals="0x6", symbol=None):
        # Return a *function* that dispatches on RPC method+selector, so the
        # aggregator can call methods in any order without the test caring.
        def fake(method, params, rpc_url, timeout=30):  # noqa: ARG001
            if method == "eth_blockNumber":
                return "0x1234"
            if method == "eth_chainId":
                return chain_id
            if method == "eth_getBalance":
                return native_balance
            if method == "eth_getTransactionCount":
                return nonce
            if method == "eth_gasPrice":
                return gas_price
            if method == "eth_call":
                data = (params[0].get("data") or "").lower()
                # Normalize away accidental leading '0x' duplication.
                while data.startswith("0x"):
                    data = data[2:]
                if data.startswith("70a08231"):
                    return token_balance
                if data.startswith("dd62ed3e"):
                    return allowance
                if data.startswith("313ce567"):
                    return decimals
                if data.startswith("95d89b41"):
                    return symbol or "0x" + ("00" * 32) + ("00" * 31) + "04" + b"USDC".hex().ljust(64, "0")
            raise AssertionError(f"unexpected RPC call: {method} {params}")
        return fake

    def test_all_ok_when_balances_sufficient(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch("evm_wallet_scanner.common._json_rpc", side_effect=self._rpc_side_effect()):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                    token_address=self._GOOD_TOKEN,
                    spender=self._GOOD_SPENDER,
                    required_allowance_raw=1000,
                    min_native_wei=10**17,
                    min_token_balance_raw=1,
                )

        self.assertTrue(report.ok, msg=json.dumps(report.to_dict(), indent=2))
        names = {c.name: c.status for c in report.checks}
        self.assertEqual(names["rpc_reachable"], "ok")
        self.assertEqual(names["chain_id_matches"], "ok")
        self.assertEqual(names["native_balance"], "ok")
        self.assertEqual(names["pending_nonce"], "ok")
        self.assertEqual(names["gas_price"], "ok")
        self.assertEqual(names["token_balance"], "ok")
        self.assertEqual(names["allowance"], "ok")
        self.assertEqual(names["signer_env"], "ok")

    def test_chain_id_mismatch_fails(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch(
            "evm_wallet_scanner.common._json_rpc",
            side_effect=self._rpc_side_effect(chain_id="0x89"),  # polygon, not ethereum
        ):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                )

        self.assertFalse(report.ok)
        chain_check = next(c for c in report.checks if c.name == "chain_id_matches")
        self.assertEqual(chain_check.status, "fail")
        self.assertEqual(chain_check.details["actualChainId"], 137)
        self.assertEqual(chain_check.details["expectedChainId"], 1)

    def test_zero_native_balance_fails(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch(
            "evm_wallet_scanner.common._json_rpc",
            side_effect=self._rpc_side_effect(native_balance="0x0"),
        ):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                )

        self.assertFalse(report.ok)
        native = next(c for c in report.checks if c.name == "native_balance")
        self.assertEqual(native.status, "fail")

    def test_low_native_balance_warns_but_passes(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch(
            "evm_wallet_scanner.common._json_rpc",
            side_effect=self._rpc_side_effect(native_balance=hex(10**13)),  # 10^13 wei
        ):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                    min_native_wei=10**17,
                )

        self.assertTrue(report.ok)  # warn doesn't trip ok
        native = next(c for c in report.checks if c.name == "native_balance")
        self.assertEqual(native.status, "warn")

    def test_missing_token_skips_token_checks(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch("evm_wallet_scanner.common._json_rpc", side_effect=self._rpc_side_effect()):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                )

        tok = next(c for c in report.checks if c.name == "token_balance")
        allow = next(c for c in report.checks if c.name == "allowance")
        self.assertEqual(tok.status, "skip")
        self.assertEqual(allow.status, "skip")
        self.assertTrue(report.ok)

    def test_no_signer_env_warns(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch("evm_wallet_scanner.common._json_rpc", side_effect=self._rpc_side_effect()):
            with patch.dict(os.environ, {}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                )

        signer = next(c for c in report.checks if c.name == "signer_env")
        self.assertEqual(signer.status, "warn")
        self.assertTrue(report.ok)  # signer is warn, not fail

    def test_insufficient_allowance_fails(self):
        from evm_wallet_scanner.doctor import run_preflight

        with patch(
            "evm_wallet_scanner.common._json_rpc",
            side_effect=self._rpc_side_effect(allowance="0x0"),
        ):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                    token_address=self._GOOD_TOKEN,
                    spender=self._GOOD_SPENDER,
                    required_allowance_raw=1000,
                )

        self.assertFalse(report.ok)
        allow = next(c for c in report.checks if c.name == "allowance")
        self.assertEqual(allow.status, "fail")

    def test_check_exception_recorded_as_error_not_raised(self):
        from evm_wallet_scanner.doctor import run_preflight

        def boom(method, params, rpc_url, timeout=30):  # noqa: ARG001
            raise RuntimeError("rpc dead")

        with patch("evm_wallet_scanner.common._json_rpc", side_effect=boom):
            with patch.dict(os.environ, {}, clear=True):
                report = run_preflight(
                    chain="ethereum",
                    wallet=self._GOOD_WALLET,
                    rpc_url="https://rpc.example.com",
                )

        # Every check that touches RPC should be 'error', the report not ok.
        self.assertFalse(report.ok)
        errors = [c for c in report.checks if c.status == "error"]
        self.assertGreaterEqual(len(errors), 1)

    def test_cli_exit_code_signals_failure(self):
        from evm_wallet_scanner.doctor.cli import doctor_main

        with patch(
            "evm_wallet_scanner.common._json_rpc",
            side_effect=self._rpc_side_effect(chain_id="0x89"),
        ):
            with patch.dict(os.environ, {"HOT_WALLET_PRIVATE_KEY": "0x" + "11" * 32}, clear=True):
                with patch("builtins.print"):
                    code = doctor_main(
                        [
                            "--chain", "ethereum",
                            "--wallet", self._GOOD_WALLET,
                            "--rpc-url", "https://rpc.example.com",
                            "--exit-code",
                        ]
                    )
        self.assertEqual(code, 2)


class TestAuditLog(unittest.TestCase):
    """Schema-stability tests for the audit-log emitter.

    Downstream consumers (jq queries, future ingestion pipeline) depend on the
    record shape being stable. These tests pin the required keys and reject
    unknown event names.
    """

    def test_build_record_has_all_required_keys(self):
        from evm_wallet_scanner.audit import (
            EVENT_BROADCAST,
            REQUIRED_KEYS,
            build_record,
        )

        record = build_record(
            event=EVENT_BROADCAST,
            chain="ethereum",
            wallet="0xabc",
            tx_hash="0xdef",
        )
        for key in REQUIRED_KEYS:
            self.assertIn(key, record, f"missing required key {key}")
        self.assertEqual(record["event"], "broadcast")
        self.assertEqual(record["chain"], "ethereum")
        self.assertEqual(record["wallet"], "0xabc")
        self.assertEqual(record["tx_hash"], "0xdef")
        self.assertEqual(record["details"], {})

    def test_build_record_rejects_unknown_event(self):
        from evm_wallet_scanner.audit import build_record

        with self.assertRaises(ValueError):
            build_record(event="frobnicate")

    def test_run_id_pulled_from_stageforge_env(self):
        from evm_wallet_scanner.audit import EVENT_QUOTE, build_record

        with patch.dict(os.environ, {"STAGEFORGE_RUN_ID": "run-42"}, clear=True):
            record = build_record(event=EVENT_QUOTE)
        self.assertEqual(record["run_id"], "run-42")

    def test_explicit_run_id_wins_over_env(self):
        from evm_wallet_scanner.audit import EVENT_QUOTE, build_record

        with patch.dict(os.environ, {"STAGEFORGE_RUN_ID": "run-42"}, clear=True):
            record = build_record(event=EVENT_QUOTE, run_id="explicit-99")
        self.assertEqual(record["run_id"], "explicit-99")

    def test_emit_writes_to_audit_log_path(self):
        import tempfile

        from evm_wallet_scanner.audit import EVENT_PREFLIGHT, log_event

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "audit.jsonl")
            with patch.dict(os.environ, {"AUDIT_LOG_PATH": log_path}, clear=True):
                log_event(event=EVENT_PREFLIGHT, chain="ethereum", wallet="0xabc")
                log_event(event=EVENT_PREFLIGHT, chain="base", wallet="0xdef")

            with open(log_path, encoding="utf-8") as fh:
                lines = [json.loads(line) for line in fh if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["chain"], "ethereum")
            self.assertEqual(lines[1]["chain"], "base")
            self.assertEqual(lines[0]["event"], "preflight")

    def test_record_is_json_serializable_oneline(self):
        from evm_wallet_scanner.audit import EVENT_BROADCAST, build_record

        record = build_record(
            event=EVENT_BROADCAST,
            chain="ethereum",
            wallet="0xabc",
            tx_hash="0xdef",
            details={"nested": {"key": "value"}, "list": [1, 2, 3]},
        )
        # Serializing as a JSON line must succeed and produce no newlines
        # inside the JSON body.
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        self.assertNotIn("\n", line)
        roundtrip = json.loads(line)
        self.assertEqual(roundtrip["details"]["nested"]["key"], "value")


class TestWalletTransferAuditTrail(unittest.TestCase):
    def test_error_path_emits_audit_event(self):
        from argparse import Namespace
        from evm_wallet_scanner.transfer import wallet_transfer

        emitted: list[dict] = []

        def capture(**kwargs):
            emitted.append(kwargs)
            return kwargs

        args = Namespace(
            chain="ethereum",
            sender="not-a-valid-address",
            receiver="0x2222222222222222222222222222222222222222",
            token="NATIVE",
            amount="0.1",
            broadcast=False,
        )
        with patch("evm_wallet_scanner.transfer.wallet_transfer.log_event", side_effect=capture):
            with self.assertRaises(SystemExit):
                wallet_transfer.main(args)

        self.assertTrue(emitted)
        # The terminal event should be the error.
        self.assertEqual(emitted[-1]["event"], "error")
        self.assertEqual(emitted[-1]["chain"], "ethereum")


if __name__ == "__main__":
    unittest.main()
