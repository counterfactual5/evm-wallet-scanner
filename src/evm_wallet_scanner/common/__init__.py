"""Shared utilities — RPC calls, Etherscan API, formatting, address validation.

All chain interactions use pure JSON-RPC over urllib.  No external CLI
dependencies (cast, web3.py, etc.) are required.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
UTC = timezone.utc
from decimal import Decimal
from typing import Any

from evm_wallet_scanner.chains import CHAIN_BY_ID, CHAINS, ChainInfo, normalize_chain

# ── Constants ──────────────────────────────────────────────────────────────

ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

GLOBAL_RPC_ENV_CANDIDATES = ("ETH_RPC_URL", "RPC_URL")

ETHERSCAN_API_URL = "https://api.etherscan.io/v2/api"

ETHERSCAN_EMPTY_RESULT_MESSAGES = {
    "No transactions found",
    "No internal transactions found",
    "No token transfers found",
    "No records found",
}

# ERC-20 function selectors (keccak256 first 4 bytes, hardcoded)
_SELECTOR_DECIMALS = "0x313ce567"
_SELECTOR_SYMBOL = "0x95d89b41"
_SELECTOR_BALANCE_OF = "0x70a08231"
_SELECTOR_ALLOWANCE = "0xdd62ed3e"
_SELECTOR_TRANSFER = "0xa9059cbb"


# ── JSON-RPC ───────────────────────────────────────────────────────────────

def _json_rpc(method: str, params: list[Any], rpc_url: str, timeout: int = 30) -> Any:
    """Send a JSON-RPC request and return the ``result`` field."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf-8")
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())
    if body.get("error"):
        raise RuntimeError(f"RPC error: {body['error']}")
    return body.get("result")


def _decode_int(hex_or_int: Any) -> int:
    """Decode a hex string or int from RPC response."""
    if isinstance(hex_or_int, int):
        return hex_or_int
    if isinstance(hex_or_int, str):
        return int(hex_or_int, 0)
    raise ValueError(f"Cannot decode integer from {type(hex_or_int)}: {hex_or_int}")


def _encode_address(addr: str) -> str:
    """Left-pad address to 32 bytes (no 0x prefix)."""
    return addr.lower().replace("0x", "").rjust(64, "0")


def _encode_uint256(val: int) -> str:
    """Encode uint256 to 32-byte hex (no 0x prefix)."""
    return hex(val)[2:].rjust(64, "0")


# ── Address validation ────────────────────────────────────────────────────

def validate_address(value: str, field_name: str = "address") -> str:
    """Validate and return a checksummed-lowercase EVM address."""
    cleaned = value.strip()
    if not ADDRESS_RE.match(cleaned):
        raise ValueError(f"{field_name} is not a valid EVM address: {value}")
    return cleaned.lower()


# ── RPC URL resolution ────────────────────────────────────────────────────

def rpc_env_candidates(chain_id: int) -> list[str]:
    """Return environment variable names to check for an RPC URL."""
    chain = CHAIN_BY_ID.get(chain_id)
    candidates: list[str] = []
    if chain:
        key = chain.key.upper()
        candidates.extend([f"{key}_RPC_URL", f"RPC_URL_{key}", f"{key}_MAINNET_RPC_URL"])
    candidates.extend(GLOBAL_RPC_ENV_CANDIDATES)
    deduped: list[str] = []
    for c in candidates:
        if c not in deduped:
            deduped.append(c)
    return deduped


def resolve_rpc_url(explicit_rpc_url: str | None, chain_id: int) -> tuple[str, list[str]]:
    """Resolve RPC URL from explicit value, env vars, or chain defaults."""
    if explicit_rpc_url:
        return explicit_rpc_url, []
    candidates = rpc_env_candidates(chain_id)
    for env_name in candidates:
        value = os.environ.get(env_name)
        if value:
            return value, candidates
    # Fall back to public RPC
    chain = CHAIN_BY_ID.get(chain_id)
    if chain and chain.rpc_url:
        return chain.rpc_url, candidates
    raise RuntimeError(
        f"RPC URL is not configured; set one of {', '.join(candidates)} or pass --rpc-url"
    )


# ── On-chain queries (pure JSON-RPC) ──────────────────────────────────────

def query_native_balance(address: str, rpc_url: str) -> int:
    """Query native token balance (wei) via eth_getBalance."""
    result = _json_rpc("eth_getBalance", [address, "latest"], rpc_url)
    return _decode_int(result)


