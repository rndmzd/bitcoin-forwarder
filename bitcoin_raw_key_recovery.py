#!/usr/bin/env python3
"""
Bitcoin Raw Key Data Recovery Tool

This script attempts to recover a usable private key from raw key data.
It tries multiple formats and encoding types to convert the raw data
into a WIF format that can be used in Electrum.
"""

import os
import sys
import binascii
import hashlib
import base58
import codecs

def sha256(data):
    """Calculate SHA256 hash"""
    return hashlib.sha256(data).digest()

def convert_to_wif(private_key_bytes):
    """Convert raw private key bytes to WIF format"""
    # Add version byte (0x80 for mainnet)
    extended_key = b'\x80' + private_key_bytes
    
    # Add compression flag (optional)
    # extended_key += b'\x01'  # Uncomment to generate compressed WIF
    
    # Double SHA-256 hash for checksum
    checksum = sha256(sha256(extended_key))[:4]
    
    # Combine and encode
    wif_key = base58.b58encode(extended_key + checksum)
    
    return wif_key.decode('utf-8')

def extract_private_key(raw_data):
    """
    Try different approaches to extract a private key from raw data
    """
    results = []
    attempted_formats = []
    
    # Try to interpret as direct 32-byte private key
    if len(raw_data) >= 32:
        private_key_bytes = raw_data[:32]
        wif = convert_to_wif(private_key_bytes)
        results.append({
            'method': 'Direct 32-byte key',
            'wif': wif,
            'raw_bytes': binascii.hexlify(private_key_bytes).decode('utf-8')
        })
        attempted_formats.append('Direct 32-byte key')
    
    # Try to find a 32-byte sequence with a standard prefix
    for offset in range(0, len(raw_data) - 32, 8):
        private_key_bytes = raw_data[offset:offset+32]
        wif = convert_to_wif(private_key_bytes)
        results.append({
            'method': f'32-byte sequence at offset {offset}',
            'wif': wif,
            'raw_bytes': binascii.hexlify(private_key_bytes).decode('utf-8')
        })
        attempted_formats.append(f'32-byte sequence at offset {offset}')
    
    # Try to interpret as hex string
    try:
        hex_str = raw_data.decode('utf-8').strip()
        if len(hex_str) >= 64:  # A private key is 32 bytes = 64 hex chars
            hex_key = hex_str[:64]
            private_key_bytes = binascii.unhexlify(hex_key)
            wif = convert_to_wif(private_key_bytes)
            results.append({
                'method': 'Hex string',
                'wif': wif,
                'raw_bytes': hex_key
            })
            attempted_formats.append('Hex string')
    except:
        pass
    
    # Try to interpret as Base58Check encoded data
    try:
        base58_str = raw_data.decode('utf-8').strip()
        try:
            decoded = base58.b58decode(base58_str)
            # If this is a WIF already, just return it
            if decoded[0] == 0x80 and (len(decoded) == 37 or len(decoded) == 38):
                results.append({
                    'method': 'Already WIF format',
                    'wif': base58_str,
                    'raw_bytes': binascii.hexlify(decoded[1:33]).decode('utf-8')
                })
                attempted_formats.append('Already WIF format')
        except:
            pass
    except:
        pass
    
    return results, attempted_formats

def process_raw_key_file(filename):
    """
    Process a file containing raw key data
    """
    if not os.path.exists(filename):
        print(f"Error: File {filename} not found")
        return None
    
    try:
        with open(filename, 'rb') as f:
            raw_data = f.read()
        
        print(f"Read {len(raw_data)} bytes from {filename}")
        
        if len(raw_data) < 32:
            print("Warning: File is too small to contain a valid private key (need at least 32 bytes)")
        
        # Show first few bytes in hex
        print(f"First 64 bytes in hex: {binascii.hexlify(raw_data[:64]).decode('utf-8')}")
        
        # Try to extract private key
        print("\nAttempting to extract private key...")
        results, attempted_formats = extract_private_key(raw_data)
        
        if not results:
            print("Could not extract private key. Attempted formats:", ", ".join(attempted_formats))
            return None
        
        # Display results
        print(f"Generated {len(results)} possible private keys")
        print("============================================")
        
        for i, result in enumerate(results, 1):
            print(f"\nPossible Key #{i}:")
            print(f"Method: {result['method']}")
            print(f"WIF Private Key: {result['wif']}")
            print(f"Raw Bytes (hex): {result['raw_bytes']}")
        
        # Output to file
        output_file = "recovered_keys.txt"
        with open(output_file, 'w') as f:
            f.write("Recovered Bitcoin Private Keys\n")
            f.write("=============================\n\n")
            
            for i, result in enumerate(results, 1):
                f.write(f"Possible Key #{i}:\n")
                f.write(f"Method: {result['method']}\n")
                f.write(f"WIF Private Key: {result['wif']}\n")
                f.write(f"Raw Bytes (hex): {result['raw_bytes']}\n\n")
        
        print(f"\nSaved all possible keys to {output_file}")
        print("\nINSTRUCTIONS:")
        print("1. Open Electrum")
        print("2. Go to Wallet > Private Keys > Sweep")
        print("3. Try each WIF key until you find one that works")
        
        return results
    
    except Exception as e:
        print(f"Error processing file: {e}")
        return None

def main():
    print("\n======================================")
    print("BITCOIN RAW KEY DATA RECOVERY TOOL")
    print("======================================")
    
    # Check if we have the required libraries
    try:
        import base58
    except ImportError:
        print("Error: Missing required library 'base58'")
        print("Please install it with: pip install base58")
        sys.exit(1)
    
    # Get input file
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        default_file = "private_key_export.bin"
        if os.path.exists(default_file):
            filename = default_file
            print(f"Using default file: {default_file}")
        else:
            filename = input("Enter the path to the raw key file: ")
    
    # Process the file
    process_raw_key_file(filename)

if __name__ == "__main__":
    main()