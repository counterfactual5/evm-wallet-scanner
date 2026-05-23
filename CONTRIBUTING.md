# Contributing to evm-wallet-scanner

## Setup

```bash
git clone https://github.com/counterfactual5/evm-wallet-scanner.git
cd evm-wallet-scanner
uv pip install -e ".[dev]"
```

## Running Tests

```bash
uv run pytest tests/ -v
```

36 tests covering imports, chains, addresses, formatting, RPC resolution, on-chain queries (mocked), and Etherscan requests.

## Code Style

- Python 3.10+ compatible
- 120-char line length (configured in `pyproject.toml`)
- Public functions have docstrings
- Addresses in lowercase for comparison

## Project Philosophy

### Zero Dependencies

`evm-wallet-scanner` uses **only the Python standard library** for core functionality. `eth-account` is optional for transaction signing only.

### Module Pattern

Each module follows the same pattern:
- A Python script with a `main()` function that uses `argparse`
- Importable public helpers from `common.py`
- CLI arguments use `--chain`, `--wallet`, `--rpc-url`, `--output`

## Adding a New Chain

1. Add to `CHAINS` dict in `chains.py`
2. Set `rpc_url` to a public RPC endpoint
3. The chain auto-works with all modules

## Pull Requests

1. Fork → feature branch → changes + tests → PR to `main`
2. Keep PRs focused — one concern per PR