def query_erc20_balance(owner: str, token: str, rpc_url: str) -> int:
    """Query ERC-20 balanceOf via eth_call."""
    data = _SELECTOR_BALANCE_OF + _encode_address(owner)
    result = _json_rpc("eth_call", [{"to": token, "data": "0x" + data}, "latest"], rpc_url)
    return _decode_int(result)


def query_erc20_allowance(token: str, owner: str, spender: str, rpc_url: str) -> int:
    """Query ERC-20 allowance via eth_call."""
    data = _SELECTOR_ALLOWANCE + _encode_address(owner) + _encode_address(spender)
    result = _json_rpc("eth_call", [{"to": token, "data": "0x" + data}, "latest"], rpc_url)
    return _decode_int(result)


def query_token_decimals(token: str, rpc_url: str) -> int:
    """Query ERC-20 decimals() via eth_call."""
    result = _json_rpc("eth_call", [{"to": token, "data": _SELECTOR_DECIMALS}, "latest"], rpc_url)
    return _decode_int(result)


def query_token_symbol(token: str, rpc_url: str) -> str | None:
    """Query ERC-20 symbol() via eth_call."""
    try:
        raw = _json_rpc("eth_call", [{"to": token, "data": _SELECTOR_SYMBOL}, "latest"], rpc_url)
    except RuntimeError:
        return None
    if raw is None:
        return None
    try:
        return _decode_string(raw)
    except Exception:
        return raw.replace("0x", "")[:8]


def _decode_string(hex_val: str) -> str:
    """Decode a dynamic string from ABI-encoded hex return."""
    clean = hex_val.replace("0x", "")
    if len(clean) < 128:
        return ""
    length = int(clean[64:128], 16)
    hex_str = clean[128:128 + length * 2]
    return bytes.fromhex(hex_str).decode("utf-8", errors="replace")


def estimate_transaction_gas(tx: dict[str, str], rpc_url: str) -> int:
    """Estimate gas for a transaction via eth_estimateGas."""
    params: dict[str, str] = {
        "to": tx["to"],
        "data": tx["data"],
        "value": hex(int(tx["value"])),
    }
    if tx.get("from"):
        params["from"] = tx["from"]
    result = _json_rpc("eth_estimateGas", [params], rpc_url)
    return _decode_int(result)


def query_gas_price(rpc_url: str) -> int:
    """Query current gas price via eth_gasPrice."""
    result = _json_rpc("eth_gasPrice", [], rpc_url)
    return _decode_int(result)


def get_transaction_receipt(tx_hash: str, rpc_url: str) -> dict[str, Any]:
    """Get transaction receipt via eth_getTransactionReceipt."""
    result = _json_rpc("eth_getTransactionReceipt", [tx_hash], rpc_url)
    if result is None:
        raise RuntimeError(f"Receipt not found for tx {tx_hash}")
    return result


def receipt_succeeded(receipt: dict[str, Any]) -> bool:
    """Check if a receipt indicates success."""
    status = receipt.get("status")
    if isinstance(status, str):
        return status.lower() in {"0x1", "1"}
    if isinstance(status, int):
        return status == 1
    return False


# ── Etherscan API ─────────────────────────────────────────────────────────

def require_etherscan_api_key() -> str:
    """Return ETHERSCAN_API_KEY from env or raise."""
    api_key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ETHERSCAN_API_KEY is not configured")
    return api_key


