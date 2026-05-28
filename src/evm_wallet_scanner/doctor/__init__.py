"""Preflight doctor — pre-trade health check aggregator.

Runs a fixed battery of read-only checks against an RPC endpoint and a wallet
to surface "is this environment trade-ready?" in a single call. Designed to be
imported by other projects (uniswap-autopilot, polymarket-autopilot, etc.) so
they can reuse the same checks instead of re-implementing them inline.

Public entry point: ``run_preflight`` returns a structured report. The CLI
wrapper lives in :mod:`evm_wallet_scanner.doctor.cli`.
"""

from evm_wallet_scanner.doctor.preflight import (
    PreflightCheck,
    PreflightReport,
    run_preflight,
)

__all__ = ["PreflightCheck", "PreflightReport", "run_preflight"]
