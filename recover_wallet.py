#!/usr/bin/env python3
"""
Bitcoin Wallet Recovery Tool

This script allows you to manually access a wallet created by the Bitcoin Forwarding Service
and send funds to another address if the main script fails.

Prerequisites:
- Python 3.6+
- bitcoinlib package: pip install bitcoinlib
"""

import sys
import logging
from bitcoinlib.wallets import Wallet, wallet_exists, wallets_list

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("WalletRecovery")

def list_available_wallets():
    """
    List all available wallets in the bitcoinlib database
    """
    print("\nAvailable wallets:")
    print("-" * 60)
    print(f"{'Wallet Name':<30} {'Network':<10} {'Status'}")
    print("-" * 60)
    
    wallets = wallets_list()
    if not wallets:
        print("No wallets found in database")
        return False
    
    for wallet_info in wallets:
        # Get network name using different possible keys
        network = "Unknown"
        for key in ['network_name', 'network', 'scheme']:
            if key in wallet_info:
                network = wallet_info[key]
                break
        
        name = wallet_info.get('name', 'Unknown')
        print(f"{name:<30} {network:<10} {'Active'}")
    
    print("-" * 60)
    return True

def open_wallet(wallet_name):
    """
    Open a specific wallet and return it
    """
    if not wallet_exists(wallet_name):
        print(f"Wallet '{wallet_name}' does not exist")
        return None
    
    try:
        wallet = Wallet(wallet_name)
        # Update wallet with latest blockchain information
        wallet.scan()
        return wallet
    except Exception as e:
        print(f"Error opening wallet: {e}")
        return None

def display_wallet_info(wallet):
    """
    Display wallet information including addresses and balance
    """
    if not wallet:
        return
    
    print("\nWallet Information:")
    print(f"Name: {wallet.name}")
    print(f"ID: {wallet.wallet_id}")
    print(f"Network: {wallet.network.name}")
    
    # Display addresses
    print("\nAddresses:")
    for key in wallet.keys():
        address = key.address
        path = key.path
        balance = wallet.utxos_address(address, as_dict=True)
        balance_sum = sum([utxo['value'] for utxo in balance]) if balance else 0
        
        print(f"- {address} (Path: {path})")
        print(f"  Balance: {balance_sum / 1e8:.8f} BTC")
    
    # Display total balance
    print(f"\nTotal Balance: {wallet.balance() / 1e8:.8f} BTC")

def send_transaction(wallet, to_address, amount=None, fee=None):
    """
    Send a transaction from the wallet
    """
    if not wallet:
        return
    
    balance = wallet.balance()
    if balance <= 0:
        print("Wallet has zero balance")
        return
    
    # If amount is not specified, send entire balance minus fee
    if amount is None:
        if fee is None:
            # Estimate fee (default to 5000 satoshis if estimation fails)
            try:
                from bitcoinlib.services.services import Service
                service = Service(network=wallet.network.name)
                fee_per_kb = service.estimatefee(4)  # Target 4 blocks
                # Assuming a typical transaction size of ~250 bytes
                fee = int(fee_per_kb * 1e8 * 250 / 1024)
                fee = max(fee, 5000)  # Minimum 5000 satoshis
            except:
                fee = 5000  # Default fee if estimation fails
        
        amount = balance - fee
    
    if amount <= 0:
        print(f"Amount after fee deduction is too small: {amount} satoshis")
        return
    
    print(f"\nPreparing to send {amount / 1e8:.8f} BTC to {to_address}")
    print(f"Transaction fee: {fee / 1e8:.8f} BTC")
    
    confirm = input("Confirm transaction? (y/n): ").lower().strip()
    if confirm != 'y':
        print("Transaction cancelled")
        return
    
    try:
        tx = wallet.send_to(to_address, amount, fee=fee)
        print(f"\nTransaction sent successfully!")
        print(f"Transaction ID: {tx.hash}")
        print(f"Amount: {amount / 1e8:.8f} BTC")
        print(f"Fee: {fee / 1e8:.8f} BTC")
        return tx
    except Exception as e:
        print(f"Error sending transaction: {e}")
        return None

def main():
    print("\nBitcoin Wallet Recovery Tool")
    print("===========================\n")
    
    print("This tool helps you access funds in a wallet created by the Bitcoin Forwarding Service")
    
    # List available wallets
    if not list_available_wallets():
        print("No wallets found. Exiting.")
        sys.exit(1)
    
    # Get wallet name
    wallet_name = input("\nEnter wallet name to open (default: forwarding_wallet): ")
    if not wallet_name:
        wallet_name = "forwarding_wallet"
    
    # Open wallet
    wallet = open_wallet(wallet_name)
    if not wallet:
        print("Failed to open wallet. Exiting.")
        sys.exit(1)
    
    # Display wallet info
    display_wallet_info(wallet)
    
    # Check if wallet has balance
    if wallet.balance() <= 0:
        print("\nWallet has zero balance. No funds to recover.")
        sys.exit(0)
    
    # Ask for destination address
    print("\nTo send funds, please provide the following information:")
    to_address = input("Destination Bitcoin address: ")
    
    # Validate address
    try:
        from bitcoinlib.keys import Address
        Address.parse(to_address)
    except Exception as e:
        print(f"Invalid Bitcoin address: {e}")
        sys.exit(1)
    
    # Ask for amount (optional)
    amount_input = input("Amount to send in BTC (leave blank to send entire balance): ")
    amount = None
    if amount_input:
        try:
            amount = int(float(amount_input) * 1e8)  # Convert to satoshis
        except:
            print("Invalid amount")
            sys.exit(1)
    
    # Send transaction
    send_transaction(wallet, to_address, amount)

if __name__ == "__main__":
    main()