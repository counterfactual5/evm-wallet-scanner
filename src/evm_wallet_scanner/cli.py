"""Unified CLI entry point — zero dependencies (argparse, stdlib only).

Usage:
    evm-scan balance --chain ethereum --wallet 0x...
    evm-scan multichain --wallet 0x...
    evm-scan history --chain ethereum --wallet 0x...
"""

from __future__ import annotations

import argparse
import sys

from evm_wallet_scanner import __version__
from evm_wallet_scanner.balances import balance_main, multichain_main, overview_main
from evm_wallet_scanner.history import counterparties_main, history_main, transfer_report_main
from evm_wallet_scanner.portfolio import gas_report_main, portfolio_main
from evm_wallet_scanner.status import tx_status_main
from evm_wallet_scanner.transfer import transfer_main

# ── shared helpers ──────────────────────────────────────────────────────────


def _add_rpc_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--rpc-url", help="Override RPC URL")
    parser.add_argument("--output", help="Write JSON output to file")


def _add_chain_wallet(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--chain", required=True, help="Chain key (ethereum, base, arbitrum, optimism, polygon)")
    parser.add_argument("--wallet", required=True, help="Wallet address (0x...)")


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="evm-scan",
        description="EVM Wallet Scanner — balances, history, portfolio, gas reports.",
    )
    parser.add_argument("--version", action="version", version=f"evm-scan {__version__}")

    sub = parser.add_subparsers(dest="command")

    # ── balance ──
    p = sub.add_parser("balance", help="Query native or ERC20 balance")
    _add_chain_wallet(p)
    p.add_argument("--token", help="Token symbol, address, or NATIVE (omit for native)")
    p.add_argument("--token-decimals", type=int, help="Override token decimals")
    _add_rpc_output(p)
    p.set_defaults(func=lambda a: balance_main())

    # ── overview ──
    p = sub.add_parser("overview", help="Native + known ERC20 balances")
    _add_chain_wallet(p)
    p.add_argument("--token", action="append", dest="tokens", help="Additional token to query")
    p.add_argument("--include-zero", action="store_true")
    _add_rpc_output(p)
    p.set_defaults(func=lambda a: overview_main())

    # ── multichain ──
    p = sub.add_parser("multichain", help="Portfolio across all chains")
    p.add_argument("--wallet", required=True, help="Wallet address")
    p.add_argument("--chain", action="append", dest="chains", help="Limit to specific chain(s)")
    p.add_argument("--token", action="append", dest="tokens", help="Additional tokens")
    p.add_argument("--include-zero", action="store_true")
    p.add_argument("--output", help="Write JSON output to file")
    p.set_defaults(func=lambda a: multichain_main())

    # ── history ──
    p = sub.add_parser("history", help="Transaction history")
    _add_chain_wallet(p)
    p.add_argument("--kind", action="append", choices=["normal", "internal", "erc20"])
    p.add_argument("--contract-address", help="Filter ERC20 by token")
    p.add_argument("--start-block", default="0")
    p.add_argument("--end-block", default="9999999999")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--offset", type=int, default=20)
    p.add_argument("--sort", choices=["asc", "desc"], default="desc")
    p.add_argument("--output", help="Write JSON output to file")
    p.set_defaults(func=lambda a: history_main())

    # ── transfer-report ──
    p = sub.add_parser("transfer-report", help="ERC20 transfer report")
    _add_chain_wallet(p)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--contract-address", help="Filter by token contract")
    p.add_argument("--output", help="Write JSON output to file")
    p.set_defaults(func=lambda a: transfer_report_main())

    # ── counterparties ──
    p = sub.add_parser("counterparties", help="Find related addresses")
    _add_chain_wallet(p)
    p.add_argument("--min-interactions", type=int, default=1)
    p.add_argument("--include-known-contracts", action="store_true")
    p.add_argument("--exclude-erc20", action="store_true")
    p.add_argument("--exclude-internal", action="store_true")
    p.add_argument("--output", help="Write JSON output to file")
    p.set_defaults(func=lambda a: counterparties_main())

    # ── portfolio ──
    p = sub.add_parser("portfolio", help="Estimate wallet value")
    _add_chain_wallet(p)
    p.add_argument("--include-zero", action="store_true")
    _add_rpc_output(p)
    p.set_defaults(func=lambda a: portfolio_main())

    # ── gas-report ──
    p = sub.add_parser("gas-report", help="Gas spend analysis")
    _add_chain_wallet(p)
    p.add_argument("--start-block", default="0")
    p.add_argument("--end-block", default="9999999999")
    p.add_argument("--output", help="Write JSON output to file")
    p.set_defaults(func=lambda a: gas_report_main())

    # ── tx-status ──
    p = sub.add_parser("tx-status", help="Check transaction status")
    p.add_argument("--chain", required=True, help="Chain key")
    p.add_argument("--tx-hash", required=True, help="Transaction hash")
    _add_rpc_output(p)
    p.set_defaults(func=lambda a: tx_status_main())

    # ── transfer ──
    # Mirror the full surface of ``evm_wallet_scanner.transfer.wallet_transfer``
    # so the orchestrator can drive --broadcast / --confirm without users
    # being told to call a second CLI. ``dry-run`` is the implicit default
    # because broadcasting requires both ``--broadcast`` and ``--confirm``.
    p = sub.add_parser("transfer", help="Send native or ERC20 tokens (dry-run by default)")
    p.add_argument("--chain", required=True, help="Chain key")
    p.add_argument("--from", dest="sender", required=True, help="Sender address")
    p.add_argument("--to", dest="receiver", required=True, help="Receiver address")
    p.add_argument("--token", default="NATIVE", help="NATIVE or ERC20 symbol/address")
    p.add_argument("--token-address", help="Arbitrary ERC20 address")
    p.add_argument("--token-decimals", type=int)
    amount_group = p.add_mutually_exclusive_group(required=False)
    amount_group.add_argument("--amount", help="Human-readable amount (e.g. 0.01)")
    amount_group.add_argument("--amount-raw", help="Raw uint256 amount")
    amount_group.add_argument("--send-all", action="store_true", help="Send the entire balance")
    p.add_argument("--gas-limit", help="Gas limit override")
    p.add_argument("--gas-price", help="Gas price in wei")
    p.add_argument("--private-key", help="Signer private key (prefer env var)")
    p.add_argument("--broadcast", action="store_true", help="Actually broadcast (otherwise dry-run)")
    p.add_argument("--confirm", help="Must match the confirmation phrase to broadcast")
    p.add_argument("--receipt-confirmations", type=int, default=1)
    p.add_argument("--rpc-url", help="Override RPC URL")
    p.add_argument("--output", help="Write JSON output to file")
    p.set_defaults(func=lambda a: transfer_main(a))

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
