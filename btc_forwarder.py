#!/usr/bin/env python3
"""
Bitcoin Transaction Forwarding Service

This script creates a local Bitcoin wallet, monitors it for incoming transactions, and
forwards received funds to a pre-specified address after sufficient confirmations.
It also displays a QR code for the local wallet address in the terminal.

Prerequisites:
- Python 3.6+
- Install required packages: pip install bitcoinlib qrcode
"""

import time
import sys
import logging
import argparse
import os
from pathlib import Path
from bitcoinlib.wallets import Wallet, wallet_exists
from bitcoinlib.services.services import Service
from bitcoinlib.keys import Address

# Setup logging directory
log_dir = Path.home() / ".bitcoin_forwarder"
os.makedirs(log_dir, exist_ok=True)
log_file = log_dir / "bitcoin_forwarder.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger("BitcoinForwarder")

def validate_bitcoin_address(address):
    """
    Validate if the provided string is a valid Bitcoin address
    """
    try:
        Address.parse(address)
        return True
    except Exception as e:
        logger.error(f"Invalid Bitcoin address: {e}")
        return False

def get_or_create_wallet(wallet_name="forwarding_wallet"):
    """
    Get existing wallet or create a new one if it doesn't exist
    """
    if wallet_exists(wallet_name):
        logger.info(f"Using existing wallet: {wallet_name}")
        wallet = Wallet(wallet_name)
    else:
        logger.info(f"Creating new wallet: {wallet_name}")
        wallet = Wallet.create(wallet_name, network='bitcoin')
    
    key = wallet.get_key()
    address = key.address
    logger.info(f"Wallet address: {address}")
    return wallet, address

def monitor_wallet(wallet, destination_address, required_confirmations=3, check_interval=60):
    """
    Monitor the wallet for incoming transactions
    Once a transaction is confirmed, forward the funds to the destination address
    """
    wallet_address = wallet.get_key().address
    logger.info(f"Monitoring wallet for transactions. Send Bitcoin to: {wallet_address}")
    print(f"\n=== WALLET ADDRESS TO RECEIVE FUNDS ===")
    print(f"{wallet_address}")
    print(f"======================================")
    
    # Generate and display QR code for the wallet address
    generate_qr_terminal(wallet_address)
    
    service = Service(network='bitcoin')
    
    # Keep track of transactions we've processed
    processed_txs = set()
    
    while True:
        try:
            # Update wallet with latest blockchain information
            wallet.scan()
            
            # Check for new unspent outputs (received transactions)
            for utxo in wallet.utxos():
                tx_id = utxo.transaction.hash
                
                # Skip if we've already processed this transaction
                if tx_id in processed_txs:
                    continue
                
                # Check confirmation count
                confirmations = utxo.transaction.confirmations
                logger.info(f"Found transaction {tx_id} with {confirmations} confirmations")
                print(f"Found transaction: {tx_id}")
                print(f"  Amount: {utxo.value / 1e8:.8f} BTC")
                print(f"  Confirmations: {confirmations}/{required_confirmations}")
                
                if confirmations >= required_confirmations:
                    # Calculate transaction fee based on current network conditions
                    tx_fee = calculate_transaction_fee(service)
                    
                    # Create and send transaction to forward funds
                    if utxo.value > tx_fee:
                        amount_to_forward = utxo.value - tx_fee
                        logger.info(f"Forwarding {amount_to_forward} satoshis to {destination_address}")
                        print(f"Forwarding {amount_to_forward / 1e8:.8f} BTC to {destination_address}")
                        print(f"  Network fee: {tx_fee / 1e8:.8f} BTC")
                        
                        forward_funds(wallet, destination_address, amount_to_forward, tx_fee)
                        processed_txs.add(tx_id)
                    else:
                        logger.warning(f"Transaction value ({utxo.value}) is too small to cover fee ({tx_fee})")
                        print(f"Transaction value is too small to cover network fee. Skipping.")
                        processed_txs.add(tx_id)
            
            # Wait before checking again
            sys.stdout.write(f"\rLast checked: {time.strftime('%H:%M:%S')}. Checking again in {check_interval} seconds...")
            sys.stdout.flush()
            time.sleep(check_interval)
            sys.stdout.write("\r" + " " * 80 + "\r")  # Clear line
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            print(f"Error occurred: {e}")
            print(f"Retrying in {check_interval} seconds...")
            time.sleep(check_interval)  # Still wait before retrying

