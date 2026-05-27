"""Chain definitions for supported EVM networks.

Each chain entry contains the chain ID, native symbol, wrapped native symbol,
and a public RPC URL.  Token catalogs are intentionally minimal — the scanner
auto-discovers tokens on-chain via ERC-20 metadata calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChainInfo:
    key: str
    chain_id: int
    native_symbol: str
    wrapped_native_symbol: str
    rpc_url: str


CHAINS: dict[str, ChainInfo] = {
    "ethereum": ChainInfo(
        key="ethereum",
        chain_id=1,
        native_symbol="ETH",
        wrapped_native_symbol="WETH",
        rpc_url="https://eth.llamarpc.com",
    ),
    "base": ChainInfo(
        key="base",
        chain_id=8453,
        native_symbol="ETH",
        wrapped_native_symbol="WETH",
        rpc_url="https://mainnet.base.org",
    ),
    "arbitrum": ChainInfo(
        key="arbitrum",
        chain_id=42161,
        native_symbol="ETH",
        wrapped_native_symbol="WETH",
        rpc_url="https://arb1.arbitrum.io/rpc",
    ),
    "optimism": ChainInfo(
        key="optimism",
        chain_id=10,
        native_symbol="ETH",
        wrapped_native_symbol="WETH",
        rpc_url="https://mainnet.optimism.io",
    ),
    "polygon": ChainInfo(
        key="polygon",
        chain_id=137,
        native_symbol="MATIC",
        wrapped_native_symbol="WMATIC",
        rpc_url="https://polygon-rpc.com",
    ),
}

CHAIN_BY_ID: dict[int, ChainInfo] = {c.chain_id: c for c in CHAINS.values()}

# Chain aliases for flexible lookup
_CHAIN_ALIASES: dict[str, str] = {
    "eth": "ethereum",
    "arb": "arbitrum",
    "op": "optimism",
    "poly": "polygon",
    "matic": "polygon",
}


def normalize_chain(name: str) -> ChainInfo:
    """Resolve a chain name (case-insensitive, with aliases) to a ChainInfo."""
    key = name.strip().lower()
    key = _CHAIN_ALIASES.get(key, key)
    chain = CHAINS.get(key)
    if chain is None:
        supported = ", ".join(sorted(CHAINS.keys()))
        raise ValueError(f"unknown chain '{name}'; supported: {supported}")
    return chain
