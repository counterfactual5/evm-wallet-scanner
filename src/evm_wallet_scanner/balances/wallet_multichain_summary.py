"""Multi-chain wallet asset summary.

Query native and common token balances across multiple chains in one call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evm_wallet_scanner.chains import normalize_chain
from evm_wallet_scanner.common import build_balance_entry, dump_json

DEFAULT_CHAINS = ["ethereum", "base", "arbitrum", "optimism", "polygon"]

DEFAULT_TOKENS = [
    "USDC",
    "WETH",
    "USDT",
    "DAI",
    "WBTC",
    "UNI",
    "LINK",
    "AAVE",
    "ARB",
    "OP",
]


def format_balance(raw: str, decimals: int, min_significant: int = 8) -> str:
    """Format a raw balance with enough significant digits."""
    try:
        raw_int = int(raw)
        if raw_int == 0:
            return "0"
        sign = "-" if raw_int < 0 else ""
        scale = 10 ** decimals
        absolute = abs(raw_int)
        integer_part = absolute // scale
        fractional_part = absolute % scale
        if fractional_part == 0:
            return f"{sign}{integer_part}"
        fractional_text = f"{fractional_part:0{decimals}d}".rstrip("0")
        if len(fractional_text) < min_significant:
            fractional_text = fractional_text.ljust(min_significant, "0")
        return f"{sign}{integer_part}.{fractional_text}"
    except (ValueError, ZeroDivisionError):
        return "0"


def query_chain_assets(
    chain_name: str,
    wallet: str,
    tokens: list[str],
    include_zero: bool = False,
    rpc_url: str | None = None,
) -> dict[str, Any]:
    """Query assets on a single chain."""
    chain = normalize_chain(chain_name)
    assets: list[dict[str, Any]] = []

    # Native
    native_entry = build_balance_entry(
        chain_name=chain.key,
        wallet=wallet,
        token_name="NATIVE",
        token_decimals=None,
        explicit_rpc_url=rpc_url,
    )
    if include_zero or int(native_entry.get("rawBalance", 0)) > 0:
        assets.append({
            "token": "NATIVE",
            "symbol": chain.native_symbol,
            "rawBalance": native_entry.get("rawBalance", "0"),
            "decimals": 18,
            "humanBalance": format_balance(native_entry.get("rawBalance", "0"), 18),
        })

    # Tokens — skip symbols that can't be resolved without a catalog
    for token_symbol in tokens:
        if token_symbol.upper() == "NATIVE":
            continue
        try:
            entry = build_balance_entry(
                chain_name=chain.key,
                wallet=wallet,
                token_name=token_symbol,
                token_decimals=None,
                explicit_rpc_url=rpc_url,
            )
            if include_zero or int(entry.get("rawBalance", 0)) > 0:
                assets.append({
                    "token": token_symbol.upper(),
                    "symbol": token_symbol.upper(),
                    "rawBalance": entry.get("rawBalance", "0"),
                    "decimals": int(entry["asset"].get("decimals", 18)),
                    "humanBalance": format_balance(
                        entry.get("rawBalance", "0"),
                        int(entry["asset"].get("decimals", 18)),
                    ),
                })
        except Exception:
            pass

    return {
        "chain": chain.key,
        "chainId": chain.chain_id,
        "assets": assets,
        "assetCount": len(assets),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query wallet balances across multiple chains with high precision",
    )
    parser.add_argument("--wallet", required=True, help="Wallet address to query")
    parser.add_argument("--chain", action="append", dest="chains",
                        help=f"Chain(s) to query; repeatable; defaults to: {', '.join(DEFAULT_CHAINS)}")
    parser.add_argument("--token", action="append", dest="tokens",
                        help=f"Token symbol(s) to query; repeatable; defaults to: {', '.join(DEFAULT_TOKENS)}")
    parser.add_argument("--include-zero", action="store_true", help="Include zero-balance assets")
    parser.add_argument("--output", help="Write JSON output to a file")
    parser.add_argument("--format", choices=["json", "table"], default="json", help="Output format")
    args = parser.parse_args()

    try:
        wallet = args.wallet.strip()
        chains_to_query = list(args.chains or DEFAULT_CHAINS)
        tokens_to_query = list(args.tokens or DEFAULT_TOKENS)

        results: list[dict[str, Any]] = []
        for chain_name in chains_to_query:
            try:
                chain_result = query_chain_assets(
                    chain_name=chain_name,
                    wallet=wallet,
                    tokens=tokens_to_query,
                    include_zero=args.include_zero,
                )
                results.append(chain_result)
            except Exception as e:
                results.append({"chain": chain_name, "error": str(e)})

        response = {
            "action": "wallet_multichain_summary",
            "wallet": wallet,
            "chains": results,
            "totalChains": len(chains_to_query),
            "successChains": sum(1 for r in results if "assets" in r),
        }

        if args.output:
            Path(args.output).write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        if args.format == "table":
            print(f"\n{'=' * 60}")
            print(f"Wallet: {wallet}")
            print(f"{'=' * 60}\n")
            for chain_result in results:
                if "error" in chain_result:
                    print(f"### {chain_result['chain']} ###")
                    print(f"  Error: {chain_result['error']}\n")
                    continue
                print(f"### {chain_result['chain']} (chainId: {chain_result['chainId']}) ###")
                for asset in chain_result.get("assets", []):
                    print(f"  {asset['symbol']}: {asset['humanBalance']}")
                print()
        else:
            dump_json(response)

    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