def etherscan_request(
    *,
    chain_id: int,
    module: str,
    action: str,
    api_key: str,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a request to the Etherscan API (v2) and return the parsed result."""
    params: dict[str, str] = {
        "chainid": str(chain_id),
        "module": module,
        "action": action,
        "apikey": api_key,
    }
    if extra_params:
        for key, value in extra_params.items():
            if value is None:
                continue
            params[key] = str(value)
    url = ETHERSCAN_API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Etherscan request failed for {module}.{action}: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Etherscan {module}.{action} returned non-object JSON")
    status = str(payload.get("status", ""))
    message = str(payload.get("message", ""))
    result = payload.get("result")
    if status == "1":
        return payload
    if isinstance(result, str) and result in ETHERSCAN_EMPTY_RESULT_MESSAGES:
        payload["result"] = []
        return payload
    if module == "logs" and action == "getLogs" and isinstance(result, list) and len(result) == 0:
        payload["result"] = []
        return payload
    details = [m for m in [message, str(result) if result not in (None, "") else ""] if m]
    raise RuntimeError(f"Etherscan {module}.{action} error: {' | '.join(details)}")


def get_block_by_timestamp(chain_id: int, timestamp: int, closest: str, api_key: str) -> int:
    """Get block number by timestamp via Etherscan."""
    payload = etherscan_request(
        chain_id=chain_id,
        module="block",
        action="getblocknobytime",
        api_key=api_key,
        extra_params={"timestamp": timestamp, "closest": closest},
    )
    result = payload.get("result")
    try:
        return int(str(result), 0)
    except ValueError as exc:
        raise RuntimeError(f"invalid block number returned by Etherscan: {result}") from exc


# ── Formatting helpers ────────────────────────────────────────────────────

def format_units(raw_value: int, decimals: int) -> str:
    """Convert a raw uint256 value to a human-readable decimal string."""
    scaled = Decimal(raw_value) / (Decimal(10) ** decimals)
    text = format(scaled, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def iso_from_timestamp(value: str | int | None) -> str | None:
    """Convert a unix timestamp (string or int) to ISO 8601."""
    if value in (None, "", "0x0", "0"):
        return None
    try:
        timestamp = int(str(value), 0)
    except ValueError:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def dump_json(obj: Any) -> None:
    """Pretty-print a JSON object to stdout."""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ── Direction helpers ─────────────────────────────────────────────────────

def normalize_direction(wallet: str, from_address: str | None, to_address: str | None) -> str:
    """Determine if a transaction is 'in', 'out', 'self', or 'other'."""
    owner = wallet.lower()
    source = (from_address or "").lower()
    target = (to_address or "").lower()
    if source == owner and target == owner:
        return "self"
    if source == owner:
        return "out"
    if target == owner:
        return "in"
    return "other"


# ── Token resolution ──────────────────────────────────────────────────────

def resolve_query_token(
    chain_name: str,
    token_name: str | None,
    token_decimals: int | None,
    rpc_url: str,
) -> dict[str, Any]:
    """Resolve a token name/address to a dict with kind, symbol, address, decimals."""
    chain = normalize_chain(chain_name)
    if not token_name:
        return {
            "kind": "native",
            "symbol": chain.native_symbol,
            "address": "NATIVE",
            "decimals": 18,
        }

    token_upper = token_name.strip().upper()

    # Native token
    if token_upper in ("NATIVE", chain.native_symbol, chain.wrapped_native_symbol.replace("W", "")):
        if token_upper == chain.wrapped_native_symbol:
            # WETH etc — not native, fall through to address resolution
            pass
        elif token_upper == "NATIVE" or token_upper == chain.native_symbol:
            return {
                "kind": "native",
                "symbol": chain.native_symbol,
                "address": "NATIVE",
                "decimals": 18,
            }

    # If it's an address, resolve on-chain metadata
    if token_name.startswith("0x"):
        address = validate_address(token_name, "token-address")
        decimals = token_decimals if token_decimals is not None else query_token_decimals(address, rpc_url)
        symbol = query_token_symbol(address, rpc_url) or "UNKNOWN"
        return {
            "kind": "erc20",
            "symbol": symbol,
            "address": address,
            "decimals": decimals,
        }

    # Symbol — resolve on-chain
    return {
        "kind": "erc20",
        "symbol": token_name,
        "address": token_name,  # Caller should provide contract address for symbol resolution
        "decimals": token_decimals or 18,
    }


# ── Balance entry builder ─────────────────────────────────────────────────

def build_balance_entry(
    chain_name: str,
    wallet: str,
    token_name: str | None,
    token_decimals: int | None,
    explicit_rpc_url: str | None,
) -> dict[str, Any]:
    """Build a complete balance entry dict for a wallet + token pair."""
    chain = normalize_chain(chain_name)
    wallet_address = validate_address(wallet, "wallet")
    rpc_url, rpc_candidates = resolve_rpc_url(explicit_rpc_url, chain.chain_id)
    token = resolve_query_token(chain.key, token_name, token_decimals, rpc_url)

    if token["address"] == "NATIVE":
        raw_balance = query_native_balance(wallet_address, rpc_url)
    else:
        raw_balance = query_erc20_balance(wallet_address, token["address"], rpc_url)

    return {
        "chain": {"key": chain.key, "chainId": chain.chain_id},
        "wallet": wallet_address,
        "asset": token,
        "rawBalance": str(raw_balance),
        "humanBalance": format_units(raw_balance, int(token["decimals"])),
        "rpcUrlResolved": rpc_url,
        "rpcEnvCandidates": rpc_candidates,
    }
