#!/usr/bin/env python3
"""
Bitcoin Private Key Exporter for Electrum

This script exports private keys from a bitcoinlib wallet in WIF format 
for importing into Electrum or other wallets.

SECURITY WARNING: Private keys give full access to your funds.
- Run this script on a secure computer
- Don't share the output with anyone
- Clear your clipboard and terminal history after copying keys
"""

import sys
from bitcoinlib.wallets import Wallet, wallet_exists, wallets_list
import getpass

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
        try:
            wallet.scan()
        except:
            print("Warning: Could not scan wallet for latest transactions")
        return wallet
    except Exception as e:
        print(f"Error opening wallet: {e}")
        return None

def export_private_keys(wallet):
    """
    Export private keys in WIF format
    """
    if not wallet:
        return
    
    print("\n===== PRIVATE KEY EXPORT =====")
    print("WARNING: These keys give FULL ACCESS to your funds")
    print("- Make sure no one is looking at your screen")
    print("- Store these keys securely\n")
    
    print("Keys with balances will be marked with [HAS FUNDS]")
    print("-" * 75)
    
    # Try to get UTXOs to identify which addresses have funds
    addresses_with_funds = set()
    try:
        utxos = wallet.utxos()
        for utxo in utxos:
            try:
                if hasattr(utxo, 'address'):
                    addresses_with_funds.add(utxo.address)
                elif hasattr(utxo, 'key') and hasattr(utxo.key, 'address'):
                    addresses_with_funds.add(utxo.key.address)
            except:
                pass
    except:
        print("Warning: Could not check which addresses have funds")
    
    # Get all keys
    keys_exported = 0
    for key in wallet.keys():
        try:
            address = key.address
            path = key.path
            
            # Get the private key in WIF format
            try:
                wif = key.wif
                has_funds = address in addresses_with_funds
                flag = " [HAS FUNDS]" if has_funds else ""
                
                print(f"Address: {address}{flag}")
                print(f"Path: {path}")
                print(f"WIF Private Key: {wif}")
                print("-" * 75)
                keys_exported += 1
            except:
                print(f"WARNING: Could not export private key for {address}")
        except Exception as e:
            print(f"Error processing key: {e}")
    
    print(f"\nExported {keys_exported} private keys")
    print("\nHOW TO IMPORT INTO ELECTRUM:")
    print("1. Install Electrum from https://electrum.org")
    print("2. Create a new wallet or restore an existing one")
    print("3. Go to Wallet > Private Keys > Import")
    print("4. Paste the WIF private key(s) marked with [HAS FUNDS]")
    print("5. Electrum will scan for transactions and show your balance")
    
    print("\nSECURITY REMINDER:")
    print("- Clear your clipboard after copying keys")
    print("- Clear your terminal history (e.g., 'history -c' in bash)")
    print("- Consider moving funds to a fresh wallet after importing")

def main():
    print("\nBitcoin Private Key Exporter")
    print("===========================")
    print("\nWARNING: Private keys give complete control over your funds.")
    print("Run this script on a secure computer.\n")
    
    # List available wallets
    if not list_available_wallets():
        print("No wallets found. Exiting.")
        sys.exit(1)
    
    # Get wallet name
    wallet_name = input("\nEnter wallet name to export keys from (default: forwarding_wallet): ")
    if not wallet_name:
        wallet_name = "forwarding_wallet"
    
    # Open wallet
    wallet = open_wallet(wallet_name)
    if not wallet:
        print("Failed to open wallet. Exiting.")
        sys.exit(1)
    
    # Confirmation
    print(f"\nYou are about to export private keys from wallet: {wallet_name}")
    print("These keys will give FULL ACCESS to any funds in this wallet.")
    confirm = input("Are you sure you want to continue? (type 'yes' to confirm): ")
    
    if confirm.lower() != 'yes':
        print("Export cancelled.")
        sys.exit(0)
    
    # Export keys
    export_private_keys(wallet)

if __name__ == "__main__":
    main()