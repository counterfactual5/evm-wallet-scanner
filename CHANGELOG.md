# Changelog

## [0.1.0] — 2026-05-23

### Added
- Balance queries: native token + ERC20 balances via pure JSON-RPC
- Wallet overview: native + known ERC20 balances in one call
- Multi-chain summary: portfolio across 5 chains (Ethereum, Base, Arbitrum, Optimism, Polygon)
- Transaction history: normal, internal, and ERC20 transfers via Etherscan v2 API
- ERC20 transfer report: aggregated transfers with counterparty breakdown
- Counterparty analysis: find related addresses from transaction history
- Portfolio valuation: estimate wallet value from on-chain holdings
- Gas spend report: gas cost summary over time
- Transaction status: verify receipt and success by tx hash
- Token transfer: native and ERC20 transfers with dry-run (signing via optional eth-account)
- Chain aliases: `eth`, `arb`, `op`, `poly` shortcuts
- Public RPC fallback: auto-fallback when no RPC_URL is configured
- 36 tests covering imports, chains, addresses, formatting, RPC, and Etherscan
- GitHub Actions CI (Python 3.10, 3.11, 3.12)
- MIT License

[0.1.0]: https://github.com/counterfactual5/evm-wallet-scanner/releases/tag/v0.1.0
