# Status

This tool is deprecated and no longer relevant for current DoubleZero operations.

It was created for automatic PDA account top-ups when protocol fee payments were required. After DoubleZero removed those fees, the tool no longer serves an active purpose.

The repository remains available as a reference to the original implementation.

# DZ-Reward: Validator Debt Management Tool

A comprehensive tool for managing validator debt on the DoubleZero network. Automatically checks debt status, funds outstanding debt, and sends notifications via Telegram, Discord, and Slack.

## Features

- Check validator debt status
- Fund outstanding debt (interactive or auto mode)
- Wallet balance verification before funding
- Telegram, Discord, and Slack notifications
- Payment history logging
- Automatic retry on network failures
- Configuration validation command
- Cron-friendly auto mode (required for automatic alerts)
- Systemd service and timer support

## Requirements

- Python 3.12+
- `uv` package manager
- `doublezero` and `doublezero-solana` CLI tools installed
- `solana` CLI (for balance checks)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/lumlabs/dz-reward.git
cd dz-reward
```

2. Copy the example environment file and configure:
```bash
cp .env.example .env
nano .env  # Edit with your settings
```

3. Make scripts executable:
```bash
chmod +x main.py run.sh
```

4. Verify installation:
```bash
./run.sh check
```

5. **Set up automation** (required for automatic alerts):
```bash
crontab -e
# Add this line to run daily at 9 AM:
0 9 * * * cd /path/to/dz-reward && ./run.sh fund --auto >> /var/log/dz-reward.log 2>&1
```

## Configuration

Configure via environment variables or `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `DZ_VALIDATOR_ADDRESS` | Validator identity address | Auto-detected from CLI |
| `DZ_KEYPAIR_PATH` | Path to Solana keypair | `/root/solana/mainnet-validator-keypair.json` |
| `DZ_NETWORK` | Network (mainnet-beta, testnet, devnet) | `mainnet-beta` |
| `DZ_SOLANA_CLI_PATH` | Path to solana CLI | Auto-detected |
| `DZ_TELEGRAM_BOT_TOKEN` | Telegram bot token | (optional) |
| `DZ_TELEGRAM_CHAT_ID` | Telegram chat ID | (optional) |
| `DZ_DISCORD_WEBHOOK_URL` | Discord webhook URL | (optional) |
| `DZ_SLACK_WEBHOOK_URL` | Slack webhook URL | (optional) |
| `DZ_AUTO_FUND` | Auto-fund without prompts | `false` |
| `DZ_RETRY_ATTEMPTS` | Number of retry attempts | `3` |
| `DZ_RETRY_DELAY` | Delay between retries (seconds) | `5` |
| `DZ_LOG_PATH` | Payment history path | `~/.dz-reward/payment_history.json` |

## Usage

### Using Python directly

```bash
# Verify configuration
python3 main.py check

# Check debt status
python3 main.py status

# Check and fund debt (interactive)
python3 main.py fund

# Check and fund debt (auto mode for cron)
python3 main.py fund --auto

# Test without executing transaction
python3 main.py fund --dry-run

# Show payment history
python3 main.py history

# Show version
python3 main.py version
```

### Using the shell wrapper

The `run.sh` script handles virtual environment setup and dependency installation:

```bash
# Verify configuration
./run.sh check

# Check debt status
./run.sh status

# Fund debt (interactive)
./run.sh fund

# Fund debt (auto mode)
./run.sh fund --auto

# Dry run
./run.sh fund --dry-run

# Show history
./run.sh history

# Show help
./run.sh --help
```

## Automation (Required for Alerts)

> **Important:** The script does NOT run continuously. To receive automatic alerts when debt is detected, you MUST set up either Cron or Systemd timer. Without this, you'll need to run the script manually each time.

### Cron Setup (Recommended)

For automated debt funding, add to crontab:

```bash
crontab -e
```

```bash
# Run every day at 9 AM
0 9 * * * cd /path/to/dz-reward && ./run.sh fund --auto >> /var/log/dz-reward.log 2>&1
```

### Systemd Setup (Recommended)

1. Copy files to `/opt/dz-reward`:
```bash
sudo cp -r . /opt/dz-reward
sudo cp .env.example /opt/dz-reward/.env
sudo nano /opt/dz-reward/.env  # Configure
```

2. Install systemd files:
```bash
sudo cp dz-reward.service /etc/systemd/system/
sudo cp dz-reward.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

3. Enable and start the timer:
```bash
sudo systemctl enable dz-reward.timer
sudo systemctl start dz-reward.timer
```

4. Check timer status:
```bash
sudo systemctl list-timers | grep dz-reward
```

5. Run manually:
```bash
sudo systemctl start dz-reward.service
```

6. Check logs:
```bash
sudo tail -f /var/log/dz-reward.log
```

## Notifications

### Telegram Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) - copy the bot token
2. **Find your bot** in Telegram and send it any message (e.g., "hello")
3. Get your chat ID by running:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```
4. In the response, find `"chat":{"id":123456789,...}` - that number is your chat ID
5. Add to `.env`:
```
DZ_TELEGRAM_BOT_TOKEN=your_bot_token
DZ_TELEGRAM_CHAT_ID=your_chat_id
```

**Troubleshooting Telegram:**

If you get `403 Forbidden` error:
- Make sure you sent a message to your bot first
- Verify chat_id is YOUR id, not the bot's id (bot id is the first part of the token)
- Run `getUpdates` again after sending a message to the bot

Alternative way to get chat ID - use [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot)

### Discord Setup

1. Go to your Discord server settings
2. Navigate to Integrations > Webhooks
3. Create a new webhook and copy the URL
4. Add to `.env`:
```
DZ_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### Slack Setup

1. Go to your Slack workspace settings
2. Create an incoming webhook app
3. Copy the webhook URL
4. Add to `.env`:
```
DZ_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

## Payment History

Payments are logged to `~/.dz-reward/payment_history.json`:

```json
{
  "payments": [
    {
      "timestamp": "2026-01-26T15:30:00+00:00",
      "validator": "9Wmaz9VPpEnH67ZqrvYd9bcH66DtsGaEKcSQE1ac5wkf",
      "amount_sol": "0.226958871",
      "tx_hash": "2NZVgo864ouR8fSgin73kWEipm6q6Mh9KaMzefjin2oaFC4sQqmkFW5LZd6Tti6A9ypCZtYgdmH9WqSS9tEy11Rz",
      "status": "success"
    }
  ]
}
```

View history with:
```bash
python3 main.py history
```

## CLI Commands Reference

The tool uses the DoubleZero CLI commands:

- `doublezero address` - Get validator address
- `doublezero-solana revenue-distribution fetch validator-debts` - Check outstanding debt
- `doublezero-solana revenue-distribution validator-deposit --fund-outstanding-debt` - Fund debt
- `solana balance` - Check wallet balance

## Troubleshooting

Run the check command to diagnose issues:
```bash
./run.sh check
```

This will verify:
- CLI tools installation (doublezero, doublezero-solana, solana)
- Validator address configuration
- Keypair file existence
- Notification channels
- Wallet balance

## License

MIT
