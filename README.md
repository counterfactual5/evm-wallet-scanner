<p align="center">
  <img src="https://img.shields.io/badge/EVM-Wallet--Scanner-4A90E2?style=for-the-badge&logo=ethereum&logoColor=white" alt="EVM Wallet Scanner" />
</p>

<h1 align="center">🔍 EVM Wallet Scanner</h1>

<p align="center">
  <strong>轻量 · 零依赖 · 高性能</strong><br/>
  纯 Python EVM 钱包扫描与分析工具包
</p>

<p align="center">
  <a href="https://github.com/counterfactual5/evm-wallet-scanner/stargazers"><img src="https://img.shields.io/github/stars/counterfactual5/evm-wallet-scanner?style=social" alt="Stars"></a>
  <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

---

## ✨ 项目亮点

- **零依赖**：仅使用 Python 标准库，无需安装 web3.py、requests 等重型包
- **多链支持**：Ethereum、Base、Arbitrum、Optimism、Polygon 等
- **高性能**：异步支持 + 批量查询 + 智能 RPC 管理
- **实用功能**：余额查询、交易历史、资金流分析、Gas 报告、Portfolio 估值
- **CLI 友好**：可作为命令行工具快速使用

## 🚀 快速开始

```bash
# 克隆仓库
git clone https://github.com/counterfactual5/evm-wallet-scanner.git
cd evm-wallet-scanner

# 直接运行示例
python -m evm_wallet_scanner.example
```

### 示例：查询余额

```python
from evm_wallet_scanner.scanner import WalletScanner

scanner = WalletScanner()

result = scanner.get_balance(
    wallet="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    chain="ethereum"
)
print(result)
```

## 📋 核心功能

| 功能模块 | 描述 |
|----------|------|
| **余额查询** | 原生代币 + ERC20 批量余额 |
| **交易历史** | 普通交易 + 内部交易 + Token Transfer |
| **资金流分析** | 对手方统计、鲸鱼追踪 |
| **Portfolio** | 持仓估值 + Gas 消耗报告 |
| **批量扫描** | 支持多地址、多链并行扫描 |

## 🛠 安装与开发

```bash
pip install -e .
```

## 📌 支持链

- Ethereum (1)
- Base (8453)
- Arbitrum (42161)
- Optimism (10)
- Polygon (137)

## 📄 License

MIT License

---

**Made with ❤️ for DeFi researchers and on-chain analysts**