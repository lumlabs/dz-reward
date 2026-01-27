#!/usr/bin/env python3
"""
DZ-Reward: Validator Debt Management Tool for DoubleZero Network

A comprehensive tool for checking and funding validator debt on the DoubleZero network.
Supports notifications via Telegram, Discord, and Slack, and maintains payment history.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from loguru import logger

# Version
__version__ = "0.3.0"

# Load environment variables from .env file
load_dotenv()

# Configuration from environment variables
DZ_VALIDATOR_ADDRESS = os.getenv("DZ_VALIDATOR_ADDRESS")
DZ_KEYPAIR_PATH = os.getenv("DZ_KEYPAIR_PATH", "/root/solana/mainnet-validator-keypair.json")
DZ_TELEGRAM_BOT_TOKEN = os.getenv("DZ_TELEGRAM_BOT_TOKEN")
DZ_TELEGRAM_CHAT_ID = os.getenv("DZ_TELEGRAM_CHAT_ID")
DZ_DISCORD_WEBHOOK_URL = os.getenv("DZ_DISCORD_WEBHOOK_URL")
DZ_SLACK_WEBHOOK_URL = os.getenv("DZ_SLACK_WEBHOOK_URL")
DZ_AUTO_FUND = os.getenv("DZ_AUTO_FUND", "false").lower() == "true"
DZ_LOG_PATH = os.getenv("DZ_LOG_PATH", os.path.expanduser("~/.dz-reward/payment_history.json"))
DZ_NETWORK = os.getenv("DZ_NETWORK", "mainnet-beta")
DZ_SOLANA_CLI_PATH = os.getenv("DZ_SOLANA_CLI_PATH", "solana")

# Retry configuration
DZ_RETRY_ATTEMPTS = int(os.getenv("DZ_RETRY_ATTEMPTS", "3"))
DZ_RETRY_DELAY = int(os.getenv("DZ_RETRY_DELAY", "5"))  # seconds


def retry_on_failure(max_attempts: int = None, delay: int = None):
    """Decorator for retrying functions on failure."""
    max_attempts = max_attempts or DZ_RETRY_ATTEMPTS
    delay = delay or DZ_RETRY_DELAY

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(f"Attempt {attempt}/{max_attempts} failed: {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
            raise last_exception
        return wrapper
    return decorator


def get_validator_address() -> str:
    """Get the validator address from env or doublezero CLI."""
    if DZ_VALIDATOR_ADDRESS:
        return DZ_VALIDATOR_ADDRESS

    try:
        result = subprocess.run(
            ["doublezero", "address"],
            capture_output=True,
            text=True,
            check=True
        )
        address = result.stdout.strip()
        if address:
            return address
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get address from doublezero CLI: {e}")
    except FileNotFoundError:
        logger.error("doublezero CLI not found. Please install it first.")

    return None


def find_solana_cli() -> str | None:
    """Find solana CLI in common locations."""
    # First check if user specified a path
    if DZ_SOLANA_CLI_PATH != "solana":
        if os.path.isfile(DZ_SOLANA_CLI_PATH):
            return DZ_SOLANA_CLI_PATH

    # Common solana CLI locations
    common_paths = [
        "solana",  # In PATH
        os.path.expanduser("~/.local/share/solana/install/active_release/bin/solana"),
        "/root/.local/share/solana/install/active_release/bin/solana",
        "/usr/local/bin/solana",
        "/usr/bin/solana",
        os.path.expanduser("~/solana/bin/solana"),
    ]

    for path in common_paths:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                check=True
            )
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    return None


def get_wallet_balance() -> float | None:
    """Get the current wallet balance in SOL."""
    solana_cli = find_solana_cli()
    if not solana_cli:
        logger.warning("solana CLI not found. Set DZ_SOLANA_CLI_PATH or install Solana CLI tools.")
        return None

    try:
        result = subprocess.run(
            [solana_cli, "balance", "--output", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        # Parse JSON output like {"lamports":1000000000}
        data = json.loads(result.stdout.strip())
        lamports = data.get("lamports", 0)
        return lamports / 1_000_000_000
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get wallet balance: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        # Try parsing plain text output like "1.5 SOL"
        try:
            result = subprocess.run(
                [solana_cli, "balance"],
                capture_output=True,
                text=True,
                check=True
            )
            balance_str = result.stdout.strip().replace(" SOL", "")
            return float(balance_str)
        except Exception:
            logger.error(f"Failed to parse wallet balance: {e}")
            return None


def get_validator_pda(validator_address: str) -> str | None:
    """Get the PDA (deposit) account address for a validator."""
    try:
        result = subprocess.run(
            [
                "doublezero-solana", "revenue-distribution", "fetch", "validator-deposits",
                "-u", DZ_NETWORK,
                "--node-id", validator_address
            ],
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.strip()
        logger.debug(f"Validator deposits output:\n{output}")

        # Parse the table to find PDA account
        # Format: PDA Account | Node ID | Balance
        for line in output.split("\n"):
            if validator_address in line:
                parts = line.split("|")
                if len(parts) >= 1:
                    pda = parts[0].strip()
                    if pda and len(pda) > 30:  # Valid Solana address
                        return pda

        return None

    except subprocess.CalledProcessError as e:
        logger.debug(f"Failed to fetch validator deposits: {e}")
        return None
    except FileNotFoundError:
        return None


@retry_on_failure()
def get_validator_debt(validator_address: str) -> dict | None:
    """
    Run doublezero-solana fetch validator-debts to get debt information.
    Returns dict with debt info or None if no debt/error.
    """
    try:
        result = subprocess.run(
            [
                "doublezero-solana", "revenue-distribution", "fetch", "validator-debts",
                "-u", DZ_NETWORK,
                "--node-id", validator_address
            ],
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.strip()
        logger.debug(f"Validator debts output:\n{output}")

        # Parse the output to extract debt information
        # Expected format is a table with columns: Node ID | Debt (SOL)
        debt_info = {
            "validator": validator_address,
            "raw_output": output,
            "debt_sol": 0.0,
            "has_debt": False,
            "pda_account": None
        }

        # Get PDA account
        debt_info["pda_account"] = get_validator_pda(validator_address)

        for line in output.split("\n"):
            if validator_address in line:
                parts = line.split("|")
                if len(parts) >= 2:
                    try:
                        debt_str = parts[-1].strip()
                        debt_sol = float(debt_str)
                        debt_info["debt_sol"] = debt_sol
                        debt_info["has_debt"] = debt_sol > 0
                    except ValueError:
                        pass

        return debt_info

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch validator debts: {e}")
        logger.error(f"stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        logger.error("doublezero-solana CLI not found. Please install it first.")
        return None


@retry_on_failure()
def fund_outstanding_debt(validator_address: str, dry_run: bool = False) -> dict | None:
    """
    Run doublezero-solana validator-deposit --fund-outstanding-debt to fund the debt.
    Returns dict with transaction info or None on error.
    """
    cmd = [
        "doublezero-solana", "revenue-distribution", "validator-deposit",
        "--fund-outstanding-debt",
        "--node-id", validator_address,
        "-u", DZ_NETWORK
    ]

    if dry_run:
        logger.info(f"[DRY RUN] Would execute: {' '.join(cmd)}")
        return {
            "status": "dry_run",
            "validator": validator_address,
            "tx_hash": "DRY_RUN_NO_TX",
            "amount_sol": "0"
        }

    try:
        logger.info("Executing funding transaction...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        output = result.stdout.strip()
        logger.info(f"Funding output:\n{output}")

        # Parse output for transaction details
        tx_info = {
            "status": "success",
            "validator": validator_address,
            "raw_output": output,
            "tx_hash": None,
            "amount_sol": None
        }

        for line in output.split("\n"):
            if "Funded:" in line:
                tx_info["tx_hash"] = line.split("Funded:")[-1].strip()
            if "Balance:" in line:
                balance_str = line.split("Balance:")[-1].strip().replace(" SOL", "")
                tx_info["amount_sol"] = balance_str

        return tx_info

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fund debt: {e}")
        logger.error(f"stderr: {e.stderr}")
        raise
    except FileNotFoundError:
        logger.error("doublezero-solana CLI not found. Please install it first.")
        return {"status": "failed", "error": "CLI not found"}


def send_telegram_notification(message: str) -> bool:
    """Send notification via Telegram bot."""
    if not DZ_TELEGRAM_BOT_TOKEN or not DZ_TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured, skipping notification")
        return False

    try:
        url = f"https://api.telegram.org/bot{DZ_TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": DZ_TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        return False


def send_discord_notification(message: str) -> bool:
    """Send notification via Discord webhook."""
    if not DZ_DISCORD_WEBHOOK_URL:
        logger.debug("Discord not configured, skipping notification")
        return False

    try:
        payload = {"content": message}
        response = requests.post(DZ_DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Discord notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return False


def send_slack_notification(message: str) -> bool:
    """Send notification via Slack webhook."""
    if not DZ_SLACK_WEBHOOK_URL:
        logger.debug("Slack not configured, skipping notification")
        return False

    try:
        # Convert to Slack mrkdwn format
        slack_message = message.replace("<b>", "*").replace("</b>", "*")
        slack_message = slack_message.replace("<code>", "`").replace("</code>", "`")

        payload = {"text": slack_message}
        response = requests.post(DZ_SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Slack notification sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False


def send_notifications(message: str):
    """Send notifications to all configured channels."""
    send_telegram_notification(message)

    # Discord and Slack use different formatting
    markdown_message = (
        message
        .replace("<b>", "**").replace("</b>", "**")
        .replace("<code>", "`").replace("</code>", "`")
    )
    send_discord_notification(markdown_message)
    send_slack_notification(message)


def log_payment(validator: str, amount_sol: str, tx_hash: str, status: str):
    """Log payment to history file."""
    log_path = Path(DZ_LOG_PATH).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing history or create new
    if log_path.exists():
        with open(log_path) as f:
            history = json.load(f)
    else:
        history = {"payments": []}

    # Add new payment entry
    payment_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "validator": validator,
        "amount_sol": amount_sol,
        "tx_hash": tx_hash,
        "status": status
    }
    history["payments"].append(payment_entry)

    # Save updated history
    with open(log_path, "w") as f:
        json.dump(history, f, indent=2)

    logger.info(f"Payment logged to {log_path}")


def check_cli_installed(cli_name: str) -> bool:
    """Check if a CLI tool is installed."""
    try:
        subprocess.run(
            [cli_name, "--version"],
            capture_output=True,
            check=False
        )
        return True
    except FileNotFoundError:
        return False


def cmd_check(args):
    """Check configuration and dependencies."""
    print(f"\nDZ-Reward Configuration Check (v{__version__})")
    print("=" * 50)

    errors = []
    warnings = []

    # Check CLI tools
    print("\n[CLI Tools]")

    cli_tools = [
        ("doublezero", "Required for getting validator address"),
        ("doublezero-solana", "Required for debt operations"),
    ]

    for cli, description in cli_tools:
        if check_cli_installed(cli):
            print(f"  {cli}: OK")
        else:
            print(f"  {cli}: NOT FOUND")
            errors.append(f"{cli} CLI not installed - {description}")

    # Check solana CLI separately (can be in different location)
    solana_path = find_solana_cli()
    if solana_path:
        print(f"  solana: OK ({solana_path})")
    else:
        print("  solana: NOT FOUND")
        warnings.append("solana CLI not found - set DZ_SOLANA_CLI_PATH or install Solana CLI tools")

    # Check configuration
    print("\n[Configuration]")

    # Validator address
    validator = get_validator_address()
    if validator:
        print(f"  Validator: {validator}")
    else:
        print("  Validator: NOT CONFIGURED")
        errors.append("Validator address not configured. Set DZ_VALIDATOR_ADDRESS or configure doublezero CLI")

    # Keypair
    keypair_path = Path(DZ_KEYPAIR_PATH).expanduser()
    if keypair_path.exists():
        print(f"  Keypair: {DZ_KEYPAIR_PATH} (exists)")
    else:
        print(f"  Keypair: {DZ_KEYPAIR_PATH} (NOT FOUND)")
        warnings.append(f"Keypair file not found at {DZ_KEYPAIR_PATH}")

    # Network
    print(f"  Network: {DZ_NETWORK}")

    # Auto fund
    print(f"  Auto Fund: {DZ_AUTO_FUND}")

    # Retry settings
    print(f"  Retry Attempts: {DZ_RETRY_ATTEMPTS}")
    print(f"  Retry Delay: {DZ_RETRY_DELAY}s")

    # Notifications
    print("\n[Notifications]")

    if DZ_TELEGRAM_BOT_TOKEN and DZ_TELEGRAM_CHAT_ID:
        print("  Telegram: Configured")
    else:
        print("  Telegram: Not configured")

    if DZ_DISCORD_WEBHOOK_URL:
        print("  Discord: Configured")
    else:
        print("  Discord: Not configured")

    if DZ_SLACK_WEBHOOK_URL:
        print("  Slack: Configured")
    else:
        print("  Slack: Not configured")

    if not (DZ_TELEGRAM_BOT_TOKEN or DZ_DISCORD_WEBHOOK_URL or DZ_SLACK_WEBHOOK_URL):
        warnings.append("No notification channels configured")

    # Log path
    print("\n[Logging]")
    log_path = Path(DZ_LOG_PATH).expanduser()
    print(f"  Log Path: {log_path}")
    if log_path.exists():
        print("  Status: File exists")
    else:
        print("  Status: Will be created on first payment")

    # Wallet balance
    print("\n[Wallet]")
    balance = get_wallet_balance()
    if balance is not None:
        print(f"  Balance: {balance:.9f} SOL")
        if balance < 0.01:
            warnings.append(f"Low wallet balance: {balance:.9f} SOL")
    else:
        print("  Balance: Could not retrieve")
        warnings.append("Could not check wallet balance")

    # Summary
    print("\n" + "=" * 50)

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if not errors and not warnings:
        print("\nAll checks passed!")
        return 0
    elif errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    else:
        print(f"\n{len(warnings)} warning(s)")
        return 0


def cmd_status(args):
    """Check validator debt status."""
    validator = get_validator_address()
    if not validator:
        logger.error("Could not determine validator address. Set DZ_VALIDATOR_ADDRESS or ensure doublezero CLI is configured.")
        return 1

    logger.info(f"Checking debt status for validator: {validator}")

    try:
        debt_info = get_validator_debt(validator)
    except Exception as e:
        logger.error(f"Failed to fetch debt information: {e}")
        return 1

    if debt_info is None:
        logger.error("Failed to fetch debt information")
        return 1

    print(f"\nValidator: {validator}")
    if debt_info.get("pda_account"):
        print(f"PDA Account: {debt_info['pda_account']}")
    print(f"Network: {DZ_NETWORK}")
    print(f"Outstanding Debt: {debt_info['debt_sol']:.9f} SOL")
    print(f"Has Debt: {'Yes' if debt_info['has_debt'] else 'No'}")

    # Show wallet balance
    balance = get_wallet_balance()
    if balance is not None:
        print(f"Wallet Balance: {balance:.9f} SOL")

    if debt_info["raw_output"]:
        print(f"\nRaw output from CLI:\n{debt_info['raw_output']}")

    return 0


def cmd_fund(args):
    """Check and fund outstanding debt."""
    validator = get_validator_address()
    if not validator:
        logger.error("Could not determine validator address. Set DZ_VALIDATOR_ADDRESS or ensure doublezero CLI is configured.")
        return 1

    logger.info(f"Checking debt status for validator: {validator}")

    try:
        debt_info = get_validator_debt(validator)
    except Exception as e:
        logger.error(f"Failed to fetch debt information after retries: {e}")
        return 1

    if debt_info is None:
        logger.error("Failed to fetch debt information")
        return 1

    print(f"\nValidator: {validator}")
    if debt_info.get("pda_account"):
        print(f"PDA Account: {debt_info['pda_account']}")
    print(f"Network: {DZ_NETWORK}")
    print(f"Outstanding Debt: {debt_info['debt_sol']:.9f} SOL")

    if not debt_info["has_debt"]:
        logger.info("No outstanding debt to fund")
        return 0

    # Check wallet balance
    balance = get_wallet_balance()
    if balance is not None:
        print(f"Wallet Balance: {balance:.9f} SOL")

        # Need some extra for transaction fees
        required_balance = debt_info["debt_sol"] + 0.001
        if balance < required_balance:
            logger.error(f"Insufficient balance. Need at least {required_balance:.9f} SOL, have {balance:.9f} SOL")

            # Send notification about insufficient balance
            fail_msg = (
                f"<b>DZ-Reward: Insufficient Balance</b>\n"
                f"Validator: <code>{validator}</code>\n"
                f"Debt: {debt_info['debt_sol']:.9f} SOL\n"
                f"Balance: {balance:.9f} SOL\n"
                f"Required: {required_balance:.9f} SOL"
            )
            send_notifications(fail_msg)
            return 1

    # Send notification about detected debt
    notification_msg = (
        f"<b>DZ-Reward: Debt Detected</b>\n"
        f"Validator: <code>{validator}</code>\n"
        f"Outstanding Debt: {debt_info['debt_sol']:.9f} SOL"
    )
    send_notifications(notification_msg)

    # Determine if we should proceed with funding
    auto_mode = args.auto or DZ_AUTO_FUND

    if args.dry_run:
        logger.info("[DRY RUN] Would fund outstanding debt")
        fund_outstanding_debt(validator, dry_run=True)
        return 0

    if not auto_mode:
        # Interactive mode - ask for confirmation
        try:
            confirm = input(f"\nDo you want to fund {debt_info['debt_sol']:.9f} SOL? (y/n): ")
            if not confirm.lower().startswith("y"):
                logger.info("Funding canceled by user")
                return 0
        except EOFError:
            logger.error("Interactive mode requires user input. Use --auto for non-interactive mode.")
            return 1

    # Proceed with funding
    try:
        result = fund_outstanding_debt(validator)
    except Exception as e:
        # Log failed payment
        log_payment(
            validator=validator,
            amount_sol=str(debt_info["debt_sol"]),
            tx_hash="failed",
            status="failed"
        )

        # Send failure notification
        fail_msg = (
            f"<b>DZ-Reward: Payment Failed</b>\n"
            f"Validator: <code>{validator}</code>\n"
            f"Error: {str(e)}"
        )
        send_notifications(fail_msg)

        logger.error(f"Failed to fund debt after retries: {e}")
        return 1

    if result and result.get("status") == "success":
        # Log the payment
        log_payment(
            validator=validator,
            amount_sol=result.get("amount_sol", str(debt_info["debt_sol"])),
            tx_hash=result.get("tx_hash", "unknown"),
            status="success"
        )

        # Send success notification
        success_msg = (
            f"<b>DZ-Reward: Payment Successful</b>\n"
            f"Validator: <code>{validator}</code>\n"
            f"Amount: {result.get('amount_sol', 'N/A')} SOL\n"
            f"TX: <code>{result.get('tx_hash', 'N/A')}</code>"
        )
        send_notifications(success_msg)

        logger.info("Debt funded successfully!")
        return 0
    else:
        # Log failed payment
        log_payment(
            validator=validator,
            amount_sol=str(debt_info["debt_sol"]),
            tx_hash="failed",
            status="failed"
        )

        # Send failure notification
        fail_msg = (
            f"<b>DZ-Reward: Payment Failed</b>\n"
            f"Validator: <code>{validator}</code>\n"
            f"Error: {result.get('error', 'Unknown error') if result else 'Unknown error'}"
        )
        send_notifications(fail_msg)

        logger.error("Failed to fund debt")
        return 1


def cmd_history(args):
    """Show payment history."""
    log_path = Path(DZ_LOG_PATH).expanduser()

    if not log_path.exists():
        print("No payment history found.")
        return 0

    with open(log_path) as f:
        history = json.load(f)

    payments = history.get("payments", [])

    if not payments:
        print("No payments recorded.")
        return 0

    print(f"\nPayment History ({len(payments)} entries):")
    print("-" * 100)
    print(f"{'Timestamp':<25} {'Validator':<45} {'Amount (SOL)':<15} {'Status':<10}")
    print("-" * 100)

    for payment in payments[-20:]:  # Show last 20 entries
        timestamp = payment.get("timestamp", "N/A")[:19]
        validator = payment.get("validator", "N/A")[:44]
        amount = payment.get("amount_sol", "N/A")
        status = payment.get("status", "N/A")
        print(f"{timestamp:<25} {validator:<45} {amount:<15} {status:<10}")

    if len(payments) > 20:
        print(f"\n... and {len(payments) - 20} more entries")

    print(f"\nFull history at: {log_path}")
    return 0


def cmd_version(args):
    """Show version information."""
    print(f"DZ-Reward v{__version__}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="DZ-Reward: Validator Debt Management Tool for DoubleZero Network",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py check            Verify configuration and dependencies
  python3 main.py status           Check validator debt status
  python3 main.py fund             Check and fund debt (interactive)
  python3 main.py fund --auto      Check and fund debt (non-interactive)
  python3 main.py fund --dry-run   Test without executing transaction
  python3 main.py history          Show payment history
  python3 main.py version          Show version

Environment Variables:
  DZ_VALIDATOR_ADDRESS    Validator identity address
  DZ_KEYPAIR_PATH         Path to Solana keypair (default: /root/solana/mainnet-validator-keypair.json)
  DZ_NETWORK              Network to use (default: mainnet-beta)
  DZ_SOLANA_CLI_PATH      Path to solana CLI (auto-detected if not set)
  DZ_TELEGRAM_BOT_TOKEN   Telegram bot token for notifications
  DZ_TELEGRAM_CHAT_ID     Telegram chat ID for notifications
  DZ_DISCORD_WEBHOOK_URL  Discord webhook URL for notifications
  DZ_SLACK_WEBHOOK_URL    Slack webhook URL for notifications
  DZ_AUTO_FUND            Set to 'true' for non-interactive mode
  DZ_RETRY_ATTEMPTS       Number of retry attempts (default: 3)
  DZ_RETRY_DELAY          Delay between retries in seconds (default: 5)
  DZ_LOG_PATH             Payment history path (default: ~/.dz-reward/payment_history.json)
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Check command
    check_parser = subparsers.add_parser("check", help="Verify configuration and dependencies")
    check_parser.set_defaults(func=cmd_check)

    # Status command
    status_parser = subparsers.add_parser("status", help="Check validator debt status")
    status_parser.set_defaults(func=cmd_status)

    # Fund command
    fund_parser = subparsers.add_parser("fund", help="Check and fund outstanding debt")
    fund_parser.add_argument(
        "--auto", "-a",
        action="store_true",
        help="Non-interactive mode (skip confirmation prompt)"
    )
    fund_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without executing"
    )
    fund_parser.set_defaults(func=cmd_fund)

    # History command
    history_parser = subparsers.add_parser("history", help="Show payment history")
    history_parser.set_defaults(func=cmd_history)

    # Version command
    version_parser = subparsers.add_parser("version", help="Show version information")
    version_parser.set_defaults(func=cmd_version)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
