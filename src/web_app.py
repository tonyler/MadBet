"""
web_app.py - Web frontend for Discord betting bot
Displays active bets and past results by reading JSON files only
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
import json
import os
import requests
import logging
from datetime import datetime
from typing import Dict, List, Optional
from config import get_supported_token_list, is_bet_locked, parse_time_limit

app = Flask(__name__, 
           template_folder=os.path.join(os.path.dirname(__file__), '..', 'web', 'templates'),
           static_folder=os.path.join(os.path.dirname(__file__), '..', 'web', 'static'))

# Configure logging to match bot.logs format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'logs', 'webapp.logs')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log_webapp_action(action: str, details: dict = None, user_info: str = None, status: str = "INFO"):
    """Log web app actions in structured format matching bot.logs"""
    emoji_map = {
        "INFO": "🌐",
        "SUCCESS": "✅", 
        "ERROR": "❌",
        "WARNING": "⚠️"
    }
    
    emoji = emoji_map.get(status, "🌐")
    
    parts = [f"{emoji} WEBAPP"]
    
    if user_info:
        parts.append(f"User: {user_info}")
    
    parts.append(f"Action: {action}")
    
    if details:
        for key, value in details.items():
            if value is not None:
                parts.append(f"{key}={value}")
    
    log_message = " | ".join(parts)
    
    if status == "ERROR":
        logger.error(log_message)
    elif status == "WARNING":
        logger.warning(log_message)
    else:
        logger.info(log_message)

def log_bet_creation(bet_data: dict, user_info: str = None):
    log_webapp_action(
        "CREATE_BET", 
        {
            "bet_id": bet_data.get("id"),
            "question": f"{bet_data.get('question', '')[:20]}...",
            "amount": bet_data.get("bet_amount"),
            "token": bet_data.get("bet_token", "").upper(),
            "options_count": len(bet_data.get("options", []))
        },
        user_info,
        "SUCCESS"
    )

def log_bet_placement(bet_id: int, wallet_address: str, option: int, amount: float, token: str, tx_hash: str = None, status: str = "SUCCESS"):
    details = {
        "bet_id": bet_id,
        "wallet": f"{wallet_address[:6]}...{wallet_address[-4:]}",
        "option": option,
        "amount": amount,
        "token": token.upper()
    }
    
    if tx_hash:
        details["tx_hash"] = tx_hash[:16] if len(tx_hash) > 16 else tx_hash
    
    log_webapp_action("PLACE_BET", details, wallet_address[:10], status)

def log_api_call(endpoint: str, method: str, user_info: str = None, status_code: int = None, duration_ms: float = None):
    details = {
        "endpoint": endpoint,
        "method": method
    }
    
    if status_code:
        details["status"] = status_code
    
    if duration_ms:
        details["duration"] = f"{duration_ms:.2f}ms"
    
    status = "SUCCESS" if status_code and status_code < 400 else "ERROR" if status_code and status_code >= 400 else "INFO"
    log_webapp_action("API_CALL", details, user_info, status)

class BetDataManager:
    """Manages betting data - reads from and writes to JSON files"""
    
    MAX_BETS = 100  # Maximum bets to keep (circular buffer)
    
    def __init__(self, bets_file=None, wallets_file=None):
        if bets_file is None:
            bets_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'bets_data.json')
        if wallets_file is None:
            wallets_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'user_wallets.json')
        self.bets_file = bets_file
        self.wallets_file = wallets_file
        self._user_cache = {}
    
    def get_bet_storage_key(self, bet_id: int) -> str:
        """Get circular buffer storage key for bet ID"""
        storage_slot = bet_id % self.MAX_BETS
        if storage_slot == 0:
            storage_slot = self.MAX_BETS
        return str(storage_slot)
    
    def load_bets_data(self) -> Dict:
        try:
            if os.path.exists(self.bets_file):
                with open(self.bets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"bets": {}, "bet_id_counter": 0}
        except Exception as e:
            print(f"Error loading bets data: {e}")
            return {"bets": {}, "bet_id_counter": 0}
    
    def load_wallets_data(self) -> Dict:
        try:
            if os.path.exists(self.wallets_file):
                with open(self.wallets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error loading wallets data: {e}")
            return {}
    
    def calculate_total_pool(self, bet: Dict) -> float:
        participants = bet.get("participants", [])
        bet_amount = bet.get("bet_amount", 0)
        
        total_pool = len(participants) * bet_amount
        return total_pool
    
    def get_active_bets(self) -> List[Dict]:
        data = self.load_bets_data()
        bets = data.get("bets", {})
        
        active_bets = []
        for bet_id, bet in bets.items():
            if bet.get("is_active", False):
                if is_bet_locked(bet):
                    continue
                    
                bet["total_pool"] = self.calculate_total_pool(bet)
                
                bet["lock_info"] = self.get_bet_lock_info(bet)
                
                active_bets.append(bet)
        
        active_bets.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return active_bets
    
    def get_bet_lock_info(self, bet_data: Dict) -> Dict:
        from datetime import datetime
        
        lock_time_str = bet_data.get('lock_time')
        if not lock_time_str:
            return {"type": "indefinite", "display": "Never locks"}
        
        if lock_time_str.lower() in ['indefinite', 'never', '∞', 'infinite']:
            return {"type": "indefinite", "display": "Never locks"}
        
        try:
            lock_time = datetime.fromisoformat(lock_time_str.replace('Z', '+00:00'))
            now = datetime.now()
            
            if now >= lock_time:
                return {"type": "locked", "display": "Locked"}
            
            time_remaining = lock_time - now
            days = time_remaining.days
            hours, remainder = divmod(time_remaining.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                display = f"Locks in {days}d {hours}h"
            elif hours > 0:
                display = f"Locks in {hours}h {minutes}m"
            else:
                display = f"Locks in {minutes}m"
                
            return {
                "type": "countdown", 
                "display": display,
                "lock_time": lock_time_str,
                "remaining_minutes": int(time_remaining.total_seconds() / 60)
            }
        except (ValueError, AttributeError):
            return {"type": "indefinite", "display": "Never locks"}
    
    def get_bet_by_id(self, bet_id: int) -> Optional[Dict]:
        data = self.load_bets_data()
        bets = data.get("bets", {})
        storage_key = self.get_bet_storage_key(bet_id)
        bet = bets.get(storage_key)
        
        if bet:
            bet["total_pool"] = self.calculate_total_pool(bet)
            
            bet["lock_info"] = self.get_bet_lock_info(bet)
        
        return bet
    
    def build_user_mapping(self) -> Dict[int, str]:
        if self._user_cache:
            return self._user_cache
        
        data = self.load_bets_data()
        bets = data.get("bets", {})
        user_mapping = {}
        
        for bet in bets.values():
            for participant in bet.get("participants", []):
                user_id = participant.get("user_id")
                username = participant.get("username")
                if user_id and username:
                    user_mapping[user_id] = username
            
            if "distribution_result" in bet:
                for payout in bet["distribution_result"].get("successful_payouts", []):
                    user_id = payout.get("user_id")
                    username = payout.get("username")
                    if user_id and username:
                        user_mapping[user_id] = username
            
            if "refund_results" in bet:
                for refund in bet["refund_results"].get("successful_refunds", []):
                    user_id = refund.get("user_id")
                    username = refund.get("username")
                    if user_id and username:
                        user_mapping[user_id] = username
        
        self._user_cache = user_mapping
        return user_mapping
    
    def get_username(self, user_id_or_name) -> str:
        if isinstance(user_id_or_name, str):
            return user_id_or_name
        
        try:
            user_id = int(user_id_or_name)
            user_mapping = self.build_user_mapping()
            return user_mapping.get(user_id, f"User#{user_id}")
        except (ValueError, TypeError):
            return str(user_id_or_name)
    
    def get_bet_statistics(self) -> Dict:
        data = self.load_bets_data()
        bets = data.get("bets", {})
        
        active_bets = [bet for bet in bets.values() if bet.get("is_active", False)]
        completed_bets = [bet for bet in bets.values() if not bet.get("is_active", True)]
        
        total_active = len(active_bets)
        total_participants = sum(len(bet.get("participants", [])) for bet in active_bets)
        
        total_volume = sum(self.calculate_total_pool(bet) for bet in completed_bets)
        
        total_payouts = 0
        for bet in completed_bets:
            if "payout_data" in bet:
                payout_data = bet["payout_data"]
                total_payouts += payout_data.get("payout_pool", 0)
        
        return {
            "active_bets": total_active,
            "total_participants": total_participants,
            "total_volume": round(total_volume, 6),
            "total_payouts": round(total_payouts, 6)
        }
    
    def save_bets_data(self, data: Dict) -> bool:
        try:
            data["last_saved"] = datetime.now().isoformat()
            
            with open(self.bets_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving bets data: {e}")
            return False
    
    def add_webapp_bet(self, bet_id: int, wallet_address: str, option_index: int, 
                      amount: float, token: str, tx_hash: str = None, 
                      block_height: int = None, gas_used: str = None) -> Dict:
        """Add a webapp bet to the JSON data"""
        try:
            # Load current data
            data = self.load_bets_data()
            bets = data.get("bets", {})
            bet_key = self.get_bet_storage_key(bet_id)
            
            if bet_key not in bets:
                return {"success": False, "error": "Bet not found"}
            
            bet = bets[bet_key]
            
            # Check if bet is still active
            if not bet.get("is_active", False):
                return {"success": False, "error": "Bet is no longer active"}
            
            # Check if bet is locked
            if is_bet_locked(bet):
                return {"success": False, "error": "Bet is locked and no longer accepting new participants"}
            
            # Check if user already bet (by wallet address)
            existing_participant = None
            for participant in bet.get("participants", []):
                if participant.get("wallet_address") == wallet_address:
                    existing_participant = participant
                    break
            
            if existing_participant:
                return {"success": False, "error": "You have already placed a bet on this question"}
            
            # Create new participant entry
            new_participant = {
                "wallet_address": wallet_address,
                "username": f"{wallet_address[:6]}...{wallet_address[-4:]}",
                "amount": amount,
                "amount_str": str(amount),
                "option": option_index,
                "token": token.lower(),
                "timestamp": datetime.now().isoformat(),
                "source": "webapp"
            }
            
            # Add transaction details - only real transactions allowed
            if not tx_hash or tx_hash.startswith('SIM_'):
                return {"success": False, "error": "Real transaction hash required - no simulations allowed"}
            
            new_participant["tx_hash"] = tx_hash
            new_participant["real_transaction"] = True
            
            if block_height is not None:
                new_participant["block_height"] = block_height
            if gas_used:
                new_participant["gas_used"] = gas_used
            
            # All transactions are now real - no endpoint issue handling needed
            
            # Add participant to bet
            bet["participants"].append(new_participant)
            
            # Note: total_pool is now calculated dynamically, no need to store it
            
            # Save updated data
            if self.save_bets_data(data):
                return {
                    "success": True, 
                    "message": "Bet placed successfully",
                    "participant": new_participant
                }
            else:
                return {"success": False, "error": "Failed to save bet data"}
                
        except Exception as e:
            print(f"Error adding webapp bet: {e}")
            return {"success": False, "error": f"Internal error: {str(e)}"}
    
    def get_user_bets(self, wallet_address: str) -> List[Dict]:
        """Get all bets placed by a specific wallet address"""
        try:
            data = self.load_bets_data()
            bets = data.get("bets", {})
            user_bets = []
            
            for bet_id, bet in bets.items():
                for participant in bet.get("participants", []):
                    if participant.get("wallet_address") == wallet_address:
                        user_bets.append({
                            "bet_id": int(bet_id),
                            "option_index": participant.get("option"),
                            "amount": participant.get("amount"),
                            "token": participant.get("token"),
                            "timestamp": participant.get("timestamp"),
                            "bet_question": bet.get("question"),
                            "bet_active": bet.get("is_active", False)
                        })
                        break  # User can only bet once per bet
            
            return user_bets
            
        except Exception as e:
            print(f"Error getting user bets: {e}")
            return []
    
    def generate_bet_id(self) -> int:
        """Generate unique bet ID"""
        data = self.load_bets_data()
        current_counter = data.get("bet_id_counter", 1)
        new_id = current_counter
        
        # Update counter for next bet
        data["bet_id_counter"] = current_counter + 1
        self.save_bets_data(data)
        
        return new_id
    
    def save_bet(self, bet: Dict) -> Dict:
        """Save a new bet to the JSON file"""
        try:
            # Load current data
            data = self.load_bets_data()
            bets = data.get("bets", {})
            
            # Add new bet (use circular buffer key)
            storage_key = self.get_bet_storage_key(bet["id"])
            bets[storage_key] = bet
            data["bets"] = bets
            
            # Save updated data
            if self.save_bets_data(data):
                return {"success": True, "message": "Bet saved successfully"}
            else:
                return {"success": False, "error": "Failed to save bet data"}
                
        except Exception as e:
            print(f"Error saving bet: {e}")
            return {"success": False, "error": f"Internal error: {str(e)}"}
    

# Initialize data manager
data_manager = BetDataManager()

@app.route('/')
def index():
    """Homepage showing active bets and search"""
    start_time = datetime.now()
    try:
        bets = data_manager.get_active_bets()
        stats = data_manager.get_bet_statistics()
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/", "GET", 
                    user_info=request.remote_addr, 
                    status_code=200, 
                    duration_ms=duration_ms)
        
        return render_template('index.html', bets=bets, stats=stats)
    except Exception as e:
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/", "GET", 
                    user_info=request.remote_addr, 
                    status_code=500, 
                    duration_ms=duration_ms)
        log_webapp_action("INDEX_ERROR", {"error": str(e)}, request.remote_addr, "ERROR")
        raise

@app.route('/active')
def active_bets():
    """Redirect to homepage (now shows active bets)"""
    return redirect(url_for('index'))

@app.route('/search')
def search_bet():
    """Search for a specific bet by ID"""
    start_time = datetime.now()
    bet_id = request.args.get('bet_id')
    bet_data = None
    error_msg = None
    
    try:
        if bet_id:
            log_webapp_action("SEARCH_BET_ATTEMPT", 
                            {"bet_id": bet_id, "ip": request.remote_addr}, 
                            request.remote_addr)
            try:
                bet_id_int = int(bet_id)
                bet_data = data_manager.get_bet_by_id(bet_id_int)
                if not bet_data:
                    error_msg = f"Bet #{bet_id} not found"
                    log_webapp_action("SEARCH_BET_NOT_FOUND", 
                                    {"bet_id": bet_id}, 
                                    request.remote_addr, "WARNING")
                else:
                    log_webapp_action("SEARCH_BET_SUCCESS", 
                                    {"bet_id": bet_id, "found": True}, 
                                    request.remote_addr, "SUCCESS")
            except ValueError:
                error_msg = "Invalid bet ID format"
                log_webapp_action("SEARCH_BET_INVALID_FORMAT", 
                                {"bet_id": bet_id}, 
                                request.remote_addr, "ERROR")
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/search", "GET", 
                   user_info=request.remote_addr, 
                   status_code=200, 
                   duration_ms=duration_ms)
        
        return render_template('search_bet.html', 
                             bet_data=bet_data, 
                             error_msg=error_msg, 
                             bet_id=bet_id)
    except Exception as e:
        log_webapp_action("SEARCH_BET_EXCEPTION", 
                        {"error": str(e)[:100]}, 
                        request.remote_addr, "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/search", "GET", 
                   user_info=request.remote_addr, 
                   status_code=500, 
                   duration_ms=duration_ms)
        raise

@app.route('/create-bet')
def create_bet_page():
    """Page for creating new bets"""
    return render_template('create_bet.html')


@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    return jsonify(data_manager.get_bet_statistics())

@app.route('/api/bets')
def api_bets():
    """API endpoint for active bets"""
    return jsonify(data_manager.get_active_bets())

@app.route('/api/broadcast-transaction', methods=['POST'])
def broadcast_transaction():
    """Broadcast a signed transaction using reliable endpoints"""
    start_time = datetime.now()
    tx_hash = None
    
    try:
        data = request.get_json()
        tx_bytes = data.get('tx_bytes')  # Expect protobuf-encoded tx_bytes directly
        signed_tx_data = data.get('signed')  # Legacy support
        
        # Log broadcast attempt
        log_webapp_action("BROADCAST_TX_ATTEMPT", 
                         {"ip": request.remote_addr, "has_tx_bytes": bool(tx_bytes), "has_signed": bool(signed_tx_data)}, 
                         request.remote_addr)
        
        if not tx_bytes and not signed_tx_data:
            log_webapp_action("BROADCAST_TX_VALIDATION_ERROR", 
                            {"error": "Missing transaction data"}, 
                            request.remote_addr, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/broadcast-transaction", "POST", 
                       user_info=request.remote_addr, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return {"success": False, "error": "Missing transaction data. Provide either 'tx_bytes' or 'signed' transaction data."}
        
        # If tx_bytes is provided directly (preferred), use it
        if tx_bytes:
            log_webapp_action("BROADCAST_TX_METHOD", 
                            {"method": "tx_bytes", "length": len(tx_bytes)}, 
                            request.remote_addr)
            print(f"🔄 Broadcasting transaction with tx_bytes (length: {len(tx_bytes)})")
        else:
            # Legacy support - if signed transaction data is provided, expect it to be properly encoded
            log_webapp_action("BROADCAST_TX_METHOD", 
                            {"method": "signed_data"}, 
                            request.remote_addr)
            print(f"🔄 Broadcasting transaction with signed data")
            # For modern CosmJS, the signed transaction should already be properly encoded
            # If it's a string, assume it's base64-encoded protobuf
            if isinstance(signed_tx_data, str):
                tx_bytes = signed_tx_data
            else:
                log_webapp_action("BROADCAST_TX_FORMAT_ERROR", 
                                {"error": "Invalid signed transaction format"}, 
                                request.remote_addr, "ERROR")
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_api_call("/api/broadcast-transaction", "POST", 
                           user_info=request.remote_addr, 
                           status_code=400, 
                           duration_ms=duration_ms)
                return {"success": False, "error": "Invalid transaction format. Expected base64-encoded protobuf transaction."}
        
        # Try multiple reliable REST endpoints
        rest_endpoints = [
            'https://osmosis-api.polkachu.com',
            'https://lcd.osmosis.zone', 
            'https://rest-osmosis.ecostake.com'
        ]
        
        broadcast_result = None
        last_error = None
        
        for endpoint in rest_endpoints:
            try:
                log_webapp_action("BROADCAST_TX_ENDPOINT_ATTEMPT", 
                                {"endpoint": endpoint}, 
                                request.remote_addr)
                print(f"📡 Attempting broadcast via {endpoint}")
                
                broadcast_body = {
                    "tx_bytes": tx_bytes,
                    "mode": "BROADCAST_MODE_SYNC"
                }
                
                response = requests.post(
                    f"{endpoint}/cosmos/tx/v1beta1/txs",
                    json=broadcast_body,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('tx_response'):
                        tx_response = result['tx_response']
                        if tx_response.get('code') == 0:
                            broadcast_result = tx_response
                            tx_hash = broadcast_result.get('txhash')
                            log_webapp_action("BROADCAST_TX_SUCCESS", 
                                            {"endpoint": endpoint, "tx_hash": tx_hash[:16], "height": broadcast_result.get('height', 0)}, 
                                            request.remote_addr, "SUCCESS")
                            print(f"✅ Broadcast successful via {endpoint}: {tx_hash}")
                            break
                        else:
                            error_msg = tx_response.get('raw_log', 'Unknown error')
                            raise Exception(f"Transaction failed: {error_msg}")
                    else:
                        raise Exception(f"Invalid response format: {result}")
                else:
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
                    
            except Exception as e:
                log_webapp_action("BROADCAST_TX_ENDPOINT_FAILED", 
                                {"endpoint": endpoint, "error": str(e)[:100]}, 
                                request.remote_addr, "WARNING")
                print(f"❌ Broadcast failed via {endpoint}: {str(e)}")
                last_error = e
        
        if not broadcast_result:
            log_webapp_action("BROADCAST_TX_ALL_FAILED", 
                            {"error": str(last_error)[:100]}, 
                            request.remote_addr, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/broadcast-transaction", "POST", 
                       user_info=request.remote_addr, 
                       status_code=500, 
                       duration_ms=duration_ms)
            return {"success": False, "error": f"All broadcast endpoints failed: {str(last_error)}"}
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/api/broadcast-transaction", "POST", 
                   user_info=request.remote_addr, 
                   status_code=200, 
                   duration_ms=duration_ms)
        
        return {
            "success": True,
            "transactionHash": broadcast_result.get('txhash'),
            "height": broadcast_result.get('height', 0),
            "gasUsed": broadcast_result.get('gas_used', '0')
        }
        
    except Exception as e:
        log_webapp_action("BROADCAST_TX_EXCEPTION", 
                        {"error": str(e)[:100]}, 
                        request.remote_addr, "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/api/broadcast-transaction", "POST", 
                   user_info=request.remote_addr, 
                   status_code=500, 
                   duration_ms=duration_ms)
        print(f"❌ Broadcast error: {str(e)}")
        return {"success": False, "error": str(e)}

@app.route('/api/place-bet', methods=['POST'])
def api_place_bet():
    """API endpoint for placing webapp bets"""
    start_time = datetime.now()
    wallet_address = None
    bet_id = None
    
    try:
        # Get JSON data from request
        data = request.get_json()
        
        # Log bet placement attempt
        log_webapp_action("PLACE_BET_ATTEMPT", 
                         {"ip": request.remote_addr}, 
                         request.remote_addr)
        
        # Validate required fields
        required_fields = ['bet_id', 'option_index', 'wallet_address', 'amount', 'token']
        for field in required_fields:
            if field not in data:
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_api_call("/api/place-bet", "POST", 
                           user_info=request.remote_addr, 
                           status_code=400, 
                           duration_ms=duration_ms)
                log_webapp_action("PLACE_BET_VALIDATION_ERROR", 
                                {"error": f"Missing field: {field}"}, 
                                request.remote_addr, "ERROR")
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
        
        # Extract data
        bet_id = int(data['bet_id'])
        option_index = int(data['option_index'])
        wallet_address = str(data['wallet_address'])
        amount = float(data['amount'])
        token = str(data['token'])
        tx_hash = data.get('tx_hash')  # Required for real transactions
        block_height = data.get('block_height')  # Optional
        gas_used = data.get('gas_used')  # Optional
        
        # Validate data
        if amount <= 0:
            log_bet_placement(bet_id, wallet_address, option_index, amount, token, status="ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/place-bet", "POST", 
                       user_info=wallet_address[:10], 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": "Amount must be positive"}), 400
        
        if not wallet_address.startswith('osmo'):
            log_bet_placement(bet_id, wallet_address, option_index, amount, token, status="ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/place-bet", "POST", 
                       user_info=wallet_address[:10], 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": "Invalid Osmosis wallet address"}), 400
        
        # Place the bet (all transactions are real)
        result = data_manager.add_webapp_bet(
            bet_id, wallet_address, option_index, amount, token, 
            tx_hash, block_height, gas_used
        )
        
        if result["success"]:
            # Log successful bet placement
            log_bet_placement(bet_id, wallet_address, option_index, amount, token, tx_hash, "SUCCESS")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/place-bet", "POST", 
                       user_info=wallet_address[:10], 
                       status_code=200, 
                       duration_ms=duration_ms)
            return jsonify(result), 200
        else:
            # Log failed bet placement
            log_bet_placement(bet_id, wallet_address, option_index, amount, token, tx_hash, "ERROR")
            log_webapp_action("PLACE_BET_FAILED", 
                            {"error": result.get("error"), "bet_id": bet_id}, 
                            wallet_address[:10], "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/place-bet", "POST", 
                       user_info=wallet_address[:10], 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify(result), 400
            
    except ValueError as e:
        log_webapp_action("PLACE_BET_VALUE_ERROR", 
                        {"error": str(e), "bet_id": bet_id}, 
                        wallet_address[:10] if wallet_address else request.remote_addr, "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/api/place-bet", "POST", 
                   user_info=wallet_address[:10] if wallet_address else request.remote_addr, 
                   status_code=400, 
                   duration_ms=duration_ms)
        return jsonify({"success": False, "error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        log_webapp_action("PLACE_BET_EXCEPTION", 
                        {"error": str(e), "bet_id": bet_id}, 
                        wallet_address[:10] if wallet_address else request.remote_addr, "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/api/place-bet", "POST", 
                   user_info=wallet_address[:10] if wallet_address else request.remote_addr, 
                   status_code=500, 
                   duration_ms=duration_ms)
        print(f"Error in place-bet API: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

@app.route('/api/user-bets/<wallet_address>')
def api_user_bets(wallet_address):
    """API endpoint to get user's existing bets"""
    start_time = datetime.now()
    
    try:
        log_webapp_action("USER_BETS_REQUEST", 
                         {"wallet": f"{wallet_address[:6]}...{wallet_address[-4:]}" if len(wallet_address) > 10 else wallet_address}, 
                         wallet_address[:10])
        
        if not wallet_address.startswith('osmo'):
            log_webapp_action("USER_BETS_VALIDATION_ERROR", 
                            {"error": "Invalid wallet address", "wallet": wallet_address[:10]}, 
                            wallet_address[:10], "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call(f"/api/user-bets/{wallet_address[:10]}", "GET", 
                       user_info=wallet_address[:10], 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"error": "Invalid Osmosis wallet address"}), 400
        
        user_bets = data_manager.get_user_bets(wallet_address)
        
        log_webapp_action("USER_BETS_SUCCESS", 
                        {"bets_count": len(user_bets)}, 
                        wallet_address[:10], "SUCCESS")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call(f"/api/user-bets/{wallet_address[:10]}", "GET", 
                   user_info=wallet_address[:10], 
                   status_code=200, 
                   duration_ms=duration_ms)
        return jsonify(user_bets), 200
        
    except Exception as e:
        log_webapp_action("USER_BETS_EXCEPTION", 
                        {"error": str(e)[:100]}, 
                        wallet_address[:10], "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call(f"/api/user-bets/{wallet_address[:10]}", "GET", 
                   user_info=wallet_address[:10], 
                   status_code=500, 
                   duration_ms=duration_ms)
        print(f"Error in user-bets API: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/create-bet', methods=['POST'])
def api_create_bet():
    """API endpoint for creating new bets"""
    start_time = datetime.now()
    creator_name = None
    
    try:
        # Get JSON data from request
        data = request.get_json()
        
        # Log bet creation attempt
        log_webapp_action("CREATE_BET_ATTEMPT", 
                         {"ip": request.remote_addr}, 
                         request.remote_addr)
        
        # Validate required fields
        required_fields = ['question', 'options', 'bet_amount', 'token']
        for field in required_fields:
            if field not in data:
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_api_call("/api/create-bet", "POST", 
                           user_info=request.remote_addr, 
                           status_code=400, 
                           duration_ms=duration_ms)
                log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                                {"error": f"Missing field: {field}"}, 
                                request.remote_addr, "ERROR")
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
        
        question = str(data['question']).strip()
        options_str = str(data['options']).strip()
        bet_amount = data['bet_amount']
        token = str(data['token']).lower().strip()
        creator_name = data.get('creator_name', 'Anonymous').strip() or 'Anonymous'
        time_limit = str(data.get('time_limit', 'never')).strip()  # Default never (indefinite)
        
        option_list = [opt.strip() for opt in options_str.split(',') if opt.strip()]
        
        if len(option_list) < 2:
            log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                            {"error": "Too few options", "options_count": len(option_list)}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": "You need at least 2 options for a bet! Separate options with commas."}), 400
        
        if len(option_list) > 5:
            log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                            {"error": "Too many options", "options_count": len(option_list)}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": "Maximum 5 options allowed per bet."}), 400
        
        for option in option_list:
            if len(option) > 100:
                log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                                {"error": "Option too long", "option_length": len(option)}, 
                                creator_name, "ERROR")
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_api_call("/api/create-bet", "POST", 
                           user_info=creator_name, 
                           status_code=400, 
                           duration_ms=duration_ms)
                return jsonify({"success": False, "error": "Option text too long! Maximum 100 characters per option."}), 400
        
        if len(question) > 200:
            log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                            {"error": "Question too long", "question_length": len(question)}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": "Question too long! Maximum 200 characters."}), 400
        
        try:
            amount_decimal = float(bet_amount)
            if amount_decimal <= 0:
                log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                                {"error": "Non-positive amount", "amount": amount_decimal}, 
                                creator_name, "ERROR")
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_api_call("/api/create-bet", "POST", 
                           user_info=creator_name, 
                           status_code=400, 
                           duration_ms=duration_ms)
                return jsonify({"success": False, "error": "Bet amount must be positive!"}), 400
            
            min_bet_amount = 0.1  # Minimum bet amount
            if amount_decimal < min_bet_amount:
                log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                                {"error": "Amount too small", "amount": amount_decimal, "min": min_bet_amount}, 
                                creator_name, "ERROR")
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_api_call("/api/create-bet", "POST", 
                           user_info=creator_name, 
                           status_code=400, 
                           duration_ms=duration_ms)
                return jsonify({"success": False, "error": f"Minimum bet amount is {min_bet_amount} {token.upper()}"}), 400
                
        except ValueError:
            log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                            {"error": "Invalid amount format", "amount": bet_amount}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": "Invalid bet amount format!"}), 400
        
        supported_tokens = get_supported_token_list()
        if token not in supported_tokens:
            log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                            {"error": "Unsupported token", "token": token}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": f"Unsupported token! Supported tokens: {', '.join(supported_tokens)}"}), 400
        
        try:
            lock_minutes = parse_time_limit(time_limit)
        except ValueError as e:
            log_webapp_action("CREATE_BET_VALIDATION_ERROR", 
                            {"error": "Invalid time format", "time_limit": time_limit}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=400, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": str(e)}), 400
        
        from datetime import timedelta
        now = datetime.now()
        if lock_minutes == -1:
            lock_time_str = "indefinite"
        else:
            lock_time = now + timedelta(minutes=lock_minutes)
            lock_time_str = lock_time.isoformat()
        
        bet_id = data_manager.generate_bet_id()
        bet = {
            'id': bet_id,
            'question': question,
            'options': option_list,
            'creator': creator_name,
            'creator_type': 'webapp',
            'participants': [],
            'is_active': True,
            'total_pool': 0,
            'bet_amount': amount_decimal,
            'bet_token': token,
            'created_at': now.isoformat(),
            'lock_time': lock_time_str
        }
        
        result = data_manager.save_bet(bet)
        
        if result["success"]:
            # Log successful bet creation
            log_bet_creation(bet, creator_name)
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=200, 
                       duration_ms=duration_ms)
            return jsonify({
                "success": True,
                "message": "Bet created successfully!",
                "bet_id": bet_id,
                "bet": bet
            }), 200
        else:
            # Log failed bet creation
            log_webapp_action("CREATE_BET_SAVE_FAILED", 
                            {"error": result.get("error"), "bet_id": bet_id}, 
                            creator_name, "ERROR")
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            log_api_call("/api/create-bet", "POST", 
                       user_info=creator_name, 
                       status_code=500, 
                       duration_ms=duration_ms)
            return jsonify({"success": False, "error": result.get("error", "Failed to save bet")}), 500
            
    except ValueError as e:
        log_webapp_action("CREATE_BET_VALUE_ERROR", 
                        {"error": str(e)}, 
                        creator_name or request.remote_addr, "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/api/create-bet", "POST", 
                   user_info=creator_name or request.remote_addr, 
                   status_code=400, 
                   duration_ms=duration_ms)
        return jsonify({"success": False, "error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        log_webapp_action("CREATE_BET_EXCEPTION", 
                        {"error": str(e)}, 
                        creator_name or request.remote_addr, "ERROR")
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        log_api_call("/api/create-bet", "POST", 
                   user_info=creator_name or request.remote_addr, 
                   status_code=500, 
                   duration_ms=duration_ms)
        print(f"Error in create-bet API: {e}")
        return jsonify({"success": False, "error": "Internal server error"}), 500


@app.template_filter('format_token')
def format_token_filter(amount, decimals=6):
    """Template filter to format token amounts"""
    if amount == 0:
        return "0"
    
    if isinstance(amount, (int, float)):
        formatted = f"{amount:.{decimals}f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"
    
    return str(amount)

@app.template_filter('format_datetime')
def format_datetime_filter(datetime_str):
    """Template filter to format datetime strings"""
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except:
        return datetime_str

@app.template_filter('format_profit_class')
def format_profit_class(profit):
    """Template filter to get CSS class for profit/loss"""
    if profit > 0:
        return "profit-positive"
    elif profit < 0:
        return "profit-negative"
    else:
        return "profit-neutral"

@app.template_filter('get_username')
def get_username_filter(user_id_or_name):
    """Template filter to convert user ID to username or return name as-is"""
    return data_manager.get_username(user_id_or_name)

if __name__ == '__main__':
    log_webapp_action("STARTUP", {"action": "WEBAPP_STARTING"}, status="INFO")
    
    web_templates_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'templates')
    web_static_dir = os.path.join(os.path.dirname(__file__), '..', 'web', 'static')
    
    if not os.path.exists(web_templates_dir):
        os.makedirs(web_templates_dir)
        log_webapp_action("STARTUP", {"action": "CREATED_TEMPLATES_DIR"}, status="INFO")
    
    if not os.path.exists(web_static_dir):
        os.makedirs(web_static_dir)
        log_webapp_action("STARTUP", {"action": "CREATED_STATIC_DIR"}, status="INFO")
    
    try:
        bets_data = data_manager.load_bets_data()
        active_bets = data_manager.get_active_bets()
        stats = data_manager.get_bet_statistics()
        
        log_webapp_action("STARTUP", {
            "action": "DATA_LOADED",
            "total_bets": len(bets_data.get("bets", {})),
            "active_bets": len(active_bets),
            "bet_counter": bets_data.get("bet_id_counter", 0)
        }, status="SUCCESS")
        
    except Exception as e:
        log_webapp_action("STARTUP", {
            "action": "DATA_LOAD_ERROR",
            "error": str(e)[:100]
        }, status="ERROR")
    
    print("🌐 Starting betting results website...")
    print("📊 Reading data from JSON files only")
    print("🚀 Access at: http://localhost:5003")
    
    log_webapp_action("STARTUP", {
        "action": "SERVER_STARTING",
        "host": "0.0.0.0",
        "port": 5003,
        "debug": True
    }, status="SUCCESS")
    
    app.run(debug=True, host='0.0.0.0', port=5003)