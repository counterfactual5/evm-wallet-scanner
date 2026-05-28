# Risk Policy Reference

Cross-project rule engine that sits between `PREFLIGHT` and `SIGNED` states
in the trade execution state machine.

## Quick Start

```bash
# Copy the template to the default lookup path
cp policy.yaml ~/.stageforge/policy.yaml

# Or use a custom location
export POLICY_FILE=/path/to/my-policy.yaml
```

## File Resolution

1. Explicit path argument to `load_policy(path=...)`
2. `POLICY_FILE` environment variable
3. `~/.stageforge/policy.yaml`
4. `~/.stageforge/policy.json`

If no file is found, returns a **permissive default** (no limits, everything
allowed).  This is the safe default — policy files only restrict, never
broaden access.

## Rule Cascade

```
global:
  max_amount: 1000          ← base rules
  allowed_chains: [...]

uniswap-autopilot:
  max_amount: 2000          ← overrides global for this project only
```

Project sections merge on top of `global`.  Non-null values override;
non-overridden fields inherit from global.  Two edge cases worth knowing:

- **`allowed_chains: []`** — empty list disables the chain check (all chains
  pass).  This is different from omitting the field (inherits global list).
- **`blacklist_addresses: []`** — empty list means no addresses are blocked
  (check runs, nothing matches).

In short: an empty list always means "no restriction on this field", never
"block all".

## Shared Rules (all projects)

| Rule | Key | Severity | Description |
|------|-----|----------|-------------|
| Trade amount cap | `max_amount` | **Hard reject** | Trade value > limit → blocked. USD or native units. |
| Chain whitelist | `allowed_chains` | **Hard reject** | Chain not in list → blocked. |
| Blacklist addresses | `blacklist_addresses` | **Hard reject** | Sender/receiver/spender in list → blocked. |
| Whitelist addresses | `whitelist_addresses` | **Soft warn** | Address not in list → warning only. |
| Max slippage | `max_slippage_bps` | **Hard reject** | Slippage in basis points > limit → blocked. |
| Max gas price | `max_gas_price_gwei` | **Soft warn** | Gas price > limit → warning only. |

**Hard reject** = trade is blocked, `STATE_FAILED` recorded, audit event emitted.

**Soft warn** = trade proceeds, warning attached to `CheckResult.warnings`.

## Project-Specific Rules

### hyperliquid-autopilot

Activated via `check_hyperliquid(policy, context)`.

| Rule | Key | Severity | Description |
|------|-----|----------|-------------|
| Max leverage | `max_leverage` | **Hard reject** | Leverage multiplier > limit → blocked. |
| Allowed coins | `allowed_coins` | **Hard reject** | Coin not in list → blocked (empty = all allowed). |

```yaml
hyperliquid-autopilot:
  max_leverage: 10
  allowed_coins:
    - BTC
    - ETH
    - SOL
```

### polymarket-autopilot

Activated via `check_polymarket(policy, context)`.

| Rule | Key | Severity | Description |
|------|-----|----------|-------------|
| Min price | `min_price` | **Hard reject** | Order price < floor → blocked. |
| Max price | `max_price` | **Hard reject** | Order price > ceiling → blocked. |
| Max position | `max_position_value` | **Hard reject** | Total position value > cap → blocked. |

```yaml
polymarket-autopilot:
  min_price: 0.01
  max_price: 0.99
  max_position_value: 5000
```

### uniswap-autopilot

Activated via `check_uniswap(policy, context)`.

| Rule | Key | Severity | Description |
|------|-----|----------|-------------|
| Min output | `min_output_amount` | **Hard reject** | Expected output < floor → blocked (0 = disabled). |

```yaml
uniswap-autopilot:
  min_output_amount: 100.0   # require at least 100 USDC worth of output
```

## Troubleshooting

### "policy_rejected" in audit log

Look for the `details.violations` array:

```bash
jq 'select(.error_code=="policy_rejected") | .details' audit.jsonl
```

Each violation has a `rule` and `message` field telling you exactly what
failed and why.

### Trade blocked, no policy file

This can't happen.  If no policy file is found, `load_policy()` returns a
permissive `Policy()` with all limits set to `None` — everything passes.

### Trade blocked, expected to pass

1. Check `~/.stageforge/policy.yaml` — is the right project section present?
2. Run `cat ~/.stageforge/policy.yaml | python3 -c "import yaml,sys; yaml.safe_load(sys.stdin)"` to validate syntax.
3. Override temporarily: `POLICY_FILE=/dev/null` (disables policy checks for one invocation).

## Audit Integration

Policy violations emit `log_event(event=EVENT_ERROR, error_code="policy_rejected")`
with `details.violations` containing the list of failed rules:

```json
{
  "event": "error",
  "error_code": "policy_rejected",
  "details": {
    "violations": [
      {"rule": "max_amount", "message": "amount 1500 exceeds limit 1000"}
    ]
  }
}
```
