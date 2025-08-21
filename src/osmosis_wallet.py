"""
osmosis_wallet.py - Osmosis Wallet Generation and Management
"""

import hashlib
import bech32
import ecdsa
from mnemonic import Mnemonic
import bip32utils
from typing import Tuple, Optional

class WalletGenerator:
    """Generate and manage Osmosis wallets"""
    
    @staticmethod
    def generate_mnemonic() -> str:
        """Generate a new 24-word mnemonic seed phrase"""
        try:
            mnemo = Mnemonic("english")
            return mnemo.generate(strength=256)  # 256 bits = 24 words
        except Exception as e:
            print(f"❌ Error generating mnemonic: {e}")
            return None
    
    @staticmethod
    def validate_mnemonic(mnemonic: str) -> bool:
        """Validate if mnemonic is correct"""
        try:
            mnemo = Mnemonic("english")
            return mnemo.check(mnemonic.strip())
        except Exception:
            return False
    
    @staticmethod
    def mnemonic_to_address_and_key(mnemonic: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Convert mnemonic to Osmosis address and private key using cosmpy
        
        Args:
            mnemonic: 24-word seed phrase
            
        Returns:
            Tuple of (osmosis_address, private_key_hex) or (None, None) on error
        """
        try:
            # Validate mnemonic first
            if not WalletGenerator.validate_mnemonic(mnemonic):
                print("❌ Invalid mnemonic phrase")
                return None, None
            
            from cosmpy.aerial.wallet import LocalWallet
            
            # Use cosmpy to derive wallet from mnemonic - this ensures consistency
            wallet = LocalWallet.from_mnemonic(mnemonic.strip(), prefix="osmo")
            
            # Get the private key hex
            private_key_hex = wallet._private_key.private_key_hex
            
            # Get the osmosis address
            osmosis_address = str(wallet.address())
            
            print(f"✅ CosmPy derived address: {osmosis_address}")
            
            return osmosis_address, private_key_hex
            
        except Exception as e:
            print(f"❌ Error deriving address from mnemonic: {e}")
            return None, None
    
    @staticmethod
    def create_new_wallet() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Create a completely new wallet
        
        Returns:
            Tuple of (mnemonic, osmosis_address, private_key_hex) or (None, None, None) on error
        """
        try:
            # Generate new mnemonic
            mnemonic = WalletGenerator.generate_mnemonic()
            if not mnemonic:
                return None, None, None
            
            # Derive address and private key
            address, private_key = WalletGenerator.mnemonic_to_address_and_key(mnemonic)
            if not address or not private_key:
                return None, None, None
            
            return mnemonic, address, private_key
            
        except Exception as e:
            print(f"❌ Error creating new wallet: {e}")
            return None, None, None

class WalletValidator:
    """Validate wallet addresses and related data"""
    
    @staticmethod
    def is_valid_osmosis_address(address: str) -> bool:
        """Validate if address is a valid Osmosis address"""
        try:
            if not address:
                return False
            
            # Check prefix
            if not address.startswith("osmo"):
                return False
            
            # Check length (Osmosis addresses are typically 43 characters)
            if len(address) != 43:
                return False
            
            # Try to decode bech32
            try:
                hrp, data = bech32.bech32_decode(address)
                if hrp != "osmo":
                    return False
                
                # Convert back to bytes
                decoded = bech32.convertbits(data, 5, 8, False)
                if decoded is None or len(decoded) != 20:
                    return False
                
                return True
                
            except Exception:
                return False
                
        except Exception:
            return False