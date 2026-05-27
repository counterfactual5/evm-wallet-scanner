"""Portfolio valuation — estimate wallet portfolio value via Etherscan."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from evm_wallet_scanner.common import (
    build_balance_entry,
    dump_json,
    etherscan_request,
    format_units,
    normalize_chain,
    require_etherscan_api_key,
    validate_address,
)


def parse_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"{field_name} is not numeric: {value}") from exc


def to_usd_value(balance_raw: int, decimals: int, price_usd: Decimal) -> Decimal:
    quantity = Decimal(balance_raw) / (Decimal(10) ** decimals)
    return quantity * price_usd


def infer_common_token_price(asset: dict[str, Any], native_price_usd: Decimal) -> tuple[Decimal | None, str | None]:
    """Infer token price from known heuristics (stablecoins, native-wrapped)."""
    price_hint = str(asset.get("priceHint") or "").strip().lower()
    if bool(asset.get("isStable")) or price_hint == "stable_usd":
        return Decimal("1"), "catalog:stable_usd"
    if price_hint == "native":
        return native_price_usd, "catalog:native"
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate wallet portfolio value via Etherscan")
    parser.add_argument("--chain", required=True, help="chain key")
    parser.add_argument("--wallet", required=True, help="wallet address")
    parser.add_argument("--include-zero", action="store_true", help="include zero-value tokens")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--offset", type=int, default=100)
    parser.add_argument("--rpc-url", help="explicit RPC URL")
    parser.add_argument("--output", help="write full JSON output to a file")
    args = parser.parse_args()

    try:
        chain = normalize_chain(args.chain)
        wallet = validate_address(args.wallet, "wallet")
        api_key = require_etherscan_api_key()

        # Native balance
        native_balance = build_balance_entry(
            chain_name=chain.key, wallet=wallet, token_name=None,
            token_decimals=None, explicit_rpc_url=args.rpc_url,
        )

        # Native price from Etherscan
        native_price_payload = etherscan_request(
            chain_id=chain.chain_id, module="stats", action="ethprice", api_key=api_key,
        )
        native_price_result = native_price_payload.get("result") or {}
        native_price_usd = parse_decimal(
            native_price_result.get("ethusd")
            or native_price_result.get("ethusd_price")
            or native_price_result.get("nativeusd"),
            "native price",
        )
        native_value_usd = to_usd_value(
            balance_raw=int(native_balance["rawBalance"]),
            decimals=int(native_balance["asset"]["decimals"]),
            price_usd=native_price_usd,
        )

        token_entries: list[dict[str, Any]] = []
        total_usd = native_value_usd
        token_endpoint_error: str | None = None
        unpriced_token_count = 0

        try:
            token_payload = etherscan_request(
                chain_id=chain.chain_id, module="account", action="addresstokenbalance",
                api_key=api_key,
                extra_params={"address": wallet, "page": args.page, "offset": args.offset},
            )
            token_rows = token_payload.get("result") or []

            for row in token_rows:
                if not isinstance(row, dict):
                    continue
                token_decimals = int(str(row.get("TokenDivisor") or row.get("tokenDecimal") or "0"), 0)
                token_balance_raw = int(str(row.get("TokenQuantity") or row.get("balance") or "0"), 0)
                token_price_usd = parse_decimal(
                    row.get("TokenPriceUSD") or row.get("tokenPriceUSD") or "0", "token price"
                )
                token_address = str(row.get("TokenAddress") or row.get("tokenAddress"))
                price_source = "etherscan"

                token_value_usd = to_usd_value(token_balance_raw, token_decimals, token_price_usd)
                if token_balance_raw > 0 and token_price_usd == 0:
                    unpriced_token_count += 1
                if not args.include_zero and token_balance_raw == 0:
                    continue
                entry = {
                    "tokenAddress": token_address,
                    "symbol": row.get("TokenSymbol") or row.get("tokenSymbol"),
                    "name": row.get("TokenName") or row.get("tokenName"),
                    "decimals": token_decimals,
                    "rawBalance": str(token_balance_raw),
                    "humanBalance": format_units(token_balance_raw, token_decimals),
                    "priceUsd": format(token_price_usd, "f"),
                    "valueUsd": format(token_value_usd, "f"),
                    "priceSource": price_source,
                }
                token_entries.append(entry)
                total_usd += token_value_usd
        except RuntimeError as exc:
            token_endpoint_error = str(exc)

        response = {
            "action": "wallet_portfolio_value",
            "chain": {"key": chain.key, "chainId": chain.chain_id},
            "wallet": wallet,
            "nativeAsset": {
                "symbol": native_balance["asset"]["symbol"],
                "rawBalance": native_balance["rawBalance"],
                "humanBalance": native_balance["humanBalance"],
                "priceUsd": format(native_price_usd, "f"),
                "valueUsd": format(native_value_usd, "f"),
            },
            "tokens": token_entries,
            "tokenCount": len(token_entries),
            "partial": token_endpoint_error is not None or unpriced_token_count > 0,
            "tokenValuationError": token_endpoint_error,
            "unpricedTokenCount": unpriced_token_count,
            "estimatedTotalUsd": format(total_usd, "f"),
            "notes": [
                "ERC20 holdings and prices come from Etherscan addresstokenbalance.",
                "This estimate does not include DeFi positions (LP, lending, staking).",
            ],
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
