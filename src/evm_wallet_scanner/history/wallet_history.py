"""Wallet history — query normal, internal, and ERC-20 transfer history via Etherscan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evm_wallet_scanner.common import (
    dump_json,
    etherscan_request,
    format_units,
    iso_from_timestamp,
    normalize_chain,
    normalize_direction,
    require_etherscan_api_key,
    validate_address,
)


def summarize_normal_tx(wallet: str, item: dict[str, Any]) -> dict[str, Any]:
    value_raw = int(str(item.get("value") or "0"), 0)
    return {
        "kind": "normal",
        "hash": item.get("hash"),
        "blockNumber": item.get("blockNumber"),
        "timestamp": item.get("timeStamp"),
        "timestampIso": iso_from_timestamp(item.get("timeStamp")),
        "from": item.get("from"),
        "to": item.get("to"),
        "direction": normalize_direction(wallet, item.get("from"), item.get("to")),
        "valueRaw": str(value_raw),
        "valueHuman": format_units(value_raw, 18),
        "gasUsed": item.get("gasUsed"),
        "gasPrice": item.get("gasPrice"),
        "success": (str(item.get("txreceipt_status") or "") == "1" and str(item.get("isError") or "0") == "0"),
        "methodId": item.get("methodId"),
        "functionName": item.get("functionName"),
    }


def summarize_internal_tx(wallet: str, item: dict[str, Any]) -> dict[str, Any]:
    value_raw = int(str(item.get("value") or "0"), 0)
    return {
        "kind": "internal",
        "hash": item.get("hash"),
        "blockNumber": item.get("blockNumber"),
        "timestamp": item.get("timeStamp"),
        "timestampIso": iso_from_timestamp(item.get("timeStamp")),
        "from": item.get("from"),
        "to": item.get("to"),
        "direction": normalize_direction(wallet, item.get("from"), item.get("to")),
        "valueRaw": str(value_raw),
        "valueHuman": format_units(value_raw, 18),
        "contractAddress": item.get("contractAddress"),
        "type": item.get("type"),
        "traceId": item.get("traceId"),
        "success": str(item.get("isError") or "0") == "0",
    }


def summarize_token_transfer(wallet: str, item: dict[str, Any]) -> dict[str, Any]:
    decimals = int(str(item.get("tokenDecimal") or "0"), 0)
    value_raw = int(str(item.get("value") or "0"), 0)
    return {
        "kind": "erc20-transfer",
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Query wallet history via Etherscan")
    parser.add_argument("--chain", required=True, help="chain key such as ethereum / base / arbitrum")
    parser.add_argument("--wallet", required=True, help="wallet address")
    parser.add_argument("--kind", action="append", choices=["normal", "internal", "erc20"],
                        help="history kind to fetch; repeatable; default is normal")
    parser.add_argument("--contract-address", help="filter ERC20 transfers by token contract")
    parser.add_argument("--start-block", default="0", help="start block, default 0")
    parser.add_argument("--end-block", default="9999999999", help="end block, default latest-ish")
    parser.add_argument("--page", type=int, default=1, help="page number")
    parser.add_argument("--offset", type=int, default=20, help="items per page")
    parser.add_argument("--sort", choices=["asc", "desc"], default="desc", help="sort order")
    parser.add_argument("--output", help="write full JSON output to a file")
    args = parser.parse_args()

    try:
        chain = normalize_chain(args.chain)
        wallet = validate_address(args.wallet, "wallet")
        api_key = require_etherscan_api_key()
        kinds = args.kind or ["normal"]

        common_params: dict[str, Any] = {
            "address": wallet,
            "startblock": args.start_block,
            "endblock": args.end_block,
            "page": args.page,
            "offset": args.offset,
            "sort": args.sort,
        }

        sections: dict[str, Any] = {}
        if "normal" in kinds:
            payload = etherscan_request(
                chain_id=chain.chain_id, module="account", action="txlist",
                api_key=api_key, extra_params=common_params,
            )
            result = payload.get("result") or []
            sections["normal"] = {
                "count": len(result),
                "items": [summarize_normal_tx(wallet, item) for item in result if isinstance(item, dict)],
            }

        if "internal" in kinds:
            payload = etherscan_request(
                chain_id=chain.chain_id, module="account", action="txlistinternal",
                api_key=api_key, extra_params=common_params,
            )
            result = payload.get("result") or []
            sections["internal"] = {
                "count": len(result),
                "items": [summarize_internal_tx(wallet, item) for item in result if isinstance(item, dict)],
            }

        if "erc20" in kinds:
            params = dict(common_params)
            if args.contract_address:
                params["contractaddress"] = validate_address(args.contract_address, "contract-address")
            payload = etherscan_request(
                chain_id=chain.chain_id, module="account", action="tokentx",
                api_key=api_key, extra_params=params,
            )
            result = payload.get("result") or []
            sections["erc20"] = {
                "count": len(result),
                "items": [summarize_token_transfer(wallet, item) for item in result if isinstance(item, dict)],
            }

        response = {
            "action": "wallet_history",
            "chain": {"key": chain.key, "chainId": chain.chain_id},
            "wallet": wallet,
            "kinds": kinds,
            "page": args.page,
            "offset": args.offset,
            "sort": args.sort,
            "startBlock": args.start_block,
            "endBlock": args.end_block,
            "contractAddress": args.contract_address,
            "sections": sections,
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
