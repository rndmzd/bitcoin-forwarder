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
import json
from pathlib import Path
from bitcoinlib.wallets import Wallet, wallet_exists
from bitcoinlib.services.services import Service
from bitcoinlib.keys import Address

# Setup logging directory
log_dir = Path.home() / ".bitcoin_forwarder"
os.makedirs(log_dir, exist_ok=True)
log_file = log_dir / "bitcoin_forwarder.log"
config_file = log_dir / "config.json"

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

def save_config(wallet_name, destination_address):
    """
    Save wallet name and destination address to config file
    """
    config = {
        "wallet_name": wallet_name,
        "destination_address": destination_address
    }
    
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f)
        logger.info("Config saved successfully")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

def load_config():
    """
    Load wallet name and destination address from config file
    """
    if not os.path.exists(config_file):
        logger.info("No config file found")
        return None, None
    
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        wallet_name = config.get('wallet_name')
        destination_address = config.get('destination_address')
        
        logger.info(f"Loaded config: wallet={wallet_name}, destination={destination_address}")
        return wallet_name, destination_address
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return None, None

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
                # Handle both object and dictionary format
                try:
                    # Try object format first
                    tx_id = utxo.txid if hasattr(utxo, 'txid') else utxo.transaction.hash
                    confirmations = utxo.confirmations if hasattr(utxo, 'confirmations') else utxo.transaction.confirmations
                    value = utxo.value
                except AttributeError:
                    # If above fails, try dictionary format
                    tx_id = utxo['txid'] if 'txid' in utxo else utxo['tx_hash']
                    confirmations = utxo['confirmations']
                    value = utxo['value']
                
                # Skip if we've already processed this transaction
                if tx_id in processed_txs:
                    continue
                
                # Log and display transaction info
                logger.info(f"Found transaction {tx_id} with {confirmations} confirmations")
                print(f"Found transaction: {tx_id}")
                print(f"  Amount: {value / 1e8:.8f} BTC")
                print(f"  Confirmations: {confirmations}/{required_confirmations}")
                
                if confirmations >= required_confirmations:
                    # Calculate transaction fee based on current network conditions
                    tx_fee = calculate_transaction_fee(service)
                    
                    # Create and send transaction to forward funds
                    if value > tx_fee:
                        amount_to_forward = value - tx_fee
                        logger.info(f"Forwarding {amount_to_forward} satoshis to {destination_address}")
                        print(f"Forwarding {amount_to_forward / 1e8:.8f} BTC to {destination_address}")
                        print(f"  Network fee: {tx_fee / 1e8:.8f} BTC")
                        
                        forward_funds(wallet, destination_address, amount_to_forward, tx_fee)
                        processed_txs.add(tx_id)
                    else:
                        logger.warning(f"Transaction value ({value}) is too small to cover fee ({tx_fee})")
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
        # Try to get fee estimation from service
        fee_per_kb = service.estimatefee(4)  # Targeting confirmation within 4 blocks
        logger.info(f"Fee estimation from service: {fee_per_kb} BTC/KB")
        
        # The API returns fee in BTC per KB
        # Check if the fee is already in satoshis or if it's in BTC
        if fee_per_kb > 0.1:  # If fee is > 0.1 BTC/KB, something is wrong
            logger.warning(f"Fee estimation too high ({fee_per_kb} BTC/KB), using fallback")
            fee_per_kb = 0.0001  # Fallback to 0.0001 BTC/KB
        
        # Convert to satoshis (1 BTC = 100,000,000 satoshis)
        # Assuming a typical transaction size of ~250 bytes
        tx_size = 250
        tx_fee = int(fee_per_kb * 1e8 * tx_size / 1024)
        
        # Sanity check - cap maximum fee at 25,000 satoshis (0.00025 BTC)
        max_fee = 25000  # 0.00025 BTC
        if tx_fee > max_fee:
            logger.warning(f"Calculated fee too high ({tx_fee} satoshis), capping at {max_fee}")
            tx_fee = max_fee
        
        # Ensure a minimum reasonable fee
        min_fee = 1000  # 1000 satoshis minimum (0.00001 BTC)
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
        
        # Different versions of bitcoinlib use different attribute names for transaction ID
        tx_id = None
        for attr in ['hash', 'txid', 'tx_hash', 'id']:
            if hasattr(tx, attr):
                tx_id = getattr(tx, attr)
                break
        
        if not tx_id and hasattr(tx, 'dict'):
            # Try accessing as dictionary if available
            tx_dict = tx.dict()
            tx_id = tx_dict.get('txid') or tx_dict.get('hash') or tx_dict.get('tx_hash')
        
        if not tx_id:
            # Last resort: convert to string and look for ID
            tx_str = str(tx)
            if "txid" in tx_str.lower():
                # Try to extract ID from string representation
                import re
                match = re.search(r'(txid|hash|id)[\'"\s:=]+([a-fA-F0-9]{64})', tx_str, re.IGNORECASE)
                if match:
                    tx_id = match.group(2)
            
            # If we still don't have an ID, use a placeholder
            if not tx_id:
                tx_id = "Transaction sent (ID unavailable)"
                
        logger.info(f"Transaction sent! Transaction ID: {tx_id}")
        print(f"\nTransaction sent successfully!")
        print(f"  Transaction ID: {tx_id}")
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
    
    # Try to load config
    saved_wallet_name, saved_destination_address = load_config()
    
    # Use wallet name from args if provided, otherwise from config, otherwise default
    wallet_name = args.wallet_name if args.wallet_name != "forwarding_wallet" else (saved_wallet_name or "forwarding_wallet")
    
    # Get destination address from user or from config
    destination_address = None
    if saved_destination_address:
        print(f"Found saved destination address: {saved_destination_address}")
        use_saved = input("Use this address? (y/n): ").lower().strip()
        if use_saved == 'y':
            destination_address = saved_destination_address
    
    if not destination_address:
        destination_address = input("Enter the Bitcoin address to forward funds to: ")
    
    # Validate address
    if not validate_bitcoin_address(destination_address):
        logger.error("Invalid Bitcoin address provided. Exiting.")
        print("Invalid Bitcoin address provided. Exiting.")
        sys.exit(1)
    
    # Save config
    save_config(wallet_name, destination_address)
    
    # Create or get existing wallet
    wallet, wallet_address = get_or_create_wallet(wallet_name)
    
    print(f"\nMonitoring for incoming transactions with {args.confirmations} confirmations required.")
    print(f"Funds will be forwarded to: {destination_address}")
    print(f"Log file is located at: {log_file}")
    print(f"Config file is located at: {config_file}")
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