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

def list_utxos(wallet):
    """
    Directly examine the UTXOs (Unspent Transaction Outputs) in the wallet
    """
    print("\nUnspent Transaction Outputs (UTXOs):")
    print("-" * 80)
    print(f"{'TXID':<65} {'Output #':<8} {'Value (BTC)':<12} {'Confirmations'}")
    print("-" * 80)
    
    try:
        utxos = wallet.utxos()
        if not utxos:
            print("No unspent outputs found")
            return False
        
        total_value = 0
        for utxo in utxos:
            # Try different ways to access UTXO data
            try:
                txid = utxo.txid if hasattr(utxo, 'txid') else (
                    utxo.tx_hash if hasattr(utxo, 'tx_hash') else 
                    (utxo.hash if hasattr(utxo, 'hash') else "Unknown"))
                
                output_n = utxo.output_n if hasattr(utxo, 'output_n') else "?"
                value = utxo.value if hasattr(utxo, 'value') else 0
                confirmations = utxo.confirmations if hasattr(utxo, 'confirmations') else "?"
                
                print(f"{txid:<65} {output_n:<8} {value / 1e8:<12.8f} {confirmations}")
                total_value += value
            except Exception as e:
                print(f"Error accessing UTXO data: {e}")
        
        print("-" * 80)
        print(f"Total value: {total_value / 1e8:.8f} BTC")
        return True
    except Exception as e:
        print(f"Error listing UTXOs: {e}")
        return False

def display_wallet_info(wallet):
    """
    Display wallet information including addresses and balance
    """
    if not wallet:
        return
    
    print("\nWallet Information:")
    print(f"Name: {wallet.name}")
    print(f"ID: {wallet.wallet_id}")
    
    # Get network name (different library versions use different attributes)
    network_name = "Unknown"
    if hasattr(wallet, 'network') and hasattr(wallet.network, 'name'):
        network_name = wallet.network.name
    elif hasattr(wallet, 'network_name'):
        network_name = wallet.network_name
    print(f"Network: {network_name}")
    
    # Try to update wallet with latest blockchain information
    try:
        wallet.scan()
        print("Wallet updated with latest blockchain information")
    except Exception as e:
        print(f"Warning: Could not scan wallet: {e}")
    
    # Get total wallet balance
    try:
        total_balance = wallet.balance()
        print(f"\nTotal Wallet Balance: {total_balance / 1e8:.8f} BTC")
    except Exception as e:
        total_balance = 0
        print(f"Warning: Could not get wallet balance: {e}")
    
    # Display addresses
    print("\nAddresses:")
    
    # Display each key/address
    for key in wallet.keys():
        address = key.address
        path = key.path
        
        # Try different methods to get address balance
        address_balance = 0
        try:
            # Try method 1: utxos_address if it exists
            if hasattr(wallet, 'utxos_address'):
                balance_data = wallet.utxos_address(address, as_dict=True)
                address_balance = sum([utxo['value'] for utxo in balance_data]) if balance_data else 0
            else:
                # Try method 2: filter utxos by address
                try:
                    all_utxos = wallet.utxos()
                    # Different UTXO object structures in different library versions
                    for utxo in all_utxos:
                        utxo_address = None
                        # Try different attribute accesses for UTXO address
                        if hasattr(utxo, 'address'):
                            utxo_address = utxo.address
                        elif hasattr(utxo, 'key') and hasattr(utxo.key, 'address'):
                            utxo_address = utxo.key.address
                        
                        if utxo_address == address:
                            # Try different attribute accesses for UTXO value
                            if hasattr(utxo, 'value'):
                                address_balance += utxo.value
                            elif isinstance(utxo, dict) and 'value' in utxo:
                                address_balance += utxo['value']
                except Exception as e:
                    print(f"  Warning: Could not get UTXOs: {e}")
        except Exception as e:
            address_balance = 0
            print(f"  Warning: Could not get balance for {address}: {e}")
        
        print(f"- {address} (Path: {path})")
        print(f"  Balance: {address_balance / 1e8:.8f} BTC")
    
    # List UTXOs directly
    if total_balance > 0:
        print("\nNOTE: Your wallet has a balance but it's not showing in individual addresses.")
        print("This is a common issue with the bitcoinlib library. Let's examine the UTXOs directly:")
        list_utxos(wallet)

