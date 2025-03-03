#!/usr/bin/env python3
"""
Advanced Bitcoin Wallet Recovery Tool

This script attempts multiple methods to extract funds from a bitcoinlib wallet
when normal methods have failed. It will try to:

1. Extract the HD wallet seed if available
2. Extract the master private key
3. Directly access wallet database for UTXOs
4. Create an emergency transaction directly from available data

SECURITY WARNING: This script displays sensitive information. Run on a secure system.
"""

import sys
import os
import sqlite3
import json
import binascii
from pathlib import Path
from bitcoinlib.wallets import Wallet, wallet_exists, wallets_list
from bitcoinlib.keys import HDKey
from bitcoinlib.services.services import Service
from bitcoinlib.transactions import Transaction

# Determine database path
def get_database_path():
    """Get the path to the bitcoinlib database file"""
    home_dir = Path.home()
    default_db_path = home_dir / ".bitcoinlib" / "database" / "bitcoinlib.sqlite"
    if os.path.exists(default_db_path):
        return default_db_path
    
    # Try Windows path format
    windows_db_path = Path(os.getenv('APPDATA', '')) / "bitcoinlib" / "database" / "bitcoinlib.sqlite"
    if os.path.exists(windows_db_path):
        return windows_db_path
    
    # Try to find by searching
    for root_dir in [home_dir, Path(os.getenv('APPDATA', ''))]:
        for path in root_dir.glob("**/*bitcoinlib*.sqlite"):
            return path
    
    return None

