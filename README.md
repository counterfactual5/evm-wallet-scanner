<p align="center">
  <img src="https://img.shields.io/badge/EVM-Wallet--Scanner-blueviolet?style=for-the-badge&logo=ethereum" alt="EVM Wallet Scanner" />
</p>

<h1 align="center">🔍 EVM Wallet Scanner</h1>

<p align="center">
  <strong>Zero-dependency EVM wallet scanner</strong><br/>
  Balances · History · Transfers · Portfolio · Gas Reports · TX Status<br/>
  <em>5 chains, pure Python, no web3.py, no Foundry</em>
</p>

<p align="center">
  <img src="https://img.shields.io/pypi/pyversions/evm-wallet-scanner" alt="Python" />
  <img src="https://img.shields.io/pypi/l/evm-wallet-scanner" alt="License" />
  <img src="https://img.shields.io/github/actions/workflow/status/counterfactual5/evm-wallet-scanner/test.yml?branch=main" alt="CI" />
</p>

---

## ✨ Why EVM Wallet Scanner?

| Feature | EVM Wallet Scanner | web3.py | Manual Etherscan |
|---------|:------------------:|:-------:|:----------------:|
| **Zero dependencies** | ✅ | ❌ (heavy deps) | N/A |
| **Pure Python stdlib** | ✅ | ❌ | N/A |
| **Multi-chain balance query** | ✅ | Write it yourself | Tab hell |
| **TX history (normal + internal + ERC20)** | ✅ | Write it yourself | Manual API calls |
| **Counterparty analysis** | ✅ | ❌ | ❌ |
| **Portfolio valuation** | ✅ | ❌ | ❌ |
| **Gas reports by day** | ✅ | ❌ | ❌ |
| **Transfer with dry-run** | ✅ | ✅ | ❌ |
| **No API key required** (balance queries) | ✅ | ✅ | ❌ |
| **Install size** | ~50 KB | ~10 MB | — |

---

## 🚀 Quick Start

```bash
pip install evm-wallet-scanner
```

### Check a Balance (5 lines)

```python
from evm_wallet_scanner.common import build_balance_entry

result = build_balance_entry(
    chain_name="ethereum",
    wallet="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    token_name=None,  # native ETH
    token_decimals=None,
    explicit_rpc_url=None,
)
print(f"Balance: {result['humanBalance']} ETH")
```

### Query Transaction History

```python
from evm_wallet_scanner.common import etherscan_request, normalize_chain, require_etherscan_api_key

chain = normalize_chain("base")
api_key = require_etherscan_api_key()
payload = etherscan_request(
    chain_id=chain.chain_id,
    module="account",
    action="txlist",
    api_key=api_key,
    extra_params={"address": "0xYourWallet", "page": 1, "offset": 10, "sort": "desc"},
)
for tx in payload.get("result", []):
    print(f"{tx['hash'][:16]}... value={tx['value']} wei")
```

### Multi-Chain Summary

```python
from evm_wallet_scanner.balances.wallet_multichain_summary import query_chain_assets

result = query_chain_assets(
    chain_name="ethereum",
    wallet="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    tokens=["USDC", "WETH", "USDT"],
)
for asset in result["assets"]:
    print(f"{asset['symbol']}: {asset['humanBalance']}")
```

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────┐
│                   evm_wallet_scanner                  │
├──────────┬──────────┬──────────┬──────────┬──────────┤
│ balances │ history  │ transfer │ portfolio│  status  │
│          │          │          │          │          │
│ balance  │ history  │ transfer │ portfolio│ tx_status│
│ overview │ report   │  (sign)  │ gas_rpt  │          │
│ multi-   │ counter- │          │          │          │
│ chain    │ parties  │          │          │          │
├──────────┴──────────┴──────────┴──────────┴──────────┤
│                    common / chains                     │
│  ┌─────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │  JSON-RPC   │  │  Etherscan │  │  Formatting  │  │
│  │  (urllib)   │  │  API v2    │  │  & Helpers   │  │
│  └─────────────┘  └────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 📦 Modules

| Module | Description |
|--------|-------------|
| `balances` | Single token balance, multi-token overview, multi-chain summary |
| `history` | TX history (normal/internal/ERC20), transfer reports, counterparty analysis |
| `transfer` | Native/ERC-20 transfers with dry-run, gas estimation, and optional signing |
| `portfolio` | Portfolio valuation via Etherscan, gas spending reports by day |
| `status` | Transaction receipt lookup and success checking |

---

## ⛓ Supported Chains

| Chain | Chain ID | Native | RPC |
|-------|----------|--------|-----|
| Ethereum | 1 | ETH | `eth.llamarpc.com` |
| Base | 8453 | ETH | `mainnet.base.org` |
| Arbitrum | 42161 | ETH | `arb1.arbitrum.io/rpc` |
| Optimism | 10 | ETH | `mainnet.optimism.io` |
| Polygon | 137 | MATIC | `polygon-rpc.com` |

All chains also support custom RPC URLs via environment variables:
```bash
export ETH_RPC_URL=https://my-eth-node.example.com
export BASE_RPC_URL=https://my-base-node.example.com
```

---

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ETHERSCAN_API_KEY` | History, Portfolio | Etherscan API v2 key |
| `ETH_RPC_URL` / `RPC_URL` | Optional | Global RPC URL fallback |
| `<CHAIN>_RPC_URL` | Optional | Chain-specific RPC (e.g. `BASE_RPC_URL`) |
| `HOT_WALLET_PRIVATE_KEY` | Transfer (--broadcast) | Private key for signing |
| `WALLET_ADDRESS` | Optional | Default wallet address |

---

## 📋 CLI Usage

Each module also works as a standalone CLI script:

```bash
# Balance query
python -m evm_wallet_scanner.balances.wallet_balance --chain ethereum --wallet 0x... --token USDC

# Transaction history
python -m evm_wallet_scanner.history.wallet_history --chain base --wallet 0x... --kind normal --kind erc20

# Multi-chain summary
python -m evm_wallet_scanner.balances.wallet_multichain_summary --wallet 0x... --format table

# Gas report
python -m evm_wallet_scanner.portfolio.wallet_gas_report --chain ethereum --wallet 0x...

# Transfer (dry-run)
python -m evm_wallet_scanner.transfer.wallet_transfer --chain base --from 0x... --to 0x... --amount 0.01
```

---

## 🧪 Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE).
