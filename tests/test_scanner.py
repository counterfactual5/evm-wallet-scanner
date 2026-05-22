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
        self.assertEqual(evm_wallet_scanner.__version__, "0.1.0")

    def test_import_chains(self):
        from evm_wallet_scanner.chains import CHAINS, CHAIN_BY_ID, normalize_chain
        self.assertIn("ethereum", CHAINS)
        self.assertEqual(CHAINS["ethereum"].chain_id, 1)
        self.assertEqual(CHAIN_BY_ID[1].key, "ethereum")

    def test_import_common(self):
        from evm_wallet_scanner.common import (
            validate_address,
            format_units,
            normalize_direction,
            resolve_rpc_url,
            dump_json,
            iso_from_timestamp,
        )
        self.assertTrue(callable(validate_address))

    def test_import_balances(self):
        from evm_wallet_scanner.balances import balance_main, overview_main, multichain_main
        self.assertTrue(callable(balance_main))

    def test_import_history(self):
        from evm_wallet_scanner.history import history_main, transfer_report_main, counterparties_main
        self.assertTrue(callable(history_main))

    def test_import_transfer(self):
        from evm_wallet_scanner.transfer import transfer_main
        self.assertTrue(callable(transfer_main))

    def test_import_portfolio(self):
        from evm_wallet_scanner.portfolio import portfolio_main, gas_report_main
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


if __name__ == "__main__":
    unittest.main()
