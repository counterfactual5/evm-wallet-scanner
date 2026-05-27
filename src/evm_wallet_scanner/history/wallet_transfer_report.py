"""ERC-20 transfer report — aggregate token transfers over a time window."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from decimal import Decimal
from pathlib import Path
from typing import Any

from evm_wallet_scanner.common import (
    dump_json,
    etherscan_request,
    format_units,
    get_block_by_timestamp,
    iso_from_timestamp,
    normalize_chain,
    normalize_direction,
    require_etherscan_api_key,
    validate_address,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an ERC20 transfer report for a wallet")
    parser.add_argument("--chain", required=True, help="chain key")
    parser.add_argument("--wallet", required=True, help="wallet address")
    parser.add_argument("--days", type=int, default=30, help="rolling window in days, default 30")
    parser.add_argument("--start-timestamp", type=int, help="unix timestamp start; overrides --days")
    parser.add_argument("--end-timestamp", type=int, help="unix timestamp end; default now")
    parser.add_argument("--page", type=int, default=1, help="etherscan page number")
    parser.add_argument("--offset", type=int, default=200, help="etherscan page size")
    parser.add_argument("--contract-address", help="optional token contract filter")
    parser.add_argument("--sample-limit", type=int, default=10, help="number of recent transfers to include")
    parser.add_argument("--output", help="write full JSON output to a file")
    return parser.parse_args()


def timestamp_bounds(args: argparse.Namespace) -> tuple[int, int]:
    end_ts = args.end_timestamp or int(datetime.now(tz=UTC).timestamp())
    if args.start_timestamp is not None:
        start_ts = args.start_timestamp
    else:
        start_ts = int((datetime.fromtimestamp(end_ts, tz=UTC) - timedelta(days=args.days)).timestamp())
    if start_ts > end_ts:
        raise ValueError("start timestamp must be less than or equal to end timestamp")
    return start_ts, end_ts


def summarize_transfer(wallet: str, item: dict[str, Any]) -> dict[str, Any]:
    decimals = int(str(item.get("tokenDecimal") or "0"), 0)
    value_raw = int(str(item.get("value") or "0"), 0)
    return {
        "hash": item.get("hash"),
        "blockNumber": item.get("blockNumber"),
        "timestamp": item.get("timeStamp"),
        "timestampIso": iso_from_timestamp(item.get("timeStamp")),
        "from": item.get("from"),
        "to": item.get("to"),
        "direction": normalize_direction(wallet, item.get("from"), item.get("to")),
        "tokenAddress": item.get("contractAddress"),
        "tokenSymbol": item.get("tokenSymbol"),
        "tokenName": item.get("tokenName"),
        "decimals": decimals,
        "valueRaw": str(value_raw),
        "valueHuman": format_units(value_raw, decimals),
    }


def format_signed_units(raw_value: int, decimals: int) -> str:
    if raw_value < 0:
        return "-" + format_units(abs(raw_value), decimals)
    return format_units(raw_value, decimals)


def main() -> None:
    args = parse_args()
    try:
        chain = normalize_chain(args.chain)
        wallet = validate_address(args.wallet, "wallet")
        api_key = require_etherscan_api_key()
        start_ts, end_ts = timestamp_bounds(args)
        start_block = get_block_by_timestamp(chain.chain_id, start_ts, "after", api_key)
        end_block = get_block_by_timestamp(chain.chain_id, end_ts, "before", api_key)

        params: dict[str, Any] = {
            "address": wallet,
            "startblock": start_block,
            "endblock": end_block,
            "page": args.page,
            "offset": args.offset,
            "sort": "desc",
        }
        if args.contract_address:
            params["contractaddress"] = validate_address(args.contract_address, "contract-address")

        payload = etherscan_request(
            chain_id=chain.chain_id, module="account", action="tokentx",
            api_key=api_key, extra_params=params,
        )
        result = payload.get("result") or []
        summarized = [summarize_transfer(wallet, item) for item in result if isinstance(item, dict)]

        by_token: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {
                "tokenAddress": None, "symbol": None, "name": None, "decimals": 0,
                "incomingCount": 0, "outgoingCount": 0, "incomingRaw": 0, "outgoingRaw": 0,
            }
        )
        for item in summarized:
            key = (str(item["tokenAddress"]), str(item["tokenSymbol"]))
            row = by_token[key]
            row["tokenAddress"] = item["tokenAddress"]
            row["symbol"] = item["tokenSymbol"]
            row["name"] = item["tokenName"]
            row["decimals"] = item["decimals"]
            raw_value = int(item["valueRaw"])
            if item["direction"] == "in":
                row["incomingCount"] += 1
                row["incomingRaw"] += raw_value
            elif item["direction"] == "out":
                row["outgoingCount"] += 1
                row["outgoingRaw"] += raw_value

        token_summaries = []
        for row in by_token.values():
            decimals = int(row["decimals"])
            incoming_raw = int(row["incomingRaw"])
            outgoing_raw = int(row["outgoingRaw"])
            net_raw = incoming_raw - outgoing_raw
            token_summaries.append({
                "tokenAddress": row["tokenAddress"],
                "symbol": row["symbol"],
                "name": row["name"],
                "decimals": decimals,
                "incomingCount": row["incomingCount"],
                "outgoingCount": row["outgoingCount"],
                "incomingRaw": str(incoming_raw),
                "incomingHuman": format_units(incoming_raw, decimals),
                "outgoingRaw": str(outgoing_raw),
                "outgoingHuman": format_units(outgoing_raw, decimals),
                "netRaw": str(net_raw),
                "netHuman": format_signed_units(net_raw, decimals),
                "netDirection": "in" if net_raw > 0 else ("out" if net_raw < 0 else "flat"),
            })

        token_summaries.sort(
            key=lambda item: (abs(Decimal(item["netRaw"])), item["incomingCount"] + item["outgoingCount"]),
            reverse=True,
        )

        response = {
            "action": "wallet_transfer_report",
            "chain": {"key": chain.key, "chainId": chain.chain_id},
            "wallet": wallet,
            "window": {
                "startTimestamp": start_ts,
                "startIso": iso_from_timestamp(start_ts),
                "endTimestamp": end_ts,
                "endIso": iso_from_timestamp(end_ts),
                "startBlock": start_block,
                "endBlock": end_block,
            },
            "page": args.page,
            "offset": args.offset,
            "contractAddress": args.contract_address,
            "transferCount": len(summarized),
            "tokenSummaries": token_summaries,
            "recentTransfers": summarized[: args.sample_limit],
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
