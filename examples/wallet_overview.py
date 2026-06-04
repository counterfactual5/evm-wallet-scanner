#!/usr/bin/env python3
"""Show native + common ERC20 balances for a wallet.

Usage:
    python examples/wallet_overview.py ethereum 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

Environment:
    No config needed — falls back to public RPC if RPC_URL is not set.
"""

import sys

from evm_wallet_scanner.common import build_balance_entry
from evm_wallet_scanner.chains import normalize_chain

# Common tokens to check per chain
COMMON_TOKENS: dict[str, list[str]] = {
    "ethereum": [
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
        "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
        "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
    ],
    "base": [
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
    ],
    "arbitrum": [
        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # USDC
    ],
    "optimism": [
        "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",  # USDC
    ],
    "polygon": [
        "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",  # USDC
    ],
}


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <chain> <wallet_address>")
        sys.exit(1)

    chain_name = sys.argv[1]
    wallet = sys.argv[2]
    chain = normalize_chain(chain_name)

    print(f"📊 Wallet Overview: {wallet}")
    print(f"   Chain: {chain.key} (chain ID {chain.chain_id})")
    print()

    # Native balance
    native = build_balance_entry(chain.key, wallet, None, None, None)
    print(f"   {chain.native_symbol:<6} {native['humanBalance']}")

    # Common ERC20 tokens
    tokens = COMMON_TOKENS.get(chain.key, [])
    for token_addr in tokens:
        try:
            result = build_balance_entry(chain.key, wallet, token_addr, None, None)
            symbol = result["asset"]["symbol"]
            balance = result["humanBalance"]
            print(f"   {symbol:<6} {balance}")
        except Exception as e:
            print(f"   {token_addr[:10]}... error: {e}")

    print()
    print("💡 Full JSON output: add --output result.json to the CLI command")


if __name__ == "__main__":
    main()
