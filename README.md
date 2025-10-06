# Solana Validator Reward Automation

This tool automates fetching Solana validator rewards from the **Blockdaemon Staking API**, calculates the 5% fund allocation, and optionally triggers a fund distribution using the `doublezero` CLI.

---

## Overview

The process consists of two scripts:

1. **`main.py`** –  
   Fetches validator reward data from Blockdaemon, converts lamports to SOL, and prints the calculated 5% fund amount.

2. **`run.sh`** –  
   Bash automation wrapper that:
   - Sets up the Python environment using `uv`
   - Runs `get_rewards.py`
   - Extracts the calculated 5% fund value
   - Asks the user for confirmation to proceed
   - Executes the `doublezero` command to deposit the fund (if confirmed)

---

## ⚙️ Requirements

- **Python 3.12+**
- **uv** package manager (for dependency management)
- **bash** (macOS or Linux)
- **doublezero CLI** installed on the target server

---

## Installation Steps

### 1. Clone or copy the scripts

```bash
git clone git@github.com:lumlabs/dz-reward.git
cd dz-reward
```

Make sure both files exist:

```
main.py
run.sh
```

### 2. Make both files executable

```bash
chmod +x main.py run.sh
```

---

## Usage

### Syntax

```bash
./run.sh <epoch_number>
```

### Example

```bash
./run.sh 859
```

### Expected output

```
Syncing dependencies with uv...
Validator Address: <validator_address>
2025-10-06 19:30:47.837 | INFO     | __main__:main:57 - Earned fee is 4.539177417 SOL
2025-10-06 19:30:47.838 | INFO     | __main__:main:60 - 5% to be funded: 0.22695887085 SOL
__FUND_SOL__:0.226958871
You need to fund: 0.226958871 SOL
Proceed with funding? (y/n):
```

If the user confirms (`y`), the following command is executed:

```bash
doublezero-solana revenue-distribution validator-deposit <validator_address> --fund <fund_amount> -u mainnet-beta
```