def calculate_transaction_fee(service):
    """
    Calculate a reasonable transaction fee based on current network conditions
    Returns fee in satoshis
    """
    try:
        fee_per_kb = service.estimatefee(4)  # Targeting confirmation within 4 blocks
        
        # Convert to satoshis (1 BTC = 100,000,000 satoshis)
        # Assuming a typical transaction size of ~250 bytes
        tx_size = 250
        tx_fee = int(fee_per_kb * 1e8 * tx_size / 1024)
        
        # Ensure a minimum reasonable fee
        min_fee = 1000  # 1000 satoshis minimum
        tx_fee = max(tx_fee, min_fee)
        
        logger.info(f"Calculated transaction fee: {tx_fee} satoshis")
        return tx_fee
    except Exception as e:
        logger.error(f"Error calculating fee: {e}")
        # Return a conservative default fee if estimation fails
        return 10000  # 10,000 satoshis as fallback

def forward_funds(wallet, destination_address, amount, fee):
    """
    Send funds from the wallet to the destination address
    """
    try:
        # Create transaction
        tx = wallet.send_to(destination_address, amount, fee=fee)
        logger.info(f"Transaction sent! Transaction ID: {tx.hash}")
        print(f"\nTransaction sent successfully!")
        print(f"  Transaction ID: {tx.hash}")
        print(f"  Amount: {amount / 1e8:.8f} BTC")
        print(f"  Fee: {fee / 1e8:.8f} BTC")
        return tx
    except Exception as e:
        logger.error(f"Error sending transaction: {e}")
        print(f"\nError sending transaction: {e}")
        return None

def generate_qr_terminal(data):
    """
    Generate a QR code and display it in the terminal
    """
    try:
        import qrcode
        from qrcode.main import QRCode

        # Create QR code instance
        qr = QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        
        # Add data
        qr.add_data(data)
        qr.make(fit=True)
        
        # Print QR code to terminal - using ASCII characters
        # Black modules are represented by ASCII block characters, white by spaces
        modules = qr.get_matrix()
        
        print("\nQR Code for wallet address:")
        print("-" * (len(modules[0]) * 2 + 4))
        
        for row in modules:
            print("  ", end="")
            for cell in row:
                if cell:
                    print("██", end="")
                else:
                    print("  ", end="")
            print()
            
        print("-" * (len(modules[0]) * 2 + 4))
        print(f"Address: {data}")
        
    except ImportError:
        logger.warning("QR code functionality unavailable. Install 'qrcode' for this feature.")
        print("\nNote: Install 'qrcode' package to display QR codes in terminal:")
        print("pip install qrcode")

def check_dependencies():
    """
    Check if required dependencies are installed
    """
    missing = []
    
    try:
        import bitcoinlib
    except ImportError:
        missing.append("bitcoinlib")
    
    try:
        import qrcode
    except ImportError:
        missing.append("qrcode")
    
    if missing:
        if "bitcoinlib" in missing:
            print("Required package 'bitcoinlib' is not installed.")
            print("Please install it using: pip install bitcoinlib")
            return False
        else:
            print("Optional package 'qrcode' is not installed.")
            print("For QR code display, install it using: pip install qrcode")
            return True
    
    return True

def parse_arguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(description='Bitcoin Transaction Forwarding Service')
    parser.add_argument('--confirmations', type=int, default=3,
                        help='Number of confirmations required before forwarding (default: 3)')
    parser.add_argument('--interval', type=int, default=60,
                        help='Interval in seconds to check for new transactions (default: 60)')
    parser.add_argument('--wallet-name', type=str, default="forwarding_wallet",
                        help='Name for the local wallet (default: forwarding_wallet)')
    parser.add_argument('--testnet', action='store_true',
                        help='Use Bitcoin testnet instead of mainnet')
    return parser.parse_args()

def main():
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    print("\nBitcoin Transaction Forwarding Service")
    print("=====================================\n")
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Get destination address from user
    destination_address = input("Enter the Bitcoin address to forward funds to: ")
    
    # Validate address
    if not validate_bitcoin_address(destination_address):
        logger.error("Invalid Bitcoin address provided. Exiting.")
        print("Invalid Bitcoin address provided. Exiting.")
        sys.exit(1)
    
    # Create or get existing wallet
    wallet, wallet_address = get_or_create_wallet(args.wallet_name)
    
    print(f"\nMonitoring for incoming transactions with {args.confirmations} confirmations required.")
    print(f"Funds will be forwarded to: {destination_address}")
    print(f"Log file is located at: {log_file}")
    print("Press Ctrl+C to exit\n")
    
    # Start monitoring for transactions
    try:
        monitor_wallet(wallet, destination_address, 
                     required_confirmations=args.confirmations,
                     check_interval=args.interval)
    except KeyboardInterrupt:
        print("\nExiting...")
    
if __name__ == "__main__":
    main()