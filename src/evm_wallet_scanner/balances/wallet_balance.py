"""Balance query — single token or native balance for a wallet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evm_wallet_scanner.common import build_balance_entry, dump_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Query native or ERC20 balance for a wallet")
    parser.add_argument("--chain", required=True, help="chain key such as base / ethereum / arbitrum")
    parser.add_argument("--wallet", required=True, help="wallet address")
    parser.add_argument("--token", help="token symbol, token address, or NATIVE; omit for native balance")
    parser.add_argument("--token-decimals", type=int, help="override token decimals when token is an address")
    parser.add_argument("--rpc-url", help="explicit RPC URL")
    parser.add_argument("--output", help="write full JSON output to a file")
    args = parser.parse_args()

    try:
        response = {
            "action": "wallet_balance",
            **build_balance_entry(
                chain_name=args.chain,
                wallet=args.wallet,
                token_name=args.token,
                token_decimals=args.token_decimals,
                explicit_rpc_url=args.rpc_url,
            ),
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
