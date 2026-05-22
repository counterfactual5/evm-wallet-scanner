"""Counterparty analysis — find related addresses by analyzing transaction history."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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

ETH_DECIMALS = 18
ETHERSCAN_PAGE_LIMIT = 1000
DEFAULT_FETCH_CAP = 3000
TX_HASH_SAMPLE_LIMIT = 5

GENERIC_KNOWN_CONTRACTS: dict[str, dict[str, str]] = {
    "0x000000000022d473030f116ddee9f6b43ac78ba3": {"name": "Uniswap Permit2", "type": "protocol"},
}

KNOWN_CONTRACTS_BY_CHAIN: dict[str, dict[str, dict[str, str]]] = {
    "ethereum": {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"name": "USDC", "type": "token"},
        "0xdac17f958d2ee523a2206206994597c13d831ec7": {"name": "USDT", "type": "token"},
        "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": {"name": "WBTC", "type": "token"},
        "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": {"name": "UNI", "type": "token"},
        "0x000000000004444c5dc75cb358380d2e3de08a90": {"name": "Uniswap Universal Router", "type": "dex"},
        "0x1111111254eeb25477b68fb85ed929f73a960582": {"name": "1inch", "type": "aggregator"},
        "0x7a250d5630b4f539739df2c5dacb4c659f2488d7": {"name": "Uniswap V2 Router", "type": "dex"},
        "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": {"name": "Uniswap V3 Router", "type": "dex"},
        "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b": {"name": "Uniswap V3 Router 2", "type": "dex"},
        "0xdef1c0ded9bec7f1a1670819833240f027b25eff": {"name": "0x Exchange Proxy", "type": "aggregator"},
    },
}


def parse_int(value: Any) -> int:
    if value in (None, "", "0x", "0x0"):
        return 0
    try:
        return int(str(value), 0)
    except ValueError:
        return 0


def known_contracts_for_chain(chain_key: str) -> dict[str, dict[str, str]]:
    known = dict(GENERIC_KNOWN_CONTRACTS)
    known.update(KNOWN_CONTRACTS_BY_CHAIN.get(chain_key, {}))
    return known


def fetch_account_events(
    *,
    chain_id: int,
    wallet: str,
    action: str,
    api_key: str,
    fetch_cap: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    page = 1
    pages = 0
    reached_fetch_cap = False

    while len(events) < fetch_cap:
        remaining = fetch_cap - len(events)
        page_size = min(ETHERSCAN_PAGE_LIMIT, remaining)
        payload = etherscan_request(
            chain_id=chain_id, module="account", action=action,
            api_key=api_key,
            extra_params={
                "address": wallet, "startblock": "0", "endblock": "99999999",
                "page": page, "offset": page_size, "sort": "desc",
            },
        )
        pages += 1
        raw_items = payload.get("result") or []
        if not isinstance(raw_items, list):
            raise RuntimeError(f"Etherscan account.{action} returned non-list result")
        batch = [item for item in raw_items if isinstance(item, dict)]
        events.extend(batch)
        if len(raw_items) < page_size:
            break
        if len(events) >= fetch_cap:
            reached_fetch_cap = True
            break
        page += 1

    return events, {
        "action": action, "pages": pages, "fetched": len(events),
        "fetchCap": fetch_cap, "sort": "desc", "reachedFetchCap": reached_fetch_cap,
    }


def analyze_counterparties(
    chain: Any,
    wallet: str,
    min_interactions: int = 1,
    exclude_known_contracts: bool = True,
    include_erc20: bool = True,
    include_internal: bool = True,
    offset: int = DEFAULT_FETCH_CAP,
) -> dict[str, Any]:
    """Analyze wallet counterparties from transaction history."""
    wallet_lower = wallet.lower()
    api_key = require_etherscan_api_key()
    known_contracts = known_contracts_for_chain(chain.key)

    counterparties: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "interactions": 0, "eventCount": 0, "inCount": 0, "outCount": 0,
            "inValueWei": 0, "outValueWei": 0, "tokens": set(), "sources": set(),
            "firstSeen": None, "lastSeen": None, "txHashes": [],
            "_interactionTxHashes": set(), "_inTxHashes": set(), "_outTxHashes": set(),
        }
    )

    def update_counterparty(
        *, address: str, direction: str, value_wei: int = 0,
        token_symbol: str | None = None, timestamp: Any = None,
        tx_hash: str | None = None, source: str,
    ) -> None:
        if not address or address.lower() == wallet_lower or direction not in {"in", "out"}:
            return
        addr_lower = address.lower()
        cp = counterparties[addr_lower]
        cp["eventCount"] += 1
        cp["sources"].add(source)
        if tx_hash:
            tx_hash_lower = tx_hash.lower()
            if tx_hash_lower not in cp["_interactionTxHashes"]:
                cp["interactions"] += 1
                cp["_interactionTxHashes"].add(tx_hash_lower)
            if direction == "in" and tx_hash_lower not in cp["_inTxHashes"]:
                cp["inCount"] += 1
                cp["_inTxHashes"].add(tx_hash_lower)
            if direction == "out" and tx_hash_lower not in cp["_outTxHashes"]:
                cp["outCount"] += 1
                cp["_outTxHashes"].add(tx_hash_lower)
            if tx_hash_lower not in cp["txHashes"] and len(cp["txHashes"]) < TX_HASH_SAMPLE_LIMIT:
                cp["txHashes"].append(tx_hash_lower)
        else:
            cp["interactions"] += 1
            if direction == "in":
                cp["inCount"] += 1
            else:
                cp["outCount"] += 1
        if direction == "in":
            cp["inValueWei"] += value_wei
        elif direction == "out":
            cp["outValueWei"] += value_wei
        symbol = (token_symbol or "").strip()
        if symbol:
            cp["tokens"].add(symbol)
        ts_int = parse_int(timestamp)
        if ts_int > 0:
            ts_iso = iso_from_timestamp(ts_int)
            if cp["firstSeen"] is None or ts_int < cp["firstSeen"]["unix"]:
                cp["firstSeen"] = {"unix": ts_int, "iso": ts_iso}
            if cp["lastSeen"] is None or ts_int > cp["lastSeen"]["unix"]:
                cp["lastSeen"] = {"unix": ts_int, "iso": ts_iso}

    fetch: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    partial = False

    fetch_plan = [
        ("normal", "txlist", True),
        ("internal", "txlistinternal", include_internal),
        ("erc20", "tokentx", include_erc20),
    ]

    def fetch_and_process(
        source: str, action: str, enabled: bool,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], Exception | None]:
        if not enabled:
            return source, [], {
                "action": action, "enabled": False, "pages": 0, "fetched": 0,
                "fetchCap": offset, "sort": "desc", "reachedFetchCap": False,
            }, None
        try:
            records, meta = fetch_account_events(
                chain_id=chain.chain_id, wallet=wallet,
                action=action, api_key=api_key, fetch_cap=offset,
            )
            return source, records, {"enabled": True, **meta}, None
        except Exception as exc:
            return source, [], {
                "action": action, "enabled": True, "pages": 0, "fetched": 0,
                "fetchCap": offset, "sort": "desc", "reachedFetchCap": False, "error": str(exc),
            }, exc

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fetch_and_process, source, action, enabled): (source, action, enabled)
            for source, action, enabled in fetch_plan
        }
        for future in as_completed(futures):
            source, records, meta, error = future.result()
            fetch[source] = meta
            if error:
                partial = True
                warnings.append(f"failed to fetch {source} records: {error}")
                continue
            if not meta.get("enabled"):
                continue
            if meta.get("reachedFetchCap"):
                warnings.append(f"{source} records reached fetch cap {offset}")
            for tx in records:
                from_addr = tx.get("from", "")
                to_addr = tx.get("to", "")
                direction = normalize_direction(wallet, from_addr, to_addr)
                other = to_addr if direction == "out" else from_addr
                update_counterparty(
                    address=other, direction=direction,
                    value_wei=parse_int(tx.get("value")) if source != "erc20" else 0,
                    token_symbol=tx.get("tokenSymbol") if source == "erc20" else None,
                    timestamp=tx.get("timeStamp"), tx_hash=tx.get("hash"), source=source,
                )

    result_list = []
    for addr, data in counterparties.items():
        if data["interactions"] < min_interactions:
            continue
        known = known_contracts.get(addr)
        if exclude_known_contracts and known:
            continue
        entry: dict[str, Any] = {
            "address": addr,
            "interactions": data["interactions"],
            "eventCount": data["eventCount"],
            "inCount": data["inCount"],
            "outCount": data["outCount"],
            "inValueWei": str(data["inValueWei"]),
            "outValueWei": str(data["outValueWei"]),
            "inValueEth": format_units(data["inValueWei"], ETH_DECIMALS),
            "outValueEth": format_units(data["outValueWei"], ETH_DECIMALS),
            "tokens": sorted(data["tokens"]) if data["tokens"] else [],
            "sources": sorted(data["sources"]),
            "firstSeen": data["firstSeen"],
            "lastSeen": data["lastSeen"],
            "txHashes": data["txHashes"],
        }
        if known:
            entry["knownAs"] = known
        result_list.append(entry)

    result_list.sort(
        key=lambda item: (
            -item["interactions"],
            -(item["lastSeen"] or {}).get("unix", 0),
            item["address"],
        )
    )

    return {
        "action": "wallet_counterparties",
        "chain": {"key": chain.key, "chainId": chain.chain_id},
        "wallet": wallet,
        "partial": partial,
        "warnings": warnings,
        "fetch": fetch,
        "totalCounterparties": len(result_list),
        "counterparties": result_list,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze wallet counterparties")
    parser.add_argument("--chain", required=True, help="Chain key")
    parser.add_argument("--wallet", required=True, help="Wallet address")
    parser.add_argument("--min-interactions", type=int, default=1)
    parser.add_argument("--include-known-contracts", action="store_true")
    parser.add_argument("--exclude-erc20", action="store_true")
    parser.add_argument("--exclude-internal", action="store_true")
    parser.add_argument("--offset", type=int, default=DEFAULT_FETCH_CAP)
    parser.add_argument("--output", help="Write result to file")
    args = parser.parse_args()

    try:
        if args.offset < 1:
            raise ValueError("--offset must be a positive integer")
        chain = normalize_chain(args.chain)
        wallet = validate_address(args.wallet, "wallet")
        result = analyze_counterparties(
            chain=chain, wallet=wallet,
            min_interactions=args.min_interactions,
            exclude_known_contracts=not args.include_known_contracts,
            include_erc20=not args.exclude_erc20,
            include_internal=not args.exclude_internal,
            offset=args.offset,
        )
        if args.output:
            Path(args.output).write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
            )
        dump_json(result)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
