"""Preflight checks for trade-readiness.

Every check is an independent function so individual failures cannot cascade.
The aggregator catches exceptions per-check and records them as
``status="error"`` entries rather than aborting the whole report — callers
should look at ``report.ok`` to decide whether to proceed.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from evm_wallet_scanner import common as _common
from evm_wallet_scanner.chains import CHAIN_BY_ID, normalize_chain
from evm_wallet_scanner.common import (
    query_erc20_allowance,
    query_erc20_balance,
    query_gas_price,
    query_native_balance,
    query_token_decimals,
    query_token_symbol,
    resolve_rpc_url,
    validate_address,
)

# Status constants — kept as bare strings for cross-language consumability.
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_ERROR = "error"
STATUS_SKIP = "skip"


@dataclass
class PreflightCheck:
    """One row in the preflight report."""

    name: str
    status: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int = 0


@dataclass
class PreflightReport:
    """Aggregate result of a preflight run."""

    ok: bool
    chain: str
    chain_id: int
    wallet: str
    rpc_url: str
    checks: list[PreflightCheck]
    started_at: float
    finished_at: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [asdict(c) for c in self.checks]
        return data


# ── individual checks ──────────────────────────────────────────────────────


def _timed(fn: Callable[[], PreflightCheck]) -> PreflightCheck:
    """Run a check function and stamp ``elapsed_ms`` onto its result.

    Exceptions are converted into ``STATUS_ERROR`` rows so one bad check
    cannot abort the whole report.
    """
    start = time.monotonic()
    try:
        check = fn()
    except Exception as exc:  # noqa: BLE001 — we explicitly want a catch-all here
        return PreflightCheck(
            name=getattr(fn, "__name__", "unknown"),
            status=STATUS_ERROR,
            summary=f"check raised {type(exc).__name__}: {exc}",
            details={"errorType": type(exc).__name__},
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
    check.elapsed_ms = int((time.monotonic() - start) * 1000)
    return check


def check_rpc_reachable(rpc_url: str) -> PreflightCheck:
    block_hex = _common._json_rpc("eth_blockNumber", [], rpc_url, timeout=10)
    block = int(block_hex, 0) if isinstance(block_hex, str) else int(block_hex)
    return PreflightCheck(
        name="rpc_reachable",
        status=STATUS_OK,
        summary=f"rpc reachable at block {block}",
        details={"latestBlock": block},
    )


def check_chain_id_matches(rpc_url: str, expected_chain_id: int) -> PreflightCheck:
    raw = _common._json_rpc("eth_chainId", [], rpc_url, timeout=10)
    actual = int(raw, 0) if isinstance(raw, str) else int(raw)
    if actual != expected_chain_id:
        return PreflightCheck(
            name="chain_id_matches",
            status=STATUS_FAIL,
            summary=f"rpc reports chain_id={actual}, expected {expected_chain_id}",
            details={"actualChainId": actual, "expectedChainId": expected_chain_id},
        )
    return PreflightCheck(
        name="chain_id_matches",
        status=STATUS_OK,
        summary=f"chain_id={actual}",
        details={"actualChainId": actual, "expectedChainId": expected_chain_id},
    )


def check_native_balance(
    wallet: str, rpc_url: str, min_balance_wei: int
) -> PreflightCheck:
    balance = query_native_balance(wallet, rpc_url)
    if balance <= 0:
        return PreflightCheck(
            name="native_balance",
            status=STATUS_FAIL,
            summary="wallet has zero native balance; cannot pay gas",
            details={"balanceWei": str(balance), "minBalanceWei": str(min_balance_wei)},
        )
    if balance < min_balance_wei:
        return PreflightCheck(
            name="native_balance",
            status=STATUS_WARN,
            summary=f"native balance {balance} wei below threshold {min_balance_wei}",
            details={"balanceWei": str(balance), "minBalanceWei": str(min_balance_wei)},
        )
    return PreflightCheck(
        name="native_balance",
        status=STATUS_OK,
        summary=f"native balance {balance} wei",
        details={"balanceWei": str(balance), "minBalanceWei": str(min_balance_wei)},
    )


def check_pending_nonce(wallet: str, rpc_url: str) -> PreflightCheck:
    raw = _common._json_rpc("eth_getTransactionCount", [wallet, "pending"], rpc_url, timeout=10)
    nonce = int(raw, 0) if isinstance(raw, str) else int(raw)
    return PreflightCheck(
        name="pending_nonce",
        status=STATUS_OK,
        summary=f"pending nonce={nonce}",
        details={"nonce": nonce},
    )


def check_gas_price(rpc_url: str) -> PreflightCheck:
    gas_price = query_gas_price(rpc_url)
    return PreflightCheck(
        name="gas_price",
        status=STATUS_OK if gas_price > 0 else STATUS_WARN,
        summary=f"eth_gasPrice={gas_price} wei",
        details={"gasPriceWei": str(gas_price)},
    )


def check_token_balance(
    wallet: str, token_address: str, rpc_url: str, min_balance_raw: int
) -> PreflightCheck:
    address = validate_address(token_address, "token-address")
    balance = query_erc20_balance(wallet, address, rpc_url)
    decimals = 0
    symbol: str | None = None
    try:
        decimals = query_token_decimals(address, rpc_url)
    except Exception:  # noqa: BLE001 — decimals/symbol are decorative
        decimals = 0
    try:
        symbol = query_token_symbol(address, rpc_url)
    except Exception:  # noqa: BLE001
        symbol = None
    details = {
        "token": address,
        "symbol": symbol,
        "decimals": decimals,
        "balanceRaw": str(balance),
        "minBalanceRaw": str(min_balance_raw),
    }
    if balance <= 0:
        return PreflightCheck(
            name="token_balance",
            status=STATUS_FAIL,
            summary=f"token {symbol or address} balance is zero",
            details=details,
        )
    if balance < min_balance_raw:
        return PreflightCheck(
            name="token_balance",
            status=STATUS_WARN,
            summary=f"token {symbol or address} balance below threshold",
            details=details,
        )
    return PreflightCheck(
        name="token_balance",
        status=STATUS_OK,
        summary=f"token {symbol or address} balance ok",
        details=details,
    )


def check_allowance(
    wallet: str,
    token_address: str,
    spender: str,
    rpc_url: str,
    required_allowance_raw: int,
) -> PreflightCheck:
    token = validate_address(token_address, "token-address")
    spender_addr = validate_address(spender, "spender")
    allowance = query_erc20_allowance(token, wallet, spender_addr, rpc_url)
    details = {
        "token": token,
        "spender": spender_addr,
        "allowanceRaw": str(allowance),
        "requiredAllowanceRaw": str(required_allowance_raw),
    }
    if allowance >= required_allowance_raw:
        return PreflightCheck(
            name="allowance",
            status=STATUS_OK,
            summary="allowance is sufficient",
            details=details,
        )
    if allowance == 0:
        return PreflightCheck(
            name="allowance",
            status=STATUS_FAIL,
            summary="allowance is zero; approve required before swap",
            details=details,
        )
    return PreflightCheck(
        name="allowance",
        status=STATUS_FAIL,
        summary="allowance is below required amount; top up via approve",
        details=details,
    )


def check_signer_env(env_candidates: list[str]) -> PreflightCheck:
    """Verify at least one signer env var is populated (without leaking value)."""
    for name in env_candidates:
        if (os.environ.get(name) or "").strip():
            return PreflightCheck(
                name="signer_env",
                status=STATUS_OK,
                summary=f"signer env populated: {name}",
                details={"candidates": env_candidates, "matched": name},
            )
    return PreflightCheck(
        name="signer_env",
        status=STATUS_WARN,
        summary="no signer env var populated; broadcast paths will fail",
        details={"candidates": env_candidates, "matched": None},
    )


# ── aggregator ─────────────────────────────────────────────────────────────


# Default native-balance threshold: 0.0005 of the native unit (1e15 wei for 18-dec chains).
# This is intentionally small — we want a "you have at least *some* gas" check,
# not a portfolio-style threshold.
_DEFAULT_MIN_NATIVE_WEI = 5 * 10**14


def run_preflight(
    *,
    chain: str,
    wallet: str,
    rpc_url: str | None = None,
    token_address: str | None = None,
    spender: str | None = None,
    required_allowance_raw: int = 0,
    min_native_wei: int = _DEFAULT_MIN_NATIVE_WEI,
    min_token_balance_raw: int = 0,
    signer_env_candidates: list[str] | None = None,
) -> PreflightReport:
    """Run the full preflight battery and return a structured report.

    The report's ``ok`` flag is True iff every check is ``ok``, ``skip``, or
    ``warn``. A single ``fail`` or ``error`` flips it to False — callers should
    treat that as "do not broadcast".
    """
    started_at = time.time()
    chain_info = normalize_chain(chain)
    wallet_addr = validate_address(wallet, "wallet")
    resolved_rpc, _candidates = resolve_rpc_url(rpc_url, chain_info.chain_id)
    chain_record = CHAIN_BY_ID.get(chain_info.chain_id)
    chain_key = chain_record.key if chain_record else chain_info.key

    if signer_env_candidates is None:
        # Mirror the env-var conventions used by transfer/uniswap-autopilot.
        signer_env_candidates = [
            "HOT_WALLET_PRIVATE_KEY",
            "EXECUTOR_PRIVATE_KEY",
            "PRIVATE_KEY",
        ]

    checks: list[PreflightCheck] = []

    checks.append(_timed(lambda: check_rpc_reachable(resolved_rpc)))
    checks.append(
        _timed(lambda: check_chain_id_matches(resolved_rpc, chain_info.chain_id))
    )
    checks.append(_timed(lambda: check_gas_price(resolved_rpc)))
    checks.append(
        _timed(
            lambda: check_native_balance(
                wallet_addr, resolved_rpc, min_native_wei
            )
        )
    )
    checks.append(_timed(lambda: check_pending_nonce(wallet_addr, resolved_rpc)))

    if token_address:
        checks.append(
            _timed(
                lambda: check_token_balance(
                    wallet_addr,
                    token_address,
                    resolved_rpc,
                    min_token_balance_raw,
                )
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="token_balance",
                status=STATUS_SKIP,
                summary="no --token provided",
            )
        )

    if token_address and spender:
        checks.append(
            _timed(
                lambda: check_allowance(
                    wallet_addr,
                    token_address,
                    spender,
                    resolved_rpc,
                    required_allowance_raw,
                )
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="allowance",
                status=STATUS_SKIP,
                summary="no --token/--spender provided",
            )
        )

    checks.append(_timed(lambda: check_signer_env(signer_env_candidates)))

    overall_ok = all(c.status in {STATUS_OK, STATUS_SKIP, STATUS_WARN} for c in checks)
    finished_at = time.time()

    return PreflightReport(
        ok=overall_ok,
        chain=chain_key,
        chain_id=chain_info.chain_id,
        wallet=wallet_addr,
        rpc_url=resolved_rpc,
        checks=checks,
        started_at=started_at,
        finished_at=finished_at,
    )
