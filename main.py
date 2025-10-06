#!/usr/bin/env python3
import sys
import json
import requests

from loguru import logger

API_URL = (
    "https://svc.blockdaemon.com/reporting/staking/v2/solana/mainnet/validator/rewards"
)
API_KEY = "2go1YqUcuAr4WZ2-3WgSD3c7qpatZqQuNWhTVBldKZnTSUtw"
LAMPORTS_PER_SOL = 1_000_000_000


def main():
    if len(sys.argv) != 3:
        logger.info("Usage: python3 get_rewards.py <epoch> <address>")
        sys.exit(1)

    epoch = int(sys.argv[1])
    address = sys.argv[2]

    headers = {
        "X-API-Key": API_KEY,
        "accept": "application/x-ndjson",
        "content-type": "application/json",
    }

    payload = {
        "epoch": epoch,
        "addresses": [address],
        "period": "monthly",
        "aggregate": False,
        "denomination": "lamports",
    }

    response = requests.post(API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        logger.error(f"Error: {response.status_code}")
        logger.error(response.text)
        sys.exit(1)

    try:
        json_response = response.json()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        sys.exit(1)

    fee_lamports = json_response.get("metadata", {}).get("fee")
    
    if not fee_lamports:
        logger.error("Fee information not found in the response.")
        sys.exit(1)

    fee_sol = int(fee_lamports) / LAMPORTS_PER_SOL
    logger.info(f"Earned fee is {fee_sol} SOL")
    fund_lamports = int(fee_lamports) * 5 / 100
    fund_sol = fund_lamports / LAMPORTS_PER_SOL
    logger.info(f"5% to be funded: {fund_sol} SOL")
    print(f"__FUND_SOL__:{fund_sol:.9f}")

if __name__ == "__main__":
    main()