def extract_wallet_seed(wallet_name):
    """
    Attempt to extract the HD wallet seed phrase or mnemonic
    """
    print("\n=== ATTEMPTING TO EXTRACT WALLET SEED ===")
    
    db_path = get_database_path()
    if not db_path:
        print("Could not find bitcoinlib database file.")
        return None
    
    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, check the schema to see what columns are available
        cursor.execute("PRAGMA table_info(keys)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Look for potential seed columns
        seed_columns = [col for col in columns if 'seed' in col.lower()]
        print(f"Found potential seed columns: {seed_columns}")
        
        # Try different approaches based on available columns
        wallet_data = None
        if 'seed_hex' in columns:
            cursor.execute(
                "SELECT seed_hex, wallet_id FROM keys WHERE wallet_id IN "
                "(SELECT id FROM wallets WHERE name=?)", 
                (wallet_name,)
            )
            wallet_data = cursor.fetchone()
        elif 'seed' in columns:
            cursor.execute(
                "SELECT seed, wallet_id FROM keys WHERE wallet_id IN "
                "(SELECT id FROM wallets WHERE name=?)", 
                (wallet_name,)
            )
            wallet_data = cursor.fetchone()
        
        # Check for private master key
        master_key_data = None
        if 'private' in columns and 'is_private' in columns:
            cursor.execute(
                "SELECT private, wallet_id FROM keys WHERE wallet_id IN "
                "(SELECT id FROM wallets WHERE name=?) AND is_private=1 AND (path='m' OR path='' OR path IS NULL) LIMIT 1", 
                (wallet_name,)
            )
            master_key_data = cursor.fetchone()
        
        # Show wallet structure
        print("\nExamining wallet database structure...")
        print(f"Wallet name: {wallet_name}")
        
        # Get wallet ID
        cursor.execute("SELECT id FROM wallets WHERE name=?", (wallet_name,))
        wallet_id_data = cursor.fetchone()
        
        if wallet_id_data:
            wallet_id = wallet_id_data[0]
            print(f"Wallet ID: {wallet_id}")
            
            # Count keys
            cursor.execute("SELECT COUNT(*) FROM keys WHERE wallet_id=?", (wallet_id,))
            key_count = cursor.fetchone()[0]
            print(f"Number of keys: {key_count}")
            
            # Get master key info
            cursor.execute(
                "SELECT id, path, address, public, private, is_private FROM keys "
                "WHERE wallet_id=? AND (path='m' OR path='' OR path IS NULL) LIMIT 1", 
                (wallet_id,)
            )
            master_key_row = cursor.fetchone()
            
            if master_key_row:
                print("\nMaster key found:")
                id, path, address, public, private, is_private = master_key_row
                print(f"ID: {id}")
                print(f"Path: {path}")
                print(f"Address: {address}")
                print(f"Is private: {is_private}")
                
                if private and is_private:
                    try:
                        from bitcoinlib.keys import HDKey
                        master_key = HDKey.from_wif(private)
                        if hasattr(master_key, 'wif'):
                            print(f"\nMaster Private Key (WIF): {master_key.wif}")
                            print("You can import this key into Electrum")
                        
                        # Try to get seed from master key
                        if hasattr(master_key, 'seed_hex') and master_key.seed_hex:
                            seed_hex = master_key.seed_hex
                            print(f"\nFound seed from master key: {seed_hex}")
                            
                            try:
                                from bitcoinlib.mnemonic import Mnemonic
                                mnemonic = Mnemonic().to_mnemonic(binascii.unhexlify(seed_hex))
                                print("\nWALLET RECOVERY SEED PHRASE:")
                                print(f"{mnemonic}")
                                print("\n⚠️ This is your wallet recovery phrase - store it securely!")
                                return seed_hex
                            except Exception as e:
                                print(f"Could not convert to mnemonic: {e}")
                    except Exception as e:
                        print(f"Error processing master key: {e}")
        
        # Dump important tables to inspect structure
        print("\nExporting keys to human-readable format...")
        cursor.execute(
            "SELECT id, path, address, wif, public, private, is_private FROM keys "
            "WHERE wallet_id IN (SELECT id FROM wallets WHERE name=?) LIMIT 10", 
            (wallet_name,)
        )
        keys = cursor.fetchall()
        
        if keys:
            print("\nKey information:")
            for key in keys:
                key_id, path, address, wif, public, private, is_private = key
                print(f"\nKey ID: {key_id}")
                print(f"Path: {path}")
                print(f"Address: {address}")
                print(f"Has private key: {is_private}")
                if wif:
                    print(f"WIF: {wif}")
                    print("↑ This private key can be imported into Electrum")
        
        conn.close()
        
        # If we found a private key, that's success
        if master_key_data and master_key_data[0]:
            return master_key_data[0]
        elif wallet_data and wallet_data[0]:
            return wallet_data[0]
        
        print("\nCould not extract seed directly from database.")
        print("Check the output above for any private keys (WIF format) that can be imported into Electrum.")
        return None
    except Exception as e:
        print(f"Error accessing database: {e}")
        return None

def extract_master_key(wallet_name):
    """
    Attempt to extract the master private key
    """
    print("\n=== ATTEMPTING TO EXTRACT MASTER PRIVATE KEY ===")
    
    try:
        wallet = Wallet(wallet_name)
        
        # Try to get the main key and wif
        main_key = None
        for key in wallet.keys():
            if key.path in ['m', 'm/', '']:
                main_key = key
                break
        
        if main_key:
            try:
                wif = main_key.wif
                print(f"Master Private Key (WIF): {wif}")
                print("\nYou can import this private key into Electrum.")
                return wif
            except:
                print("Could not extract WIF from master key.")
        
        # Try to extract through database
        db_path = get_database_path()
        if db_path:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Try to get master private key from database
            cursor.execute(
                "SELECT key_wif FROM keys WHERE wallet_id IN "
                "(SELECT id FROM wallets WHERE name=?) AND path IN ('m', 'm/', '')", 
                (wallet_name,)
            )
            key_data = cursor.fetchone()
            
            if key_data and key_data[0]:
                print(f"Master Private Key from DB (WIF): {key_data[0]}")
                print("\nYou can import this private key into Electrum.")
                return key_data[0]
            
            conn.close()
        
        print("Could not extract master private key.")
        return None
    except Exception as e:
        print(f"Error extracting master key: {e}")
        return None

def direct_utxo_access(wallet_name):
    """
    Directly access UTXOs from the database
    """
    print("\n=== ATTEMPTING DIRECT UTXO ACCESS ===")
    
    db_path = get_database_path()
    if not db_path:
        print("Could not find bitcoinlib database file.")
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get wallet ID
        cursor.execute("SELECT id FROM wallets WHERE name=?", (wallet_name,))
        wallet_id_data = cursor.fetchone()
        
        if not wallet_id_data:
            print(f"Wallet '{wallet_name}' not found in database.")
            return None
        
        wallet_id = wallet_id_data[0]
        
        # Get UTXOs directly from database
        cursor.execute("""
            SELECT 
                t.tx_hash, t.output_n, t.value, t.key_id, t.script, 
                k.address, k.wif, k.path
            FROM
                transactions t
            JOIN
                keys k ON t.key_id = k.id
            WHERE
                t.wallet_id=? AND t.spent=0
        """, (wallet_id,))
        
        utxos = cursor.fetchall()
        
        if not utxos:
            print("No unspent outputs found in database.")
            return None
        
        total_value = 0
        print("\nFound UTXOs directly in database:")
        print("-" * 80)
        print(f"{'TXID':<32} {'Output #':<8} {'Value (BTC)':<12} {'Address':<35} {'Path'}")
        print("-" * 80)
        
        utxo_data = []
        for utxo in utxos:
            tx_hash, output_n, value, key_id, script, address, wif, path = utxo
            print(f"{tx_hash[:30]}... {output_n:<8} {value / 1e8:<12.8f} {address:<35} {path}")
            total_value += value
            
            utxo_data.append({
                'tx_hash': tx_hash,
                'output_n': output_n,
                'value': value,
                'key_id': key_id,
                'script': script,
                'address': address,
                'wif': wif,
                'path': path
            })
        
        print("-" * 80)
        print(f"Total value: {total_value / 1e8:.8f} BTC")
        
        if utxo_data:
            print("\nPrivate keys for these UTXOs:")
            for utxo in utxo_data:
                if utxo.get('wif'):
                    print(f"Address: {utxo['address']}")
                    print(f"Private Key (WIF): {utxo['wif']}")
                    print(f"Value: {utxo['value'] / 1e8:.8f} BTC")
                    print("-" * 50)
        
        conn.close()
        
        if utxo_data:
            return utxo_data
        return None
    except Exception as e:
        print(f"Error in direct UTXO access: {e}")
        return None

def create_emergency_transaction(wallet_name, destination_address):
    """
    Create an emergency transaction to send all funds to a destination address
    """
    print("\n=== ATTEMPTING EMERGENCY TRANSACTION ===")
    
    if not destination_address:
        print("No destination address provided.")
        return False
    
    # Get UTXOs
    utxos = direct_utxo_access(wallet_name)
    if not utxos:
        print("No UTXOs found for emergency transaction.")
        return False
    
    try:
        # Create a raw transaction
        print(f"\nCreating emergency transaction to {destination_address}")
        
        # Approach 1: Try using wallet.send_to
        try:
            wallet = Wallet(wallet_name)
            fee = 5000  # 5000 satoshis (conservative)
            
            # Calculate total amount
            total_value = sum(utxo['value'] for utxo in utxos)
            amount = total_value - fee
            
            if amount <= 0:
                print(f"Amount after fee too small: {amount} satoshis")
                return False
            
            print(f"Attempting to send {amount / 1e8:.8f} BTC with fee {fee / 1e8:.8f} BTC")
            
            tx = wallet.send_to(destination_address, amount, fee=fee)
            
            # Try to get transaction ID
            tx_id = None
            for attr in ['hash', 'txid', 'tx_hash', 'id']:
                if hasattr(tx, attr):
                    tx_id = getattr(tx, attr)
                    break
            
            print(f"Transaction created successfully!")
            print(f"Transaction ID: {tx_id or 'Unknown'}")
            print(f"Amount: {amount / 1e8:.8f} BTC")
            print(f"Fee: {fee / 1e8:.8f} BTC")
            
            print("\nCheck a blockchain explorer to verify the transaction was broadcast.")
            return True
        except Exception as e:
            print(f"Standard transaction attempt failed: {e}")
            print("Trying alternative method...")
        
        # TODO: If the above fails, we could implement a manual transaction creation
        # using the UTXOs directly, but this would be quite complex and requires
        # handling transaction signing manually.
        
        print("Could not create emergency transaction.")
        print("Your best option is to import the private keys or seed into Electrum.")
        return False
    except Exception as e:
        print(f"Error creating emergency transaction: {e}")
        return False

def list_and_select_wallet():
    """List available wallets and let user select one"""
    print("\nAvailable wallets:")
    print("-" * 60)
    print(f"{'Wallet Name':<30} {'Network':<10} {'Status'}")
    print("-" * 60)
    
    wallets = wallets_list()
    if not wallets:
        print("No wallets found in database")
        return None
    
    for i, wallet_info in enumerate(wallets, 1):
        name = wallet_info.get('name', 'Unknown')
        network = "Unknown"
        for key in ['network_name', 'network', 'scheme']:
            if key in wallet_info:
                network = wallet_info[key]
                break
        
        print(f"{i}. {name:<28} {network:<10} {'Active'}")
    
    print("-" * 60)
    
    # Let user select wallet
    selection = input("\nSelect wallet by number or name (default: forwarding_wallet): ")
    
    wallet_name = "forwarding_wallet"
    if selection.isdigit() and 1 <= int(selection) <= len(wallets):
        wallet_name = wallets[int(selection)-1].get('name')
    elif selection:
        wallet_name = selection
    
    return wallet_name

def display_recovery_options():
    """Display recovery options menu"""
    print("\nRecovery Options:")
    print("1. Extract wallet seed (for import into Electrum)")
    print("2. Extract master private key")
    print("3. Find UTXOs and their private keys")
    print("4. Create emergency transaction to move all funds")
    print("5. Try all recovery methods")
    print("6. Exit")
    
    choice = input("\nSelect option (1-6): ")
    return choice

def main():
    print("\n=======================")
    print("ADVANCED WALLET RECOVERY")
    print("=======================")
    print("\n⚠️ WARNING: This tool accesses sensitive wallet information")
    print("Run this on a secure computer and don't share the output")
    
    # List wallets and let user select one
    wallet_name = list_and_select_wallet()
    if not wallet_name:
        print("No wallet selected. Exiting.")
        sys.exit(1)
    
    print(f"\nSelected wallet: {wallet_name}")
    
    while True:
        choice = display_recovery_options()
        
        if choice == '1':
            extract_wallet_seed(wallet_name)
        elif choice == '2':
            extract_master_key(wallet_name)
        elif choice == '3':
            direct_utxo_access(wallet_name)
        elif choice == '4':
            destination = input("\nEnter destination Bitcoin address: ")
            create_emergency_transaction(wallet_name, destination)
        elif choice == '5':
            print("\n=== TRYING ALL RECOVERY METHODS ===")
            seed = extract_wallet_seed(wallet_name)
            if not seed:
                master_key = extract_master_key(wallet_name)
            
            utxos = direct_utxo_access(wallet_name)
            
            if utxos:
                create_tx = input("\nDo you want to create an emergency transaction to move funds? (y/n): ")
                if create_tx.lower() == 'y':
                    destination = input("Enter destination Bitcoin address: ")
                    create_emergency_transaction(wallet_name, destination)
        elif choice == '6':
            print("Exiting recovery tool.")
            sys.exit(0)
        else:
            print("Invalid choice. Please try again.")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()