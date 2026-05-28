"""CLI wrapper for ``run_preflight``.

Kept in its own module so other entry points can import either the structured
report (``preflight.run_preflight``) or the CLI driver (``doctor_main``).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from evm_wallet_scanner.audit import EVENT_PREFLIGHT, log_event
from evm_wallet_scanner.doctor.preflight import (
    STATUS_ERROR,
    STATUS_FAIL,
    STATUS_WARN,
    run_preflight,
)


def _parse_int_amount(value: str | None, *, field: str) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value, 0)
    except ValueError as exc:
        raise SystemExit(f"--{field} must be an integer in base 10 or hex; got {value!r}") from exc


def doctor_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evm-scan doctor",
        description=(
            "Preflight health check for a wallet on a given chain. "
            "Checks RPC reachability, chain id, native balance, nonce, gas price, "
            "and optionally token balance + allowance + signer env."
        ),
    )
    parser.add_argument("--chain", required=True, help="Chain key (ethereum, base, arbitrum, optimism, polygon)")
    parser.add_argument("--wallet", required=True, help="Wallet address (0x...)")
    parser.add_argument("--rpc-url", help="Override RPC URL")
    parser.add_argument("--token", dest="token_address", help="Optional ERC-20 token contract address to inspect")
    parser.add_argument("--spender", help="Spender address to verify allowance against (requires --token)")
    parser.add_argument(
        "--required-allowance-raw",
        default="0",
        help="Required allowance in raw token units (uint256, base 10 or 0x hex)",
    )
    parser.add_argument(
        "--min-native-wei",
        default=str(5 * 10**14),
        help="Minimum native balance in wei before warning (default: 0.0005 native)",
    )
    parser.add_argument(
        "--min-token-balance-raw",
        default="0",
        help="Minimum token balance in raw units before warning",
    )
    parser.add_argument(
        "--signer-env",
        action="append",
        dest="signer_envs",
        help="Env var name(s) to check for signer key. May be repeated. "
        "Default: HOT_WALLET_PRIVATE_KEY, EXECUTOR_PRIVATE_KEY, PRIVATE_KEY",
    )
    parser.add_argument("--output", help="Write JSON report to file (otherwise stdout)")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit non-zero when any check fails (otherwise always 0)",
    )

    args = parser.parse_args(argv)

    report = run_preflight(
        chain=args.chain,
        wallet=args.wallet,
        rpc_url=args.rpc_url,
        token_address=args.token_address,
        spender=args.spender,
        required_allowance_raw=_parse_int_amount(args.required_allowance_raw, field="required-allowance-raw"),
        min_native_wei=_parse_int_amount(args.min_native_wei, field="min-native-wei"),
        min_token_balance_raw=_parse_int_amount(args.min_token_balance_raw, field="min-token-balance-raw"),
        signer_env_candidates=args.signer_envs,
    )

    payload: dict[str, Any] = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.write("\n")
    else:
        print(text)

    failed = [c.name for c in report.checks if c.status in {STATUS_FAIL, STATUS_ERROR}]
    log_event(
        event=EVENT_PREFLIGHT,
        chain=report.chain,
        wallet=report.wallet,
        error_code=None if report.ok else "preflight_failed",
        details={
            "ok": report.ok,
            "failedChecks": failed,
            "rpcUrl": report.rpc_url,
            "chainId": report.chain_id,
        },
    )

    if args.exit_code:
        bad = [c for c in report.checks if c.status in {STATUS_FAIL, STATUS_ERROR}]
        if bad:
            return 2
        warn = [c for c in report.checks if c.status == STATUS_WARN]
        if warn:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(doctor_main())