def calculate_safe_transaction_fee(network='bitcoin'):
    """
    Calculate a safe and reasonable transaction fee with strict limits
    Returns fee in satoshis
    """
    try:
        from bitcoinlib.services.services import Service
        service = Service(network=network)
        fee_per_kb = service.estimatefee(4)  # Target 4 blocks
        
        # Log the raw estimation
        print(f"Raw fee estimation from service: {fee_per_kb} BTC/KB")
        
        # Sanity check - if fee is unreasonably high, use fallback
        if fee_per_kb > 0.001:  # If > 0.001 BTC/KB, something is wrong
            print(f"Fee estimation too high ({fee_per_kb} BTC/KB), using fallback")
            fee_per_kb = 0.0001  # Fallback to 0.0001 BTC/KB
        
        # Convert to satoshis for a typical transaction (250 bytes)
        tx_size = 250  # bytes
        estimated_fee = int(fee_per_kb * 1e8 * tx_size / 1024)
        
        # Apply strict limits
        MIN_FEE = 1000    # 1000 satoshis (0.00001 BTC)
        MAX_FEE = 25000   # 25000 satoshis (0.00025 BTC)
        SAFE_DEFAULT = 5000  # 5000 satoshis (0.00005 BTC)
        
        if estimated_fee > MAX_FEE:
            print(f"Estimated fee too high ({estimated_fee} satoshis), capping at {MAX_FEE}")
            return MAX_FEE
        elif estimated_fee < MIN_FEE:
            print(f"Estimated fee too low ({estimated_fee} satoshis), using minimum {MIN_FEE}")
            return MIN_FEE
        else:
            return estimated_fee
            
    except Exception as e:
        print(f"Error estimating fee: {e}")
        print("Using safe default fee")
        return 5000  # Safe default (0.00005 BTC)

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
    
    # If fee is not specified, calculate a safe fee
    if fee is None:
        fee = calculate_safe_transaction_fee(wallet.network.name)
    
    # Show fee in both satoshis and BTC
    print(f"\nTransaction fee: {fee} satoshis ({fee / 1e8:.8f} BTC)")
    
    # Allow user to modify the fee if desired
    modify_fee = input("Would you like to modify the fee? (y/n): ").lower().strip()
    if modify_fee == 'y':
        custom_fee_input = input(f"Enter custom fee in satoshis (1000-25000, current: {fee}): ")
        try:
            custom_fee = int(custom_fee_input)
            if 1000 <= custom_fee <= 25000:
                fee = custom_fee
                print(f"Using custom fee: {fee} satoshis ({fee / 1e8:.8f} BTC)")
            else:
                print("Fee must be between 1000-25000 satoshis. Using calculated fee.")
        except ValueError:
            print("Invalid input. Using calculated fee.")
    
    # If amount is not specified, send entire balance minus fee
    if amount is None:
        amount = balance - fee
    
    if amount <= 0:
        print(f"Amount after fee deduction is too small: {amount} satoshis")
        return
    
    print(f"\nPreparing to send {amount / 1e8:.8f} BTC to {to_address}")
    print(f"Transaction fee: {fee / 1e8:.8f} BTC")
    print(f"Total to be deducted from wallet: {(amount + fee) / 1e8:.8f} BTC")
    
    confirm = input("Confirm transaction? (y/n): ").lower().strip()
    if confirm != 'y':
        print("Transaction cancelled")
        return
    
    try:
        print("Sending transaction... This might take a few moments.")
        tx = wallet.send_to(to_address, amount, fee=fee)
        
        # Try to get transaction ID
        tx_id = None
        for attr in ['hash', 'txid', 'tx_hash', 'id']:
            if hasattr(tx, attr):
                tx_id = getattr(tx, attr)
                break
        
        print(f"\nTransaction sent successfully!")
        print(f"Transaction ID: {tx_id or 'Unknown'}")
        print(f"Amount: {amount / 1e8:.8f} BTC")
        print(f"Fee: {fee / 1e8:.8f} BTC")
        
        print("\nPlease verify this transaction in a blockchain explorer.")
        return tx
    except Exception as e:
        print(f"Error sending transaction: {e}")
        return None

def display_wallet_transactions(wallet):
    """
    Display recent transactions for the wallet including pending ones
    """
    print("\nRecent Transactions:")
    print("-" * 80)
    print(f"{'Transaction ID':<65} {'Type':<8} {'Amount':<15} {'Status'}")
    print("-" * 80)
    
    try:
        # Scan wallet to ensure we have the latest transactions
        wallet.scan()
        
        # Try different ways to get transactions
        transactions = []
        if hasattr(wallet, 'transactions') and callable(getattr(wallet, 'transactions')):
            try:
                transactions = wallet.transactions()
            except Exception as e:
                print(f"Warning: Error retrieving transactions: {e}")
        
        if not transactions:
            print("No transactions found or unable to retrieve transaction history")
            return
        
        for tx in transactions:
            tx_id = None
            tx_type = "Unknown"
            amount = 0
            status = "Unknown"
            
            # Try to get transaction ID
            for attr in ['txid', 'hash', 'tx_hash', 'id']:
                if hasattr(tx, attr):
                    tx_id = getattr(tx, attr)
                    break
            
            # Try to get transaction type
            if hasattr(tx, 'input_total') and hasattr(tx, 'output_total'):
                if tx.input_total > tx.output_total:
                    tx_type = "Outgoing"
                    amount = -(tx.input_total - tx.output_total)
                else:
                    tx_type = "Incoming"
                    amount = tx.output_total - tx.input_total
            
            # Try to get status
            if hasattr(tx, 'status'):
                status = tx.status
            elif hasattr(tx, 'confirmations'):
                status = "Confirmed" if tx.confirmations > 0 else "Pending"
            
            print(f"{tx_id or 'Unknown':<65} {tx_type:<8} {amount / 1e8:>14.8f} {status}")
    
    except Exception as e:
        print(f"Error retrieving transaction history: {e}")
    
    print("-" * 80)

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
    
    # Display recent transactions
    display_wallet_transactions(wallet)
    
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