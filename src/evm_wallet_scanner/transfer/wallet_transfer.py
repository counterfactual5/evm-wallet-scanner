"""EVM wallet transfer — native / ERC-20 token transfer with dry-run support.

Uses pure JSON-RPC for all queries.  Transaction signing requires the
optional ``eth-account`` package (``pip install evm-wallet-scanner[signer]``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from evm_wallet_scanner import state_machine
from evm_wallet_scanner.audit import (
    EVENT_BROADCAST,
    EVENT_CONFIRM,
    EVENT_ERROR,
    EVENT_SIGN,
    log_event,
)
from evm_wallet_scanner.common import (
    _SELECTOR_TRANSFER,
    _encode_address,
    _encode_uint256,
    _json_rpc,
    dump_json,
    estimate_transaction_gas,
    format_units,
    normalize_chain,
    query_erc20_balance,
    query_gas_price,
    query_native_balance,
    query_token_decimals,
    query_token_symbol,
    receipt_succeeded,
    resolve_query_token,
    resolve_rpc_url,
    validate_address,
    wait_for_transaction_receipt,
)

PRIVATE_KEY_ENV_CANDIDATES = ("HOT_WALLET_PRIVATE_KEY", "PRIVATE_KEY")


def parse_human_amount_to_raw(amount: str, decimals: int) -> int:
    try:
        value = Decimal(amount)
    except InvalidOperation as exc:
        raise ValueError(f"invalid --amount value: {amount}") from exc
    if value <= 0:
        raise ValueError("--amount must be greater than 0")
    scaled = value * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"amount has too many decimal places for token decimals={decimals}")
    return int(scaled)


def build_confirmation_phrase(chain_key: str, token_symbol: str, amount_human: str, receiver: str) -> str:
    return f"TRANSFER {chain_key} {token_symbol} {amount_human} TO {receiver}"


def resolve_private_key(explicit_private_key: str | None) -> tuple[str, str]:
    if explicit_private_key:
        return explicit_private_key, "--private-key"
    for env_name in PRIVATE_KEY_ENV_CANDIDATES:
        value = os.environ.get(env_name, "").strip()
        if value:
            return value, env_name
    raise RuntimeError("no signer private key found; pass --private-key or set HOT_WALLET_PRIVATE_KEY/PRIVATE_KEY")


def build_erc20_transfer_data(receiver: str, raw_amount: int) -> str:
    """Build ERC-20 transfer(address,uint256) calldata."""
    return "0x" + _SELECTOR_TRANSFER.replace("0x", "") + _encode_address(receiver) + _encode_uint256(raw_amount)


def resolve_transfer_token(
    *,
    chain_key: str,
    rpc_url: str,
    token_name: str,
    token_address: str | None,
    token_decimals: int | None,
) -> dict[str, Any]:
    if token_address:
        address = validate_address(token_address, "token-address")
        decimals = token_decimals if token_decimals is not None else query_token_decimals(address, rpc_url)
        symbol = query_token_symbol(address, rpc_url) or "UNKNOWN"
        return {"kind": "erc20", "symbol": symbol, "address": address, "decimals": decimals}
    return resolve_query_token(chain_key, token_name, token_decimals, rpc_url)


def build_tx_fields(*, sender: str, receiver: str, token: dict[str, Any], raw_amount: int) -> dict[str, str]:
    is_native = token["address"] == "NATIVE"
    tx_to = receiver if is_native else str(token["address"])
    tx_value = str(raw_amount) if is_native else "0"
    tx_data = "0x" if is_native else build_erc20_transfer_data(receiver, raw_amount)
    return {"to": tx_to, "value": tx_value, "data": tx_data, "from": sender}


def capture_balances(
    *,
    sender: str,
    receiver: str,
    token: dict[str, Any],
    rpc_url: str,
) -> dict[str, int]:
    sender_native = query_native_balance(sender, rpc_url)
    receiver_native = query_native_balance(receiver, rpc_url)
    if token["address"] == "NATIVE":
        sender_asset = sender_native
        receiver_asset = receiver_native
    else:
        token_address = str(token["address"])
        sender_asset = query_erc20_balance(sender, token_address, rpc_url)
        receiver_asset = query_erc20_balance(receiver, token_address, rpc_url)
    return {
        "senderNative": sender_native,
        "receiverNative": receiver_native,
        "senderAsset": sender_asset,
        "receiverAsset": receiver_asset,
    }


def _fetch_pending_nonce(address: str, rpc_url: str) -> int:
    """Return the next nonce for ``address`` as an int.

    Uses the ``pending`` tag so a freshly-broadcast tx in the mempool is not
    skipped. ``eth_getTransactionCount`` returns a hex string over JSON-RPC,
    which ``eth-account`` will reject if passed through unconverted.
    """
    raw = _json_rpc("eth_getTransactionCount", [address, "pending"], rpc_url)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        return int(raw, 0)
    raise RuntimeError(f"eth_getTransactionCount returned unexpected value: {raw!r}")


def sign_and_broadcast(
    *,
    tx_fields: dict[str, str],
    chain_id: int,
    gas_limit: int,
    gas_price: int,
    private_key: str,
    rpc_url: str,
) -> dict[str, Any]:
    """Sign a transaction with eth-account and broadcast via eth_sendRawTransaction."""
    try:
        from eth_account import Account
    except ImportError:
        raise ImportError(
            "eth-account is required for signing transactions. Install with: pip install evm-wallet-scanner[signer]"
        )

    account = Account.from_key(private_key)

    tx: dict[str, Any] = {
        "to": tx_fields["to"],
        "value": int(tx_fields["value"]),
        "gas": gas_limit,
        "gasPrice": gas_price,
        "data": tx_fields["data"],
        "nonce": _fetch_pending_nonce(account.address, rpc_url),
        "chainId": chain_id,
    }

    signed = account.sign_transaction(tx)
    raw_tx = signed.raw_transaction.hex() if hasattr(signed.raw_transaction, "hex") else signed.raw_transaction

    tx_hash = _json_rpc("eth_sendRawTransaction", [raw_tx], rpc_url)
    return {"transactionHash": tx_hash}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EVM wallet transfer (dry-run by default)")
    parser.add_argument("--chain", required=True, help="chain name")
    parser.add_argument("--from", dest="sender", required=True, help="sender address")
    parser.add_argument("--to", dest="receiver", required=True, help="receiver address")
    parser.add_argument("--token", default="NATIVE", help="NATIVE or ERC20 symbol/address")
    parser.add_argument("--token-address", help="arbitrary ERC20 address")
    parser.add_argument("--token-decimals", type=int, help="override token decimals")
    amount_group = parser.add_mutually_exclusive_group(required=False)
    amount_group.add_argument("--amount", help="human-readable amount (e.g. 0.01)")
    amount_group.add_argument("--amount-raw", help="raw uint256 amount")
    amount_group.add_argument("--send-all", action="store_true", help="send entire balance")
    parser.add_argument("--rpc-url", help="explicit RPC URL")
    parser.add_argument("--gas-limit", help="optional gas limit")
    parser.add_argument("--gas-price", help="optional gas price (wei)")
    parser.add_argument("--private-key", help="signer private key (or set env var)")
    parser.add_argument("--broadcast", action="store_true", help="actually broadcast")
    parser.add_argument("--confirm", help="must match confirmation phrase to broadcast")
    parser.add_argument("--receipt-confirmations", type=int, default=1)
    parser.add_argument("--output", help="write JSON output to file")
    return parser


def parse_args() -> argparse.Namespace:
    return _build_parser().parse_args()


def _coerce_args(args: argparse.Namespace | None) -> argparse.Namespace:
    """Ensure ``args`` carries every attribute the implementation expects.

    The unified ``evm-scan`` CLI builds its own argparse namespace (see
    ``evm_wallet_scanner.cli``) which historically omitted a few transfer-only
    flags (``--broadcast``, ``--confirm``, ``--amount-raw``, ``--send-all``,
    ``--receipt-confirmations``). Filling in defaults here keeps the
    standalone module callable and prevents ``AttributeError`` when the
    orchestrator forwards a partial namespace.
    """
    if args is None:
        args = parse_args()
    defaults: dict[str, Any] = {
        "token_address": None,
        "token_decimals": None,
        "amount": None,
        "amount_raw": None,
        "send_all": False,
        "rpc_url": None,
        "gas_limit": None,
        "gas_price": None,
        "private_key": None,
        "broadcast": False,
        "confirm": None,
        "receipt_confirmations": 1,
        "output": None,
    }
    for key, value in defaults.items():
        if not hasattr(args, key):
            setattr(args, key, value)
    return args


def main(args: argparse.Namespace | None = None) -> None:
    args = _coerce_args(args)
    try:
        chain = normalize_chain(args.chain)
        sender = validate_address(args.sender, "from")
        receiver = validate_address(args.receiver, "to")
        rpc_url, rpc_candidates = resolve_rpc_url(args.rpc_url, chain.chain_id)
        token = resolve_transfer_token(
            chain_key=chain.key,
            rpc_url=rpc_url,
            token_name=args.token,
            token_address=args.token_address,
            token_decimals=args.token_decimals,
        )
        decimals = int(token["decimals"])

        if not any([args.amount is not None, args.amount_raw is not None, args.send_all]):
            raise ValueError("one of --amount / --amount-raw / --send-all is required")

        if args.gas_price is not None:
            gas_price = int(args.gas_price, 0)
            if gas_price <= 0:
                raise ValueError("--gas-price must be > 0")
        else:
            gas_price = query_gas_price(rpc_url)

        native_balance_raw = query_native_balance(sender, rpc_url)
        token_balance_raw = (
            native_balance_raw
            if token["address"] == "NATIVE"
            else query_erc20_balance(sender, str(token["address"]), rpc_url)
        )

        if args.send_all:
            if token["address"] == "NATIVE":
                provisional_tx = build_tx_fields(sender=sender, receiver=receiver, token=token, raw_amount=1)
                estimated_gas = (
                    int(args.gas_limit, 0) if args.gas_limit else estimate_transaction_gas(provisional_tx, rpc_url)
                )
                raw_amount = native_balance_raw - estimated_gas * gas_price
                if raw_amount <= 0:
                    raise RuntimeError("insufficient native balance to pay gas for --send-all")
            else:
                raw_amount = token_balance_raw
                if raw_amount <= 0:
                    raise RuntimeError("token balance is zero; cannot --send-all")
        elif args.amount_raw is not None:
            raw_amount = int(args.amount_raw, 0)
            if raw_amount <= 0:
                raise ValueError("--amount-raw must be > 0")
        else:
            raw_amount = parse_human_amount_to_raw(str(args.amount), decimals)

        human_amount = format_units(raw_amount, decimals)
        tx_fields = build_tx_fields(sender=sender, receiver=receiver, token=token, raw_amount=raw_amount)
        estimated_gas = int(args.gas_limit, 0) if args.gas_limit else estimate_transaction_gas(tx_fields, rpc_url)
        if estimated_gas <= 0:
            raise RuntimeError("failed to estimate gas")
        estimated_fee_wei = estimated_gas * gas_price

        # Balance checks
        if token["address"] == "NATIVE":
            if raw_amount + estimated_fee_wei > native_balance_raw:
                raise RuntimeError("insufficient native balance for amount + gas")
        else:
            if raw_amount > token_balance_raw:
                raise RuntimeError("insufficient token balance")
            if estimated_fee_wei > native_balance_raw:
                raise RuntimeError("insufficient native balance to pay gas")

        confirmation = build_confirmation_phrase(chain.key, str(token["symbol"]), human_amount, receiver)
        response: dict[str, Any] = {
            "action": "wallet_transfer",
            "summary": {
                "chain": {"key": chain.key, "chainId": chain.chain_id},
                "from": sender,
                "to": receiver,
                "asset": token,
                "rawAmount": str(raw_amount),
                "humanAmount": human_amount,
                "transaction": {"to": tx_fields["to"], "value": tx_fields["value"], "data": tx_fields["data"]},
                "rpcUrlResolved": rpc_url,
            },
            "preflight": {
                "estimatedGas": str(estimated_gas),
                "gasPriceWei": str(gas_price),
                "estimatedFeeWei": str(estimated_fee_wei),
                "estimatedFeeNative": format_units(estimated_fee_wei, 18),
                "balances": {
                    "nativeRaw": str(native_balance_raw),
                    "nativeHuman": format_units(native_balance_raw, 18),
                    "assetRaw": str(token_balance_raw),
                    "assetHuman": format_units(token_balance_raw, decimals),
                },
            },
            "broadcastRequested": args.broadcast,
            "confirmation": confirmation,
        }

        if args.broadcast:
            if args.confirm != confirmation:
                raise ValueError(f"--confirm must exactly equal: {confirmation}")
            run_id = (
                os.environ.get("AUDIT_RUN_ID")
                or os.environ.get("STAGEFORGE_RUN_ID")
                or f"tx-{int(time.time())}-{os.getpid()}"
            )
            try:
                state_machine.transition(
                    run_id,
                    state_machine.STATE_PREFLIGHT,
                    payload={
                        "chain": chain.key,
                        "wallet": sender,
                        "token": token.get("symbol"),
                        "amount": human_amount,
                    },
                )
            except Exception:
                pass
            pre_broadcast = capture_balances(sender=sender, receiver=receiver, token=token, rpc_url=rpc_url)
            private_key, pk_source = resolve_private_key(args.private_key)
            response["signer"] = {"backend": "eth-account", "source": pk_source}
            log_event(
                event=EVENT_SIGN,
                chain=chain.key,
                wallet=sender,
                details={
                    "to": tx_fields["to"],
                    "rawAmount": str(raw_amount),
                    "asset": token.get("symbol"),
                    "gasLimit": estimated_gas,
                    "gasPriceWei": str(gas_price),
                },
            )
            try:
                state_machine.transition(run_id, state_machine.STATE_SIGNED)
            except Exception:
                pass
            broadcast_result = sign_and_broadcast(
                tx_fields=tx_fields,
                chain_id=chain.chain_id,
                gas_limit=estimated_gas,
                gas_price=gas_price,
                private_key=private_key,
                rpc_url=rpc_url,
            )
            response["broadcastResult"] = broadcast_result
            tx_hash = broadcast_result.get("transactionHash", "")
            log_event(
                event=EVENT_BROADCAST,
                chain=chain.key,
                wallet=sender,
                tx_hash=tx_hash or None,
                details={
                    "to": tx_fields["to"],
                    "rawAmount": str(raw_amount),
                    "asset": token.get("symbol"),
                },
            )
            try:
                state_machine.transition(run_id, state_machine.STATE_BROADCAST, payload={"tx_hash": tx_hash})
            except Exception:
                pass
            if tx_hash:
                response["transactionHash"] = tx_hash
                receipt = wait_for_transaction_receipt(
                    tx_hash,
                    rpc_url,
                    confirmations=max(1, int(args.receipt_confirmations)),
                )
                response["receipt"] = receipt
                response["success"] = receipt_succeeded(receipt)
                after = capture_balances(sender=sender, receiver=receiver, token=token, rpc_url=rpc_url)
                response["balanceCheck"] = {
                    "before": {k: str(v) for k, v in pre_broadcast.items()},
                    "after": {k: str(v) for k, v in after.items()},
                    "delta": {k: str(after[k] - pre_broadcast[k]) for k in pre_broadcast},
                }
                log_event(
                    event=EVENT_CONFIRM,
                    chain=chain.key,
                    wallet=sender,
                    tx_hash=tx_hash,
                    error_code=None if response["success"] else "receipt_failed",
                    details={
                        "confirmations": max(1, int(args.receipt_confirmations)),
                        "status": receipt.get("status"),
                    },
                )
                try:
                    state_machine.transition(run_id, state_machine.STATE_CONFIRMED)
                except Exception:
                    pass
        else:
            response["note"] = "dry-run only; pass --broadcast with --confirm to send"

        if args.output:
            Path(args.output).write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        dump_json(response)
    except Exception as exc:
        log_event(
            event=EVENT_ERROR,
            chain=getattr(args, "chain", None),
            wallet=getattr(args, "sender", None),
            error_code=type(exc).__name__,
            details={"message": str(exc), "action": "wallet_transfer"},
        )
        try:
            run_id = (
                os.environ.get("AUDIT_RUN_ID")
                or os.environ.get("STAGEFORGE_RUN_ID")
                or f"tx-{int(time.time())}-{os.getpid()}"
            )
            state_machine.transition(run_id, state_machine.STATE_FAILED, payload={"error_code": type(exc).__name__})
        except Exception:
            pass
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
