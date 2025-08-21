"""
osmjs_betting_engine.py - Simple OsmoJS-powered betting engine
Clean, simple integration with the OsmoJS service - no unnecessary complexity
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
from config import BotConfig

class OsmoJSBettingEngine:
    """Simple betting engine using OsmoJS service"""
    
    def __init__(self, osmjs_service_url: str = "http://localhost:3001"):
        self.osmjs_url = osmjs_service_url
        self.bot_address = BotConfig.BOT_ADDRESS
        self.bot_seed = BotConfig.BOT_SEED_PHRASE
        self.min_bet = BotConfig.MIN_BET_AMOUNT
        self.fee_percentage = BotConfig.BOT_FEE_PERCENTAGE
        self.default_token = BotConfig.DEFAULT_BET_TOKEN
        
        # Token denomination mapping
        self.token_to_denom = {
            "osmo": "uosmo",
            "lab": "factory/osmo17fel472lgzs87ekt9dvk0zqyh5gl80sqp4sk4n/LAB"
        }
    
    async def _make_osmjs_request(self, endpoint: str, data: Dict, retries: int = 3) -> Optional[Dict]:
        """Make request to OsmoJS service with simple retry logic"""
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(f"{self.osmjs_url}/{endpoint}", json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get("success"):
                                return result
                            else:
                                print(f"❌ OsmoJS {endpoint} failed: {result.get('error')}")
                                return result
                        else:
                            error_text = await response.text()
                            print(f"❌ OsmoJS HTTP {response.status}: {error_text}")
                            
            except Exception as e:
                print(f"⚠️ OsmoJS request attempt {attempt + 1} failed: {str(e)}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    print(f"❌ All OsmoJS request attempts failed for {endpoint}")
        
        return None
    
    async def health_check(self) -> bool:
        """Check if OsmoJS service is running"""
        try:
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.osmjs_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"💚 OsmoJS service healthy: {data.get('service')}")
                        return True
        except Exception as e:
            print(f"❌ OsmoJS health check failed: {e}")
        return False
    
    async def lazy_health_check(self) -> bool:
        """Silently check if OsmoJS service is running (no error output)"""
        try:
            timeout = aiohttp.ClientTimeout(total=3.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.osmjs_url}/health") as response:
                    return response.status == 200
        except:
            return False
    
    async def get_balance(self, address: str, token: str = "osmo") -> Optional[Dict]:
        """Get account balance using OsmoJS"""
        denom = self.token_to_denom.get(token.lower(), f"u{token.lower()}")
        
        data = {
            "address": address,
            "denom": denom
        }
        
        result = await self._make_osmjs_request("balance", data)
        if result and result.get("success"):
            balance_info = result["balance"]
            return {
                "denom": balance_info["denom"],
                "amount": float(balance_info["amount"]) / 1e6,  # Convert from micro units
                "formatted": balance_info["formatted"]
            }
        return None
    
    async def validate_bet_amount(self, user_id: int, amount_str: str, token: str = "osmo", wallet: dict = None) -> Tuple[bool, str, Decimal]:
        """Validate bet amount and user balance using OsmoJS"""
        try:
            # Parse amount
            amount = Decimal(amount_str)
            if amount <= 0:
                return False, "Bet amount must be positive", Decimal(0)
            
            if amount < Decimal(str(self.min_bet)):
                return False, f"Minimum bet amount is {self.min_bet} {token.upper()}", Decimal(0)
            
            # Check if user has wallet
            if not wallet:
                return False, "You don't have a wallet. Use `/create_wallet` first", Decimal(0)
            
            # Check user balance using OsmoJS
            balance_info = await self.get_balance(wallet["address"], token)
            if not balance_info:
                return False, f"Unable to check your {token.upper()} balance", Decimal(0)
            
            user_balance = Decimal(str(balance_info["amount"]))
            
            if user_balance < amount:
                return False, f"Insufficient balance. You have {user_balance} {token.upper()}, need {amount}", Decimal(0)
            
            return True, "Valid bet amount", amount
            
        except ValueError:
            return False, "Invalid amount format", Decimal(0)
        except Exception as e:
            return False, f"Error validating bet: {str(e)}", Decimal(0)
    
    async def place_bet_with_escrow(self, user_id: int, username: str, bet_id: int, 
                                   amount_str: str, option_index: int, token: str = "osmo", wallet: dict = None) -> Dict:
        """Place a bet with token transfer to bot escrow using OsmoJS"""
        try:
            # Validate bet amount and balance
            is_valid, error_msg, amount = await self.validate_bet_amount(user_id, amount_str, token, wallet)
            if not is_valid:
                return {"success": False, "error": error_msg}
            
            # Check wallet
            if not wallet:
                return {"success": False, "error": "No wallet found"}
            
            # Transfer tokens to bot escrow using OsmoJS single send
            send_data = {
                "sender_mnemonic": wallet["mnemonic"],
                "recipient_address": self.bot_address,
                "amount": amount_str,
                "token": token,
                "memo": f"Bet #{bet_id} - Option {option_index + 1}"
            }
            
            result = await self._make_osmjs_request("send", send_data)
            
            if not result or not result.get("success"):
                error_msg = result.get("error", "Unknown transaction error") if result else "OsmoJS service unavailable"
                return {"success": False, "error": f"Transfer failed: {error_msg}"}
            
            # Store bet with transaction details
            bet_record = {
                "user_id": user_id,
                "username": username,
                "amount": float(amount),
                "amount_str": amount_str,
                "option": option_index,
                "token": token,
                "tx_hash": result["tx_hash"],
                "height": result.get("height", 0),
                "gas_used": result.get("gas_used", "0"),
                "fee_paid": result.get("fee_paid", "0"),
                "timestamp": datetime.now().isoformat(),
                "escrow_address": self.bot_address,
                "osmjs_powered": True
            }
            
            return {
                "success": True, 
                "bet_record": bet_record,
                "transaction": result
            }
            
        except Exception as e:
            return {"success": False, "error": f"Betting error: {str(e)}"}
    
    async def calculate_payouts(self, bet_data: dict, winning_option_index: int) -> Dict:
        """Calculate payouts including bot fee"""
        try:
            participants = bet_data.get("participants", [])
            if not participants:
                return {
                    "success": True, 
                    "no_participants": True,
                    "total_pool": 0,
                    "bot_fee": 0,
                    "payout_pool": 0,
                    "winners": [],
                    "no_winners": True
                }
            
            print(f"📊 OsmoJS: Processing {len(participants)} participants for winning option {winning_option_index}")
            
            # Calculate totals with enhanced precision
            bet_amount = Decimal(str(bet_data.get('bet_amount', 0)))
            bet_token = bet_data.get('bet_token', 'osmo')
            
            winners = []
            valid_participants = []
            
            # Validate and filter participants
            for i, participant in enumerate(participants):
                if not isinstance(participant, dict) or 'user_id' not in participant:
                    print(f"⚠️ Skipping invalid participant {i}: {participant}")
                    continue
                    
                valid_participants.append(participant)
                if participant.get("option") == winning_option_index:
                    winners.append(participant)
            
            if len(valid_participants) == 0:
                return {"success": False, "error": "No valid participants found"}
            
            total_participants = len(valid_participants)
            total_pool = bet_amount * total_participants
            
            # Handle no winners case
            if not winners:
                return {
                    "success": True,
                    "total_pool": float(total_pool),
                    "winners": [],
                    "bot_fee": float(total_pool * Decimal(str(self.fee_percentage)) / Decimal(100)),
                    "bot_fee_percentage": self.fee_percentage,
                    "no_winners": True,
                    "token": bet_token,
                    "refund_needed": False
                }
            
            # Calculate payouts with precise arithmetic
            bot_fee = total_pool * Decimal(str(self.fee_percentage)) / Decimal(100)
            payout_pool = total_pool - bot_fee
            num_winners = len(winners)
            payout_per_winner = payout_pool / Decimal(num_winners)
            
            # Create precise payout list for OsmoJS
            payouts = []
            for winner in winners:
                user_id = winner.get("user_id")
                username = winner.get("username", "Unknown")
                
                if user_id is None:
                    print(f"⚠️ Skipping winner without user_id: {winner}")
                    continue
                
                # Use string format to maintain precision for OsmoJS
                payout_amount_str = f"{float(payout_per_winner):.6f}"
                
                payouts.append({
                    "user_id": user_id,
                    "username": username,
                    "original_bet": float(bet_amount),
                    "payout": float(payout_per_winner),
                    "payout_str": payout_amount_str,  # Precise string for OsmoJS
                    "profit": float(payout_per_winner - bet_amount),
                    "token": bet_token
                })
            
            return {
                "success": True,
                "total_pool": float(total_pool),
                "bot_fee": float(bot_fee),
                "bot_fee_percentage": self.fee_percentage,
                "payout_pool": float(payout_pool),
                "winners": payouts,
                "no_winners": False,
                "token": bet_token,
                "osmjs_ready": True
            }
            
        except Exception as e:
            return {"success": False, "error": f"Payout calculation error: {str(e)}"}
    
    async def distribute_payouts_multisend(self, payout_data: Dict, wallet_lookup_func=None) -> Dict:
        """Distribute payouts using OsmoJS multisend for maximum efficiency"""
        try:
            if not payout_data.get("success") or payout_data.get("no_winners"):
                return {"success": False, "error": "No valid payouts to distribute"}
            
            winners = payout_data.get("winners", [])
            if not winners:
                return {"success": False, "error": "No winners to pay out"}
            
            print(f"💰 OsmoJS Multisend: Processing {len(winners)} winners")
            
            # Build recipients list for OsmoJS multisend
            recipients = []
            failed_preparations = []
            
            for winner in winners:
                try:
                    user_id = winner["user_id"]
                    username = winner["username"]
                    
                    # Get winner's wallet address
                    wallet = wallet_lookup_func(user_id) if wallet_lookup_func else None
                    if not wallet:
                        print(f"❌ Wallet not found for winner {username} ({user_id})")
                        failed_preparations.append({
                            "user_id": user_id,
                            "username": username,
                            "error": "Winner's wallet not found"
                        })
                        continue
                    
                    # Add to multisend recipients with precise amount
                    recipients.append({
                        "address": wallet["address"],
                        "amount": winner["payout_str"],  # Use precise string amount
                        "token": winner["token"],
                        "user_id": user_id,  # Keep for tracking
                        "username": username
                    })
                    
                except Exception as e:
                    print(f"❌ Failed to prepare winner {winner.get('username', 'Unknown')}: {str(e)}")
                    failed_preparations.append({
                        "user_id": winner.get("user_id", 0),
                        "username": winner.get("username", "Unknown"),
                        "error": f"Preparation failed: {str(e)}"
                    })
            
            if not recipients:
                return {
                    "success": False,
                    "error": "No valid recipients prepared for multisend",
                    "failed_payouts": failed_preparations,
                    "successful_payouts": []
                }
            
            # Execute OsmoJS multisend
            multisend_data = {
                "sender_mnemonic": self.bot_seed,
                "recipients": recipients,
                "memo": f"Betting Payouts - {len(recipients)} winners"
            }
            
            print(f"📤 Executing OsmoJS multisend for {len(recipients)} recipients...")
            result = await self._make_osmjs_request("multisend", multisend_data)
            
            if not result or not result.get("success"):
                error_msg = result.get("error", "Multisend transaction failed") if result else "OsmoJS service unavailable"
                return {
                    "success": False,
                    "error": f"Multisend failed: {error_msg}",
                    "failed_payouts": failed_preparations + [{"error": "Multisend transaction failed", "recipients": len(recipients)}],
                    "successful_payouts": []
                }
            
            # All recipients in multisend succeeded
            successful_payouts = []
            for recipient in recipients:
                successful_payouts.append({
                    "user_id": recipient["user_id"],
                    "username": recipient["username"],
                    "amount": float(recipient["amount"]),
                    "token": recipient["token"],
                    "tx_hash": result["tx_hash"],
                    "address": recipient["address"],
                    "height": result.get("height", 0),
                    "gas_used": result.get("gas_used", "0"),
                    "osmjs_multisend": True
                })
            
            print(f"✅ OsmoJS Multisend successful: {result['tx_hash']}")
            print(f"📊 Gas used: {result.get('gas_used', 'unknown')}, Fee: {result.get('fee_paid', 'unknown')}")
            
            return {
                "success": True,
                "successful_payouts": successful_payouts,
                "failed_payouts": failed_preparations,
                "tx_hash": result["tx_hash"],
                "height": result.get("height", 0),
                "gas_used": result.get("gas_used", "0"),
                "fee_paid": result.get("fee_paid", "0"),
                "recipients_count": result.get("recipients_count", len(recipients)),
                "total_winners": len(winners),
                "multisend_efficiency": f"{len(successful_payouts)}/{len(winners)} in 1 transaction",
                "bot_fee_retained": payout_data.get("bot_fee", 0),
                "osmjs_powered": True
            }
            
        except Exception as e:
            print(f"❌ Critical error in OsmoJS multisend distribution: {str(e)}")
            return {"success": False, "error": f"Distribution error: {str(e)}"}
    
    async def distribute_refunds_multisend(self, bet_data: Dict, wallet_lookup_func=None) -> Dict:
        """Distribute refunds using OsmoJS multisend when bet is cancelled"""
        try:
            participants = bet_data.get("participants", [])
            if not participants:
                return {"success": False, "error": "No participants to refund"}
            
            bet_amount = bet_data.get("bet_amount", 0)
            bet_token = bet_data.get("bet_token", "osmo")
            
            print(f"🔄 OsmoJS Refund Multisend: Processing {len(participants)} participants")
            
            # Build recipients list for refunds
            recipients = []
            failed_preparations = []
            
            for participant in participants:
                try:
                    user_id = participant.get("user_id")
                    username = participant.get("username", "Unknown")
                    
                    if user_id is None:
                        failed_preparations.append({
                            "user_id": 0,
                            "username": username,
                            "error": "Invalid participant data - missing user_id"
                        })
                        continue
                    
                    # Get participant's wallet address
                    wallet = wallet_lookup_func(user_id) if wallet_lookup_func else None
                    if not wallet:
                        print(f"❌ Wallet not found for participant {username} ({user_id})")
                        failed_preparations.append({
                            "user_id": user_id,
                            "username": username,
                            "error": "Participant's wallet not found"
                        })
                        continue
                    
                    # Use participant's individual token and amount (critical fix)
                    participant_token = participant.get("token", bet_token)  # Fallback to bet_token if missing
                    participant_amount = participant.get("amount", bet_amount)  # Use actual amount they bet
                    refund_amount_str = f"{participant_amount:.6f}"
                    
                    recipients.append({
                        "address": wallet["address"],
                        "amount": refund_amount_str,
                        "token": participant_token,
                        "user_id": user_id,
                        "username": username
                    })
                    
                except Exception as e:
                    print(f"❌ Failed to prepare refund for {participant.get('username', 'Unknown')}: {str(e)}")
                    failed_preparations.append({
                        "user_id": participant.get("user_id", 0),
                        "username": participant.get("username", "Unknown"),
                        "error": f"Preparation failed: {str(e)}"
                    })
            
            if not recipients:
                return {
                    "success": False,
                    "error": "No valid recipients prepared for refund multisend",
                    "failed_refunds": failed_preparations,
                    "successful_refunds": []
                }
            
            # Execute OsmoJS multisend for refunds
            multisend_data = {
                "sender_mnemonic": self.bot_seed,
                "recipients": recipients,
                "memo": f"Bet Cancellation Refunds - {len(recipients)} participants"
            }
            
            print(f"🔄 Executing OsmoJS refund multisend for {len(recipients)} recipients...")
            result = await self._make_osmjs_request("multisend", multisend_data)
            
            if not result or not result.get("success"):
                error_msg = result.get("error", "Refund multisend failed") if result else "OsmoJS service unavailable"
                return {
                    "success": False,
                    "error": f"Refund multisend failed: {error_msg}",
                    "failed_refunds": failed_preparations + [{"error": "Refund multisend transaction failed", "recipients": len(recipients)}],
                    "successful_refunds": []
                }
            
            # All recipients in multisend succeeded
            successful_refunds = []
            for recipient in recipients:
                successful_refunds.append({
                    "user_id": recipient["user_id"],
                    "username": recipient["username"],
                    "amount": float(recipient["amount"]),
                    "token": recipient["token"],
                    "tx_hash": result["tx_hash"],
                    "address": recipient["address"],
                    "height": result.get("height", 0),
                    "gas_used": result.get("gas_used", "0"),
                    "osmjs_refund": True
                })
            
            print(f"✅ OsmoJS Refund Multisend successful: {result['tx_hash']}")
            print(f"📊 Gas used: {result.get('gas_used', 'unknown')}, Fee: {result.get('fee_paid', 'unknown')}")
            
            return {
                "success": True,
                "successful_refunds": successful_refunds,
                "failed_refunds": failed_preparations,
                "tx_hash": result["tx_hash"],
                "height": result.get("height", 0),
                "gas_used": result.get("gas_used", "0"),
                "fee_paid": result.get("fee_paid", "0"),
                "recipients_count": result.get("recipients_count", len(recipients)),
                "total_participants": len(participants),
                "refund_efficiency": f"{len(successful_refunds)}/{len(participants)} in 1 transaction",
                "osmjs_powered": True
            }
            
        except Exception as e:
            print(f"❌ Critical error in OsmoJS refund multisend: {str(e)}")
            return {"success": False, "error": f"Refund error: {str(e)}"}
    
    async def get_bot_balance(self, token: str = "osmo") -> Optional[Dict]:
        """Get bot's current balance using OsmoJS"""
        return await self.get_balance(self.bot_address, token)
    
    async def send_tokens(self, sender_mnemonic: str, recipient_address: str, amount: str, token: str = "osmo") -> Dict:
        """Send tokens using OsmoJS service"""
        try:
            send_data = {
                "sender_mnemonic": sender_mnemonic,
                "recipient_address": recipient_address,
                "amount": amount,
                "token": token,
                "memo": "Token transfer"
            }
            
            result = await self._make_osmjs_request("send", send_data)
            
            if not result or not result.get("success"):
                error_msg = result.get("error", "Unknown transaction error") if result else "OsmoJS service unavailable"
                return {"success": False, "error": error_msg}
            
            return {
                "success": True,
                "tx_hash": result["tx_hash"],
                "height": result.get("height", 0),
                "gas_used": result.get("gas_used", "0"),
                "fee_paid": result.get("fee_paid", "0")
            }
            
        except Exception as e:
            return {"success": False, "error": f"Send error: {str(e)}"}

# Helper functions for wallet lookups from existing systems
def load_wallets_data(wallets_file="user_wallets.json"):
    """Load wallets from JSON file"""
    try:
        import os
        import json
        if os.path.exists(wallets_file):
            with open(wallets_file, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading wallets: {e}")
        return {}

def get_user_wallet(user_id: int, wallets_file="user_wallets.json"):
    """Get user wallet from JSON file"""
    wallets = load_wallets_data(wallets_file)
    return wallets.get(str(user_id))