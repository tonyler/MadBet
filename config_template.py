"""
config_template.py - Bot Configuration Settings Template
COPY THIS FILE TO config.py AND FILL IN YOUR VALUES
"""

import os
from typing import Dict, List

class BotConfig:
    """Bot configuration settings"""
    
    # Bot wallet configuration
    BOT_ADDRESS = "your_bot_address_here"
    BOT_SEED_PHRASE = "your_bot_seed_phrase_here"  # ⚠️ KEEP THIS SECRET!
    
    # Betting Configuration
    MIN_BET_AMOUNT = 0.1  # Minimum bet in OSMO
    BOT_FEE_PERCENTAGE = 5  # Bot takes 5% of total pool
    DEFAULT_BET_TOKEN = "osmo"  # Default token for betting
    
    # Admin Configuration
    ADMIN_ROLE_NAMES = [
        # Add Discord role names that have admin permissions
    ]
    
    ADMIN_USER_IDS = [
        # Add Discord user IDs that have admin permissions
        # Example: 123456789012345678,
    ]
    
    # Osmosis Blockchain Settings
    OSMOSIS_CHAIN_ID = "osmosis-1"
    OSMOSIS_RPC_ENDPOINTS = [
        "https://osmosis-rpc.polkachu.com",
        "https://rpc.osmosis.zone",
        "https://osmosis-rpc.quickapi.com"
    ]
    
    OSMOSIS_REST_ENDPOINTS = [
        "https://osmosis-api.polkachu.com", 
        "https://lcd.osmosis.zone",
        "https://osmosis-api.quickapi.com"
    ]
    
    # Time limits for bet locking
    VALID_TIME_UNITS = ['m', 'h', 'd']  # minutes, hours, days
    MAX_TIME_LIMIT_DAYS = 30  # Maximum time limit in days

def get_supported_token_list() -> List[str]:
    """Get list of supported betting tokens"""
    return ["osmo", "lab"]

def is_user_admin(user_id: int) -> bool:
    """Check if user ID has admin permissions"""
    return user_id in BotConfig.ADMIN_USER_IDS

def is_bet_locked(bet_data: dict) -> bool:
    """Check if a bet is locked for new participants"""
    # Implementation depends on your bet structure
    # Add your locking logic here
    return False

def parse_time_limit(time_str: str):
    """Parse time limit string (e.g., '2h', '30m', '1d')"""
    # Add your time parsing logic here
    pass