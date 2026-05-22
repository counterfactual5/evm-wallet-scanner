"""Transaction status — query receipt and success status by tx hash."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evm_wallet_scanner.common import (
    dump_json,
    get_transaction_receipt,
    normalize_chain,
    receipt_succeeded,
    resolve_rpc_url,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query transaction receipt/status by tx hash")
    parser.add_argument("--chain", required=True, help="chain key")
    parser.add_argument("--tx-hash", required=True, help="transaction hash")
    parser.add_argument("--rpc-url", help="explicit RPC URL")
    parser.add_argument("--output", help="write full JSON output to a file")
    args = parser.parse_args()

    try:
        chain = normalize_chain(args.chain)
        rpc_url, rpc_candidates = resolve_rpc_url(args.rpc_url, chain.chain_id)
        receipt = get_transaction_receipt(args.tx_hash, rpc_url)
        status = receipt.get("status")
        success = receipt_succeeded(receipt)
        response = {
            "action": "wallet_tx_status",
            "chain": {"key": chain.key, "chainId": chain.chain_id},
            "txHash": args.tx_hash,
            "success": success,
            "status": status,
            "receipt": receipt,
            "rpcUrlResolved": rpc_url,
            "rpcEnvCandidates": rpc_candidates,
        }
        if args.output:
            Path(args.output).write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
        dump_json(response)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
