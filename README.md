<p align="center">
  <img src="https://img.shields.io/badge/EVM-Wallet--Scanner-4A90E2?style=for-the-badge&logo=ethereum&logoColor=white" alt="EVM Wallet Scanner" />
</p>

<h1 align="center">🔍 EVM Wallet Scanner</h1>

<p align="center">
  <strong>Zero dependencies · Pure Python · Multi-chain</strong><br/>
  Balance queries, transaction history, transfer reports, portfolio valuation, gas analytics
</p>

<p align="center">
  <a href="https://pypi.org/project/evm-wallet-scanner/"><img src="https://img.shields.io/badge/python-%E2%89%A53.10-blue" alt="Python"></a>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero Deps">
  <a href="https://github.com/counterfactual5/evm-wallet-scanner/actions/workflows/test.yml"><img src="https://github.com/counterfactual5/evm-wallet-scanner/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
</p>

---

## ⚡ Quick Start

```bash
pip install evm-wallet-scanner

# Query ETH balance
evm-scan balance --chain ethereum --wallet 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

# Query USDC balance on Base
evm-scan balance --chain base --wallet 0x... --token USDC

# Multi-chain portfolio summary
evm-scan multichain --wallet 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
```

### Python API

```python
from evm_wallet_scanner.common import build_balance_entry, dump_json

# Query native balance on Ethereum
result = build_balance_entry(
    chain_name="ethereum",
    wallet="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    token_name=None,  # None = native ETH
    token_decimals=None,
    explicit_rpc_url=None,
)
print(result["humanBalance"])  # e.g. "3.14"

# Query ERC20 balance
usdc = build_balance_entry("ethereum", "0x...", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", None, None)
print(usdc["humanBalance"])  # e.g. "50000"
```

---

## 📋 Core Modules

| Module | Description |
|--------|-------------|
| **balance** | Single token/native balance query |
| **overview** | Native + known ERC20 balances for one wallet |
| **multichain** | Portfolio overview across 5 chains in one call |
| **history** | Normal transactions, internal txs, ERC20 transfers |
| **transfer-report** | Aggregated ERC20 transfer report with counterparty breakdown |
| **counterparties** | Identify related addresses from transaction history |
| **portfolio** | Estimate wallet value from on-chain holdings |
| **gas-report** | Gas spend summary over time |
| **tx-status** | Verify transaction status by hash |
| **transfer** | Build & execute native/ERC20 transfers (dry-run supported) |

### Usage Examples

```bash
# Transaction history
evm-scan history --chain ethereum --wallet 0x...

# ERC20 transfer report (last 30 days)
evm-scan transfer-report --chain base --wallet 0x...

# Counterparty analysis
evm-scan counterparties --chain ethereum --wallet 0x...

# Portfolio valuation
evm-scan portfolio --chain ethereum --wallet 0x...

# Gas spend report
evm-scan gas-report --chain ethereum --wallet 0x...

# Transaction status
evm-scan tx-status --chain base --tx-hash 0x...

# Transfer — dry-run (default; no signing, no broadcast)
evm-scan transfer --chain ethereum --from 0xSENDER --to 0xRECIPIENT --amount 0.01

# Transfer — broadcast (requires --confirm to match the printed phrase)
evm-scan transfer --chain ethereum --from 0xSENDER --to 0xRECIPIENT --amount 0.01 \
  --broadcast --confirm "TRANSFER ethereum ETH 0.01 TO 0xRECIPIENT"
```

> Broadcasting requires the optional `signer` extra: `pip install "evm-wallet-scanner[signer]"`.
> Provide the private key via the `HOT_WALLET_PRIVATE_KEY` (or `PRIVATE_KEY`) env var; `--private-key` is supported but leaks the key into the process list, so it is discouraged.

### Example Output

```
$ evm-scan multichain --wallet 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045

  Ethereum:         3.14 ETH
    USDC:          50,000.00
    USDT:          25,000.00
  Base:             0.85 ETH
    USDC:          12,500.00
  Arbitrum:         1.20 ETH
  Optimism:         0.42 ETH
  Polygon:          0.00 MATIC
```

---

## 🔗 Supported Chains

| Chain | Chain ID | Public RPC (fallback) |
|-------|----------|----------------------|
| Ethereum | 1 | eth.llamarpc.com |
| Base | 8453 | mainnet.base.org |
| Arbitrum | 42161 | arb1.arbitrum.io/rpc |
| Optimism | 10 | mainnet.optimism.io |
| Polygon | 137 | polygon-rpc.com |

Use `--chain eth`, `--chain arb`, `--chain op` for short aliases.

---

## 📦 Installation

```bash
pip install evm-wallet-scanner

# With signing support (eth-account for transfers)
pip install "evm-wallet-scanner[signer]"
```

## ⚙️ Configuration

```bash
# Required for history/counterparties/portfolio (Etherscan API)
export ETHERSCAN_API_KEY="your-api-key"

# RPC URL (auto-detected; falls back to public RPC if unset)
export ETHEREUM_RPC_URL="https://eth.llamarpc.com"
export BASE_RPC_URL="https://mainnet.base.org"
# ... or use a generic fallback
export RPC_URL="https://eth.llamarpc.com"
```

If no RPC_URL is set, the scanner falls back to built-in public RPC endpoints — no config needed for basic queries.

---

## 🛡️ Security

- **Read-only by default**: Balance, history, portfolio, gas-report, tx-status are all read-only
- **Transfer is opt-in**: Requires `--dry-run` confirmation; signing needs `eth-account` extra
- **No private keys**: Private keys are never stored, logged, or required
- **Zero dependencies**: Standard library only — minimal attack surface

---

## 🛠️ Development

```bash
git clone https://github.com/counterfactual5/evm-wallet-scanner.git
cd evm-wallet-scanner
uv pip install -e ".[dev]"
uv run pytest tests/ -v
```

36 tests covering imports, chains, addresses, formatting, RPC resolution, on-chain queries (mocked), and Etherscan requests.

---

## 🗺️ Roadmap

- [x] Multi-chain balance queries (native + ERC20)
- [x] Transaction history & transfer reports
- [x] Counterparty analysis
- [x] Portfolio valuation & gas reports
- [x] Transaction status verification
- [x] Transfer with dry-run
- [ ] Async parallel queries (asyncio stdlib)
- [ ] CSV export for all report types
- [ ] NFT holdings scanner
- [ ] WebSocket real-time balance monitoring

---

## 📄 License

[MIT](LICENSE) © 2026 counterfactual5

---

If this project helped you, please ⭐ star this repo — it helps others find it!
