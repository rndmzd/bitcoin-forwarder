#!/usr/bin/env python3
"""
Schema-Adaptive Bitcoin Recovery Tool

This script carefully examines your bitcoinlib database structure
and adapts to it, making it compatible with any version of bitcoinlib.
"""

import sys
import os
import sqlite3
import json
from pathlib import Path

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

def analyze_database_schema(conn):
    """
    Analyze the database schema to understand its structure
    """
    print("\n==== DATABASE SCHEMA ANALYSIS ====")
    cursor = conn.cursor()
    
    # Get list of tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables found: {', '.join(tables)}")
    
    schema_info = {}
    
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        schema_info[table] = columns
        print(f"\nTable '{table}' columns: {', '.join(columns)}")
        
        # For key tables, show a sample row
        if table in ['wallets', 'keys', 'transactions']:
            try:
                cursor.execute(f"SELECT * FROM {table} LIMIT 1")
                row = cursor.fetchone()
                if row:
                    print(f"Sample row from '{table}':")
                    column_values = []
                    for i, column in enumerate(columns):
                        value = row[i]
                        if value is not None:
                            if isinstance(value, (str, int, float)):
                                value_str = str(value)
                                if len(value_str) > 50:
                                    value_str = value_str[:47] + "..."
                                column_values.append(f"{column}: {value_str}")
                    print(", ".join(column_values))
            except Exception as e:
                print(f"Error getting sample row: {e}")
    
    return schema_info

