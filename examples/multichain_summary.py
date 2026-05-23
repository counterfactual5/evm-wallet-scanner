#!/usr/bin/env python3
"""Show portfolio summary across all 5 supported chains.

Usage:
    python examples/multichain_summary.py 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

Environment:
    No config needed — uses public RPC fallbacks.
"""

import sys

from evm_wallet_scanner.common import build_balance_entry
from evm_wallet_scanner.chains import CHAINS

# Well-known tokens by chain
KNOWN_TOKENS: dict[str, list[str]] = {
    "ethereum": [
        ("USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
        ("USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7"),
    ],
    "base": [
        ("USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
    ],
    "arbitrum": [
        ("USDC", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"),
    ],
    "optimism": [
        ("USDC", "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85"),
    ],
    "polygon": [
        ("USDC", "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"),
    ],
}


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <wallet_address>")
        sys.exit(1)

    wallet = sys.argv[1]

    print(f"🌐 Multi-Chain Portfolio: {wallet}")
    print()

    grand_total_native = {}
    for chain_name, chain in CHAINS.items():
        try:
            native = build_balance_entry(chain_name, wallet, None, None, None)
            native_bal = native["humanBalance"]
            print(f"  {chain_name.capitalize():<12} {native_bal} {chain.native_symbol}")
            grand_total_native[chain_name] = native_bal

            # Known tokens
            for sym, addr in KNOWN_TOKENS.get(chain_name, []):
                try:
                    tok = build_balance_entry(chain_name, wallet, addr, None, None)
                    tb = tok["humanBalance"]
                    if tb != "0":
                        print(f"    {sym:<8} {tb}")
                except Exception:
                    pass

        except Exception as e:
            print(f"  {chain_name.capitalize():<12} ❌ {e}")

    print()
    print("💡 For detailed JSON: evm-scan multichain --wallet", wallet)


if __name__ == "__main__":
    main()
