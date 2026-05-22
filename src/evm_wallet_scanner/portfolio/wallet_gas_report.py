"""Gas report — summarize wallet gas spend from normal transaction history."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from evm_wallet_scanner.common import (
    dump_json,
    etherscan_request,
    format_units,
    iso_from_timestamp,
    normalize_chain,
    require_etherscan_api_key,
    validate_address,
)


def summarize_gas(tx: dict[str, Any]) -> dict[str, Any]:
    gas_used = int(str(tx.get("gasUsed") or "0"), 0)
    gas_price = int(str(tx.get("gasPrice") or "0"), 0)
    gas_cost_wei = gas_used * gas_price
    return {
        "hash": tx.get("hash"),
        "blockNumber": tx.get("blockNumber"),
        "timestamp": tx.get("timeStamp"),
        "timestampIso": iso_from_timestamp(tx.get("timeStamp")),
        "gasUsed": str(gas_used),
        "gasPriceWei": str(gas_price),
        "gasCostWei": str(gas_cost_wei),
        "gasCostNative": format_units(gas_cost_wei, 18),
        "success": (str(tx.get("txreceipt_status") or "") == "1" and str(tx.get("isError") or "0") == "0"),
    }


def aggregate_by_day(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Decimal | int]] = defaultdict(
        lambda: {"txCount": 0, "gasWei": Decimal(0)}
    )
    for item in items:
        ts = item.get("timestampIso")
        if not isinstance(ts, str) or len(ts) < 10:
            continue
        day = ts[:10]
        buckets[day]["txCount"] = int(buckets[day]["txCount"]) + 1
        buckets[day]["gasWei"] = Decimal(buckets[day]["gasWei"]) + Decimal(item["gasCostWei"])
    result = []
    for day in sorted(buckets.keys()):
        gas_wei = int(buckets[day]["gasWei"])
        result.append({
            "day": day,
            "txCount": int(buckets[day]["txCount"]),
            "gasCostWei": str(gas_wei),
            "gasCostNative": format_units(gas_wei, 18),
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize wallet gas spend from normal tx history")
    parser.add_argument("--chain", required=True, help="chain key")
    parser.add_argument("--wallet", required=True, help="wallet address")
    parser.add_argument("--start-block", default="0")
    parser.add_argument("--end-block", default="9999999999")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--offset", type=int, default=1000)
    parser.add_argument("--sort", choices=["asc", "desc"], default="desc")
    parser.add_argument("--output", help="write full JSON output to a file")
    args = parser.parse_args()

    try:
        chain = normalize_chain(args.chain)
        wallet = validate_address(args.wallet, "wallet")
        api_key = require_etherscan_api_key()
        payload = etherscan_request(
            chain_id=chain.chain_id, module="account", action="txlist",
            api_key=api_key,
            extra_params={
                "address": wallet, "startblock": args.start_block,
                "endblock": args.end_block, "page": args.page,
                "offset": args.offset, "sort": args.sort,
            },
        )
        result = [item for item in (payload.get("result") or []) if isinstance(item, dict)]
        outgoing = [item for item in result if str(item.get("from") or "").lower() == wallet.lower()]
        entries = [summarize_gas(item) for item in outgoing]
        total_wei = sum(int(item["gasCostWei"]) for item in entries)
        success_count = sum(1 for item in entries if item["success"])
        response = {
            "action": "wallet_gas_report",
            "chain": {"key": chain.key, "chainId": chain.chain_id, "nativeSymbol": chain.native_symbol},
            "wallet": wallet,
            "range": {
                "startBlock": args.start_block, "endBlock": args.end_block,
                "page": args.page, "offset": args.offset, "sort": args.sort,
            },
            "summary": {
                "txCount": len(entries),
                "successTxCount": success_count,
                "failedTxCount": len(entries) - success_count,
                "totalGasCostWei": str(total_wei),
                "totalGasCostNative": format_units(total_wei, 18),
            },
            "byDay": aggregate_by_day(entries),
            "items": entries,
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
