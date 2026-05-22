"""Wallet overview — query native + known token balances for a wallet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evm_wallet_scanner.chains import CHAINS, normalize_chain
from evm_wallet_scanner.common import build_balance_entry, dump_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Query native and known token balances for a wallet")
    parser.add_argument("--chain", required=True, help="chain key such as base / ethereum / arbitrum")
    parser.add_argument("--wallet", required=True, help="wallet address")
    parser.add_argument(
        "--token",
        action="append",
        dest="tokens",
        help="restrict the query to specific token symbols/addresses; repeatable",
    )
    parser.add_argument("--include-zero", action="store_true", help="include zero-balance assets")
    parser.add_argument("--rpc-url", help="explicit RPC URL")
    parser.add_argument("--output", help="write full JSON output to a file")
    args = parser.parse_args()

    try:
        chain = normalize_chain(args.chain)
        requested_tokens = list(args.tokens or [])
        if not requested_tokens:
            requested_tokens = ["NATIVE"]

        entries = []
        for token_name in requested_tokens:
            entry = build_balance_entry(
                chain_name=chain.key,
                wallet=args.wallet,
                token_name=token_name,
                token_decimals=None,
                explicit_rpc_url=args.rpc_url,
            )
            if args.include_zero or int(entry["rawBalance"]) > 0:
                entries.append(entry)

        response = {
            "action": "wallet_overview",
            "chain": {"key": chain.key, "chainId": chain.chain_id},
            "wallet": args.wallet,
            "assets": entries,
            "assetCount": len(entries),
            "knownAssetUniverse": len(requested_tokens),
        }
        if args.output:
            Path(args.output).write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        dump_json(response)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