def recover_from_wallet(wallet_name):
    """
    Recover keys and funds from wallet using schema-adaptive approach
    """
    db_path = get_database_path()
    if not db_path:
        print("Could not find bitcoinlib database file.")
        return None
    
    print(f"Database found at: {db_path}")
    
    try:
        # Connect to SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Analyze schema
        schema_info = analyze_database_schema(conn)
        
        # Get wallet ID
        cursor.execute("SELECT id FROM wallets WHERE name=?", (wallet_name,))
        wallet_id_data = cursor.fetchone()
        
        if not wallet_id_data:
            print(f"Wallet '{wallet_name}' not found in database.")
            return None
        
        wallet_id = wallet_id_data[0]
        print(f"\nWallet ID: {wallet_id}")
        
        # Extract wallet info
        print("\n==== WALLET INFO ====")
        if 'wallets' in schema_info:
            columns = schema_info['wallets']
            column_str = ", ".join(columns)
            cursor.execute(f"SELECT {column_str} FROM wallets WHERE id=?", (wallet_id,))
            wallet_data = cursor.fetchone()
            
            if wallet_data:
                for i, col in enumerate(columns):
                    if wallet_data[i] is not None:
                        print(f"{col}: {wallet_data[i]}")
        
        # Extract keys using available columns
        print("\n==== KEYS ====")
        if 'keys' in schema_info:
            key_columns = schema_info['keys']
            needed_columns = ['id', 'address', 'path']
            optional_columns = ['wif', 'private', 'public', 'is_private']
            
            select_columns = []
            for col in needed_columns:
                if col in key_columns:
                    select_columns.append(col)
            
            for col in optional_columns:
                if col in key_columns:
                    select_columns.append(col)
            
            column_str = ", ".join(select_columns)
            
            cursor.execute(f"SELECT {column_str} FROM keys WHERE wallet_id=?", (wallet_id,))
            keys = cursor.fetchall()
            
            if keys:
                print(f"Found {len(keys)} keys")
                
                for key in keys:
                    print("\n----------------------------")
                    for i, col in enumerate(select_columns):
                        if col == 'private' and key[i]:
                            print(f"{col} (first bytes only): {str(key[i])[:30]}...")
                        else:
                            print(f"{col}: {key[i]}")
            else:
                print("No keys found")
        
        # Extract transactions and UTXOs using available columns
        print("\n==== TRANSACTIONS & UTXOs ====")
        if 'transactions' in schema_info:
            tx_columns = schema_info['transactions']
            
            # Find likely column names
            hash_column = next((col for col in tx_columns if 'hash' in col.lower() or 'txid' in col.lower()), None)
            output_column = next((col for col in tx_columns if 'output' in col.lower() or 'index' in col.lower()), None)
            value_column = next((col for col in tx_columns if 'value' in col.lower() or 'amount' in col.lower()), None)
            spent_column = next((col for col in tx_columns if 'spent' in col.lower()), None)
            
            if hash_column and value_column:
                query_parts = [hash_column, value_column]
                if output_column:
                    query_parts.append(output_column)
                
                where_clause = f"wallet_id={wallet_id}"
                if spent_column:
                    where_clause += f" AND {spent_column}=0"
                
                query = f"SELECT {', '.join(query_parts)} FROM transactions WHERE {where_clause}"
                
                try:
                    cursor.execute(query)
                    utxos = cursor.fetchall()
                    
                    if utxos:
                        print(f"Found {len(utxos)} unspent outputs")
                        total_value = 0
                        
                        for utxo in utxos:
                            print("\n----------------------------")
                            tx_hash = utxo[0]
                            value = utxo[1]
                            output_n = utxo[2] if len(utxo) > 2 else "unknown"
                            
                            print(f"Transaction hash: {tx_hash}")
                            print(f"Output index: {output_n}")
                            print(f"Value: {value / 1e8:.8f} BTC")
                            
                            total_value += value
                        
                        print(f"\nTotal value: {total_value / 1e8:.8f} BTC")
                    else:
                        print("No unspent outputs found")
                except Exception as e:
                    print(f"Error retrieving transactions: {e}")
            else:
                print("Could not identify required transaction columns")
        
        # Extract private keys for import
        print("\n==== PRIVATE KEYS ====")
        print("These can be imported into Electrum")
        
        private_keys_found = False
        
        # Try direct WIF extraction
        if 'keys' in schema_info and 'wif' in schema_info['keys']:
            cursor.execute(f"SELECT address, wif FROM keys WHERE wallet_id=? AND wif IS NOT NULL", (wallet_id,))
            wif_keys = cursor.fetchall()
            
            if wif_keys:
                private_keys_found = True
                print(f"Found {len(wif_keys)} WIF private keys:")
                
                for key in wif_keys:
                    address, wif = key
                    print(f"\nAddress: {address}")
                    print(f"WIF Private Key: {wif}")
                    print("👆 This key can be imported into Electrum")
        
        # Try to get master key if available
        if 'keys' in schema_info:
            # Try different potential column combinations for master key
            if 'private' in schema_info['keys']:
                cursor.execute(
                    "SELECT address, private FROM keys WHERE wallet_id=? AND path IN ('m', '') LIMIT 1",
                    (wallet_id,)
                )
                master_key = cursor.fetchone()
                
                if master_key:
                    address, private = master_key
                    print(f"\nMaster Key (use caution with raw format):")
                    print(f"Address: {address}")
                    print(f"Raw Private Key Data: {str(private)[:30]}...")
                    
                    # Export the raw private key bytes to a file
                    private_key_path = os.path.join(os.getcwd(), "private_key_export.bin")
                    try:
                        with open(private_key_path, 'wb') as f:
                            if isinstance(private, str):
                                f.write(private.encode('utf-8', 'ignore'))
                            else:
                                f.write(private)
                        print(f"\nExported raw private key data to: {private_key_path}")
                        print("This file might be useful for advanced recovery methods.")
                    except Exception as e:
                        print(f"Error exporting private key: {e}")
        
        if not private_keys_found:
            print("\nNo direct WIF private keys found. Advanced recovery might be needed.")
        
        conn.close()
        
        print("\n==== RECOVERY INSTRUCTIONS ====")
        print("1. If WIF private keys were found, import them directly into Electrum:")
        print("   - Wallet > Private Keys > Import")
        print("2. If only raw private key data was found, you'll need specialized tools")
        print("   - The exported private_key_export.bin file might help with advanced recovery")
        print("3. If you found UTXOs but no usable private keys, consider using a specialized")
        print("   Bitcoin recovery service (be extremely careful to verify their legitimacy)")
        
        return True
    except Exception as e:
        print(f"Error in recovery process: {e}")
        return None

def main():
    print("\n=======================")
    print("SCHEMA-ADAPTIVE BITCOIN RECOVERY TOOL")
    print("=======================")
    print("\n⚠️ WARNING: This tool accesses sensitive wallet information")
    print("Run this on a secure computer and don't share the output")
    
    # Get wallet name
    wallet_name = input("\nEnter wallet name (default: forwarding_wallet): ")
    if not wallet_name:
        wallet_name = "forwarding_wallet"
    
    # Recover from wallet
    recover_from_wallet(wallet_name)

if __name__ == "__main__":
    main()