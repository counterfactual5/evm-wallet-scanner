#!/usr/bin/env python3
"""Show recent transaction history for a wallet.

Usage:
    python examples/tx_history.py ethereum 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

Environment:
    ETHERSCAN_API_KEY  — required for history queries
"""

import os
import sys

from evm_wallet_scanner.common import (
    dump_json,
    etherscan_request,
    format_units,
    iso_from_timestamp,
    normalize_chain,
    validate_address,
)
from evm_wallet_scanner.chains import normalize_chain

MAX_RESULTS = 10


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <chain> <wallet_address>")
        sys.exit(1)

    chain_name = sys.argv[1]
    wallet = sys.argv[2]

    if not os.environ.get("ETHERSCAN_API_KEY"):
        print("❌ ETHERSCAN_API_KEY is not set")
        sys.exit(1)

    chain = normalize_chain(chain_name)
    wallet_addr = validate_address(wallet, "wallet")
    api_key = os.environ["ETHERSCAN_API_KEY"]

    print(f"📜 Transaction History: {wallet_addr}")
    print(f"   Chain: {chain.key} (chain ID {chain.chain_id})")
    print()

    # Fetch normal transactions
    payload = etherscan_request(
        chain_id=chain.chain_id,
        module="account",
        action="txlist",
        api_key=api_key,
        extra_params={
            "address": wallet_addr,
            "startblock": "0",
            "endblock": "9999999999",
            "page": "1",
            "offset": str(MAX_RESULTS),
            "sort": "desc",
        },
    )

    txs = payload.get("result", [])
    if not isinstance(txs, list) or len(txs) == 0:
        print("   No transactions found.")
        return

    print(f"   Showing {min(len(txs), MAX_RESULTS)} most recent:")
    print()
    print(f"  {'Time':<20} {'From/To':<25} {'Value':<15} {'Status'}")
    print("  " + "-" * 75)

    for tx in txs[:MAX_RESULTS]:
        ts = iso_from_timestamp(str(tx.get("timeStamp", ""))) or "?"
        ts_short = ts[:19] if ts else "?"
        value_wei = int(str(tx.get("value", "0")), 0)
        value = format_units(value_wei, 18)
        src = (tx.get("from") or "")[:12] + "..."
        dst = (tx.get("to") or "")[:12] + "..."
        direction = "→" if tx.get("from", "").lower() == wallet_addr else "←"
        status = "✅" if tx.get("isError") == "0" else "❌"

        print(f"  {ts_short:<20} {src} {direction} {dst:<12} {value:<15} {status}")

    print()
    print("💡 For detailed JSON: evm-scan history --chain", chain_name, "--wallet", wallet)


if __name__ == "__main__":
    main()
