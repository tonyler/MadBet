import discord
from discord import app_commands
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict

from src.osmosis_wallet import WalletGenerator, WalletValidator
from config import get_supported_token_list, is_bet_locked, parse_time_limit, BotConfig
from src.osmjs_betting_engine import OsmoJSBettingEngine

load_dotenv()

# Configure logging system
def setup_bot_logging():
    """Setup comprehensive logging for the bot - single file with everything"""
    os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'logs'), exist_ok=True)
    
    logger = logging.getLogger('bot')
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    file_handler = RotatingFileHandler(
        os.path.join(os.path.dirname(__file__), '..', 'logs', 'bot_activity.log'), 
        maxBytes=20*1024*1024,
        backupCount=10
    )
    file_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

bot_logger = setup_bot_logging()
def log_command_usage(user_id: int, username: str, command: str, **kwargs):
    """Log user command usage to commands log"""
    extra_info = " | ".join([f"{k}={v}" for k, v in kwargs.items()]) if kwargs else ""
    message = f"⚡ COMMAND | User: {username} ({user_id}) | Command: /{command} | {extra_info}"
    bot_logger.info(message)

def log_error(context: str, error: str, user_id: int = None, username: str = None):
    """Log errors with context to errors log"""
    user_info = f" | User: {username} ({user_id})" if user_id else ""
    message = f"💥 ERROR | Context: {context} | Error: {str(error)}{user_info}"
    bot_logger.error(message)

def log_transaction(user_id: int, tx_type: str, success: bool, tx_hash: str = None, amount: str = None, token: str = None, duration_ms: float = None, **details):
    """Log OsmoJS transactions and performance to transactions log"""
    emoji = "🟢" if success else "🔴"
    status = "SUCCESS" if success else "FAILED"
    
    tx_details = []
    if tx_hash:
        tx_details.append(f"Hash: {tx_hash[:16]}...")
    if amount and token:
        tx_details.append(f"Amount: {amount} {token.upper()}")
    if duration_ms:
        tx_details.append(f"Duration: {duration_ms:.2f}ms")
    
    for k, v in details.items():
        tx_details.append(f"{k}: {v}")
    
    extra_info = " | ".join(tx_details) if tx_details else ""
    message = f"{emoji} OSMJS | User: {user_id} | Type: {tx_type} | Status: {status} | {extra_info}"
    
    if success:
        bot_logger.info(message)
    else:
        bot_logger.error(message)

def log_bet_action(user_id: int, username: str, action: str, bet_id: int = None, **details):
    """Log betting actions"""
    bet_info = f" | Bet: {bet_id}" if bet_id else ""
    extra_info = " | ".join([f"{k}={v}" for k, v in details.items()]) if details else ""
    message = f"🎯 BET | User: {username} ({user_id}) | Action: {action}{bet_info} | {extra_info}"
    
    bot_logger.info(message)

def log_wallet_action(user_id: int, username: str, action: str, address: str = None, **details):
    """Log wallet actions"""
    addr_info = f" | Address: {address[:10]}..." if address and len(address) > 10 else f" | Address: {address}" if address else ""
    extra_info = " | ".join([f"{k}={v}" for k, v in details.items()]) if details else ""
    message = f"👛 WALLET | User: {username} ({user_id}) | Action: {action}{addr_info} | {extra_info}"
    
    bot_logger.info(message)

def log_performance(operation: str, duration_ms: float, success: bool = True, **details):
    """Log performance metrics"""
    emoji = "⚡" if success else "⏰"
    status = "SUCCESS" if success else "FAILED"
    extra_info = " | ".join([f"{k}={v}" for k, v in details.items()]) if details else ""
    message = f"{emoji} PERF | Operation: {operation} | Duration: {duration_ms:.2f}ms | Status: {status} | {extra_info}"
    
    bot_logger.info(message)

def log_bot_startup():
    """Log bot startup"""
    bot_logger.info("🚀 BOT STARTUP | Discord bot starting up...")

def log_bot_shutdown():
    """Log bot shutdown"""
    bot_logger.info("🛑 BOT SHUTDOWN | Discord bot shutting down...")

def log_command_result(user_id: int, username: str, command: str, success: bool, error_msg: str = None, **details):
    """Log the actual result of a command (success/failure)"""
    emoji = "✅" if success else "❌"
    status = "SUCCESS" if success else "FAILED"
    error_info = f" | Error: {error_msg}" if error_msg else ""
    extra_info = " | ".join([f"{k}={v}" for k, v in details.items()]) if details else ""
    message = f"{emoji} RESULT | User: {username} ({user_id}) | Command: /{command} | Status: {status}{error_info} | {extra_info}"
    
    if success:
        bot_logger.info(message)
    else:
        bot_logger.error(message)

def log_command(func):
    """Decorator to automatically log command usage and performance"""
    import time
    import functools
    
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        start_time = time.time()
        command_name = func.__name__
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        try:
            log_command_usage(user_id, username, command_name, args=str(args)[:100] if args else "", kwargs={k: str(v)[:50] for k, v in kwargs.items()})
            result = await func(interaction, *args, **kwargs)
            duration_ms = (time.time() - start_time) * 1000
            log_performance(f"command_{command_name}", duration_ms, success=True, user_id=user_id)
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_error(f"command_{command_name}", str(e), user_id, username)
            log_performance(f"command_{command_name}", duration_ms, success=False, user_id=user_id)
            log_command_result(user_id, username, command_name, False, str(e))
            raise
    
    return wrapper

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables!")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

BETS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'bets_data.json')
WALLETS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'user_wallets.json')
MAX_BETS = 100
def get_bet_storage_key(bet_id: int) -> str:
    """Get circular buffer storage key for bet ID"""
    storage_slot = bet_id % MAX_BETS
    if storage_slot == 0:
        storage_slot = MAX_BETS
    return str(storage_slot)

def load_bets_data():
    """Load bets from JSON file"""
    try:
        if os.path.exists(BETS_FILE):
            with open(BETS_FILE, 'r') as f:
                data = json.load(f)
                return data.get("bets", {}), data.get("bet_id_counter", 1)
        return {}, 1
    except Exception as e:
        log_error("load_bets_data", str(e))
        return {}, 1

def get_current_bets():
    """Get current bets from JSON file (always fresh data)"""
    current_bets, _ = load_bets_data()
    bot_logger.debug(f"Loaded {len(current_bets)} total bets from JSON")
    return current_bets

def get_bet_by_id(bet_id: int):
    """Get specific bet by ID from JSON file"""
    current_bets = get_current_bets()
    return current_bets.get(str(bet_id))

def get_active_bets():
    """Get all active bets from JSON file"""
    current_bets = get_current_bets()
    all_bet_ids = list(current_bets.keys())
    active_bets = [bet for bet in current_bets.values() if bet.get('is_active', False)]
    active_bet_ids = [bet['id'] for bet in active_bets]
    
    bot_logger.debug(f"All bet IDs: {all_bet_ids} | Active bet IDs: {active_bet_ids}")
    
    return active_bets

def save_bet(bet_data: dict):
    """Save a single bet to JSON file"""
    try:
        current_bets, current_counter = load_bets_data()
        
        # CRITICAL: Use circular buffer storage key to prevent memory overflow
        storage_key = get_bet_storage_key(bet_data['id'])
        current_bets[storage_key] = bet_data
        data = {
            "bets": current_bets,
            "bet_id_counter": current_counter
        }
        with open(BETS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        log_error("save_bet", str(e))
        return False

def update_bet_data(bet_id: int, updates: dict):
    """Update specific fields of a bet in JSON file"""
    try:
        current_bets, current_counter = load_bets_data()
        
        if str(bet_id) not in current_bets:
            return False
        
        storage_key = get_bet_storage_key(bet_id)
        current_bets[storage_key].update(updates)
        data = {
            "bets": current_bets,
            "bet_id_counter": current_counter
        }
        with open(BETS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        log_error("update_bet_data", str(e))
        return False

def get_next_bet_id():
    """Get next bet ID and increment counter"""
    try:
        current_bets, current_counter = load_bets_data()
        new_id = current_counter
        
        data = {
            "bets": current_bets,
            "bet_id_counter": current_counter + 1
        }
        with open(BETS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        return new_id
    except Exception as e:
        log_error("get_next_bet_id", str(e))
        return 1

def load_wallets_data():
    """Load wallets from JSON file"""
    try:
        if os.path.exists(WALLETS_FILE):
            with open(WALLETS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        log_error("load_wallets_data", str(e))
        return {}

def save_wallets_data(wallets):
    """Save wallets to JSON file"""
    try:
        with open(WALLETS_FILE, 'w') as f:
            json.dump(wallets, f, indent=2)
        return True
    except Exception as e:
        log_error("save_wallets_data", str(e))
        return False

def get_user_wallet(user_id: int):
    """Get user wallet from JSON"""
    wallets = load_wallets_data()
    return wallets.get(str(user_id))

def has_wallet(user_id: int) -> bool:
    """Check if user has wallet"""
    return get_user_wallet(user_id) is not None

def add_wallet(user_id: int, address: str, mnemonic: str) -> bool:
    """Add wallet to JSON"""
    wallets = load_wallets_data()
    wallets[str(user_id)] = {
        "address": address,
        "mnemonic": mnemonic,
        "created_at": datetime.now().isoformat()
    }
    return save_wallets_data(wallets)

def remove_wallet(user_id: int) -> bool:
    """Remove wallet from JSON"""
    wallets = load_wallets_data()
    if str(user_id) in wallets:
        del wallets[str(user_id)]
        return save_wallets_data(wallets)
    return True

osmjs_engine = OsmoJSBettingEngine()
async def ensure_osmjs_available():
    """Check if OsmoJS service is available before blockchain operations"""
    if not await osmjs_engine.lazy_health_check():
        return False, "⚠️ OsmoJS service is not available. Please start it with: `cd osmjs-service && npm start`"
    return True, None

async def check_osmjs_service():
    """Verbose check if OsmoJS service is running (for admin commands)"""
    if await osmjs_engine.health_check():
        bot_logger.info("OSMJS | OsmoJS service is running and healthy")
    else:
        bot_logger.warning("OSMJS | OsmoJS service is not available - some features may not work")
        bot_logger.info("OSMJS | Start the service with: cd osmjs-service && npm start")

startup_bets, startup_counter = load_bets_data()
bot_logger.info(f"STARTUP | Loaded {len(startup_bets)} bets and counter from {BETS_FILE}")

startup_wallets = load_wallets_data()
bot_logger.info(f"STARTUP | Loaded {len(startup_wallets)} user wallets from {WALLETS_FILE}")

async def safe_defer(interaction, ephemeral=True):
    """Safely defer interaction response"""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
    except (discord.errors.NotFound, discord.errors.HTTPException):
        pass

async def safe_interaction_response(interaction, embed=None, content=None, ephemeral=True):
    """Safely send interaction response, handling expired/acknowledged interactions"""
    try:
        if interaction.response.is_done():
            if embed:
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.followup.send(content=content, ephemeral=ephemeral)
        else:
            if embed:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content=content, ephemeral=ephemeral)
    except (discord.errors.NotFound, discord.errors.HTTPException):
        pass

def format_token_amount(amount: float, max_decimals: int = 6) -> str:
    """Format token amount to remove unnecessary trailing zeros with overflow protection"""
    try:
        if amount == 0:
            return "0"
        
        if not isinstance(amount, (int, float)) or str(amount).lower() in ['inf', '-inf', 'nan']:
            return "0"
        
        # CRITICAL: Prevent overflow attacks with extreme values
        if abs(amount) > 1e15:
            return "999999999999999" if amount > 0 else "-999999999999999"
        
        if abs(amount) < 1e-10:
            return "0"
        
        formatted = f"{amount:.{max_decimals}f}".rstrip('0').rstrip('.')
        
        if not formatted or formatted == '-' or len(formatted) > 20:
            return "0"
        
        return formatted
        
    except (ValueError, OverflowError, TypeError):
        return "0"

def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions (by role or user ID)"""
    if interaction.user.id in BotConfig.ADMIN_USER_IDS:
        return True
    
    if hasattr(interaction.user, 'roles'):
        user_roles = [role.name for role in interaction.user.roles]
        for admin_role in BotConfig.ADMIN_ROLE_NAMES:
            if admin_role in user_roles:
                return True
    
    return False

async def get_user_real_balance(user_id: int, token_symbol: str = "osmo") -> Optional[Dict]:
    """Get user's token balance from blockchain using OsmoJS"""
    wallet = get_user_wallet(user_id)
    if not wallet:
        return None
    
    try:
        balance_info = await osmjs_engine.get_balance(wallet["address"], token_symbol)
        if balance_info:
            return {
                "amount": balance_info["amount"],
                "formatted": balance_info["formatted"],
                "denom": balance_info["denom"]
            }
        return {"amount": 0, "formatted": f"0 {token_symbol.upper()}"}
            
    except Exception as e:
        log_error("get_user_real_balance", str(e), user_id)
        return None


def create_bet_embed(bet: dict) -> discord.Embed:
    """Create embed for bet display"""
    embed = discord.Embed(
        title=f"📊 Bet #{bet.get('id', 'Unknown')}: {bet.get('question', 'Unknown Bet')}",
        color=0x00ff00 if bet.get('is_active', False) else 0xff0000,
        description="Active Bet" if bet.get('is_active', False) else "Bet Ended",
        timestamp=datetime.fromisoformat(bet['created_at']) if 'created_at' in bet else None
    )
    
    embed.add_field(name="Creator", value=f"<@{bet.get('creator', 'Unknown')}>", inline=True)
    
    if bet.get('is_active', False):
        if is_bet_locked(bet):
            status_text = "🔒 Locked"
            status_color = 0xff9800
            embed.color = status_color
        else:
            status_text = "🟢 Active"
    else:
        status_text = "🔴 Ended"
    
    embed.add_field(name="Status", value=status_text, inline=True)
    
    participants = bet.get('participants', [])
    
    if 'bet_amount' in bet and 'bet_token' in bet:
        embed.add_field(
            name="Bet Amount", 
            value=f"{format_token_amount(bet['bet_amount'])} {bet['bet_token'].upper()}", 
            inline=True
        )
        total_pool = len(participants) * bet['bet_amount']
        total_display = f"{format_token_amount(total_pool)} {bet['bet_token'].upper()}"
    else:
        total_pool = sum(p.get('amount', 0) for p in participants)
        total_display = f"{format_token_amount(total_pool)} tokens"
    
    embed.add_field(name="Total Pool", value=total_display, inline=True)
    
    if 'lock_time' in bet:
        lock_time_str = bet['lock_time']
        
        if lock_time_str.lower() in ['indefinite', 'never', '∞', 'infinite']:
            lock_text = "∞ Never locks (creator controls)"
            embed.add_field(name="Lock Status", value=lock_text, inline=True)
        else:
            try:
                lock_time = datetime.fromisoformat(lock_time_str.replace('Z', '+00:00'))
                if is_bet_locked(bet):
                    lock_text = f"🔒 Locked at {lock_time.strftime('%H:%M UTC')}"
                else:
                    now = datetime.now()
                    time_left = lock_time - now
                    hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                    minutes = remainder // 60
                    if hours > 0:
                        lock_text = f"⏰ Locks in {hours}h {minutes}m"
                    else:
                        lock_text = f"⏰ Locks in {minutes}m"
                embed.add_field(name="Lock Status", value=lock_text, inline=True)
            except (ValueError, AttributeError):
                lock_text = "∞ Never locks (creator controls)"
                embed.add_field(name="Lock Status", value=lock_text, inline=True)
    
    options = bet.get('options', [])
    
    for idx, option in enumerate(options):
        option_bets = [p for p in participants if p.get('option') == idx]
        bet_count = len(option_bets)
        
        if 'bet_amount' in bet and 'bet_token' in bet:
            option_total = bet_count * bet['bet_amount']
            token_display = f"{format_token_amount(option_total)} {bet['bet_token'].upper()}"
        else:
            option_total = sum(p.get('amount', 0) for p in option_bets)
            token_display = f"{format_token_amount(option_total)} tokens"
        
        if bet_count > 0:
            embed.add_field(
                name=f"Option {idx + 1}: {option}",
                value=f"💰 {token_display} • {bet_count} bets",
                inline=True
            )
        else:
            embed.add_field(
                name=f"Option {idx + 1}: {option}",
                value="💰 No bets yet",
                inline=True
            )
    
    return embed

@bot.event
async def on_ready():
    """Bot startup event"""
    bot_logger.info(f'STARTUP | {bot.user} is online!')
    
    current_bets = get_current_bets()
    bot_logger.info(f"STARTUP | Bot loaded with {len(current_bets)} existing bets")
    bot_logger.info("STARTUP | OsmoJS service will be connected on-demand for blockchain operations")
    
    try:
        synced = await tree.sync()
        bot_logger.info(f'STARTUP | Synced {len(synced)} command(s)')
        for cmd in synced:
            bot_logger.debug(f"STARTUP | Command: {cmd.name} - {cmd.description}")
    except Exception as e:
        log_error("on_ready_sync_commands", str(e))


@tree.command(name="create_wallet", description="Create a new Osmosis wallet")
@log_command
async def create_wallet(interaction: discord.Interaction):
    """Create a new Osmosis wallet for the user"""
    try:
        if has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ Wallet Already Exists",
                description="You already have a wallet! Use `/balance` to check it or `/wallet_info` to see details.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        mnemonic, osmosis_address, private_key = WalletGenerator.create_new_wallet()
        
        if not mnemonic or not osmosis_address:
            embed = discord.Embed(
                title="❌ Wallet Creation Failed",
                description="Failed to generate wallet. Please try again.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        if not add_wallet(interaction.user.id, osmosis_address, mnemonic):
            embed = discord.Embed(
                title="❌ Storage Error",
                description="Wallet created but failed to save. Please try again.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎉 Wallet Created Successfully!",
            description="Your new Osmosis wallet has been created.",
            color=0x00ff00
        )
        embed.add_field(name="📍 Address", value=f"`{osmosis_address}`", inline=False)
        embed.add_field(
            name="🔑 Seed Phrase", 
            value=f"||{mnemonic}||", 
            inline=False
        )
        embed.add_field(
            name="⚠️ IMPORTANT SECURITY WARNING",
            value="• Never share your seed phrase with anyone!\n• Anyone with this phrase can steal ALL your funds\n• Store it securely offline (write it down)\n• Use this bot at your own risk",
            inline=False
        )
        embed.add_field(
            name="🔗 Explorer Link",
            value=f"[View on Mintscan](https://www.mintscan.io/osmosis/account/{osmosis_address})",
            inline=False
        )
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        log_wallet_action(interaction.user.id, interaction.user.display_name, "CREATE_WALLET", osmosis_address)
        
    except Exception as e:
        log_error("create_wallet", str(e), interaction.user.id)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while creating your wallet. Please try again.",
            color=0xff0000
        )
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="wallet_info", description="View your wallet information")
@log_command
async def wallet_info(interaction: discord.Interaction):
    """Display user's wallet information"""
    try:
        if not has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ No Wallet Found",
                description="You don't have a wallet yet. Use `/create_wallet` to create one.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        wallet = get_user_wallet(interaction.user.id)
        
        embed = discord.Embed(
            title="💰 Your Wallet Information",
            color=0x0099ff
        )
        embed.add_field(name="📍 Address", value=f"`{wallet['address']}`", inline=False)
        embed.add_field(name="📅 Created", value=wallet.get('created_at', 'Unknown'), inline=True)
        embed.add_field(
            name="🔗 Explorer Link",
            value=f"[View on Mintscan](https://www.mintscan.io/osmosis/account/{wallet['address']})",
            inline=False
        )
        embed.add_field(
            name="💡 Tip",
            value="Use `/balance` to check your token balances",
            inline=False
        )
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        
    except Exception as e:
        log_error("wallet_info", str(e), interaction.user.id)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while getting your wallet information.",
            color=0xff0000
        )
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="export_seed", description="Get your wallet's seed phrase (PRIVATE!)")
@log_command
async def export_seed(interaction: discord.Interaction):
    """Export user's seed phrase - very sensitive operation!"""
    try:
        if not has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ No Wallet Found",
                description="You don't have a wallet yet. Use `/create_wallet` to create one.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        wallet = get_user_wallet(interaction.user.id)
        
        # ⚠️ CRITICAL: Seed phrase export - extremely sensitive operation
        embed = discord.Embed(
            title="🔑 Your Seed Phrase",
            description="⚠️ **EXTREMELY SENSITIVE INFORMATION** ⚠️",
            color=0xff9800
        )
        
        embed.add_field(
            name="📝 24-Word Seed Phrase",
            value=f"||{wallet['mnemonic']}||",
            inline=False
        )
        
        embed.add_field(
            name="🚨 CRITICAL SECURITY WARNING",
            value=(
                "• **NEVER share this with anyone!**\n"
                "• Anyone with this phrase can **steal ALL your funds**\n" 
                "• Write it down on paper and store securely offline\n"
                "• Don't save it in digital files or cloud storage\n"
                "• This phrase recovers your wallet in any Cosmos app"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 How to Use",
            value=(
                "• Import into **Keplr Wallet** for browser use\n"
                "• Import into **Cosmostation** mobile app\n"
                "• Use with any Cosmos-compatible wallet\n"
                "• Your address will always be the same"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📍 Your Address",
            value=f"`{wallet['address']}`",
            inline=False
        )
        
        embed.set_footer(text="🔒 This message is only visible to you")
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        log_wallet_action(interaction.user.id, interaction.user.display_name, "EXPORT_SEED", wallet['address'], warning="SENSITIVE_OPERATION")
        
    except Exception as e:
        log_error("export_seed", str(e), interaction.user.id)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while retrieving your seed phrase.",
            color=0xff0000
        )
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="import_wallet", description="Import an existing wallet using your seed phrase")
@app_commands.describe(seed_phrase="Your 24-word seed phrase (keep this PRIVATE!)")
@log_command
async def import_wallet(interaction: discord.Interaction, seed_phrase: str):
    """Import an existing wallet using seed phrase"""
    try:
        if has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ Wallet Already Exists",
                description="You already have a wallet! Use `/delete_wallet` first if you want to import a different one.",
                color=0xff0000
            )
            embed.add_field(
                name="Current Wallet",
                value=f"Use `/wallet_info` to see your current wallet details.",
                inline=False
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        if not WalletGenerator.validate_mnemonic(seed_phrase.strip()):
            embed = discord.Embed(
                title="❌ Invalid Seed Phrase",
                description="The provided seed phrase is not valid. Please check your 24-word seed phrase and try again.",
                color=0xff0000
            )
            embed.add_field(
                name="💡 Requirements",
                value="• Must be exactly 24 words\n• Words must be from the BIP39 wordlist\n• Check for typos and extra spaces",
                inline=False
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        osmosis_address, private_key = WalletGenerator.mnemonic_to_address_and_key(seed_phrase.strip())
        
        if not osmosis_address or not private_key:
            embed = discord.Embed(
                title="❌ Import Failed",
                description="Failed to derive wallet from seed phrase. Please verify your seed phrase is correct.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        if not add_wallet(interaction.user.id, osmosis_address, seed_phrase.strip()):
            embed = discord.Embed(
                title="❌ Storage Error",
                description="Wallet imported but failed to save. Please try again.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎉 Wallet Imported Successfully!",
            description="Your existing wallet has been imported and is now ready to use.",
            color=0x00ff00
        )
        embed.add_field(name="📍 Address", value=f"`{osmosis_address}`", inline=False)
        embed.add_field(
            name="✅ What's Next",
            value="• Use `/balance` to check your token balances\n• Use `/wallet_info` to view wallet details\n• Start betting with your tokens!",
            inline=False
        )
        embed.add_field(
            name="🔗 Explorer Link",
            value=f"[View on Mintscan](https://www.mintscan.io/osmosis/account/{osmosis_address})",
            inline=False
        )
        embed.add_field(
            name="⚠️ Security Reminder",
            value="Your seed phrase is now stored securely. Never share it with anyone!",
            inline=False
        )
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        log_wallet_action(interaction.user.id, interaction.user.display_name, "IMPORT_WALLET", osmosis_address)
        
    except Exception as e:
        log_error("import_wallet", str(e), interaction.user.id)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while importing your wallet. Please try again.",
            color=0xff0000
        )
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="delete_wallet", description="⚠️ PERMANENTLY delete your wallet (requires confirmation)")
@app_commands.describe(confirmation="Type 'DELETE MY WALLET' to confirm permanent deletion")
@log_command
async def delete_wallet(interaction: discord.Interaction, confirmation: str):
    """Delete user's wallet permanently with verification"""
    try:
        if not has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ No Wallet Found",
                description="You don't have a wallet to delete.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        # Verify confirmation phrase
        if confirmation != "DELETE MY WALLET":
            embed = discord.Embed(
                title="❌ Confirmation Required",
                description="To confirm deletion, you must type exactly: **DELETE MY WALLET**",
                color=0xff0000
            )
            embed.add_field(
                name="⚠️ Warning",
                value="This action is PERMANENT and cannot be undone!",
                inline=False
            )
            embed.add_field(
                name="💡 What happens when deleted:",
                value="• Your wallet address and seed phrase will be removed from the bot\n• You can still access your funds with the seed phrase in other wallets\n• All your betting history will remain but won't be linked to a wallet\n• You can create a new wallet with `/create_wallet`",
                inline=False
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        # Get wallet info before deletion
        wallet = get_user_wallet(interaction.user.id)
        wallet_address = wallet["address"]
        
        # Delete the wallet
        success = remove_wallet(interaction.user.id)
        
        if not success:
            embed = discord.Embed(
                title="❌ Deletion Failed",
                description="Failed to delete wallet from storage. Please try again.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        # Create deletion confirmation embed
        embed = discord.Embed(
            title="🗑️ Wallet Deleted",
            description="Your wallet has been permanently deleted from the bot.",
            color=0xff9800
        )
        
        embed.add_field(
            name="📍 Deleted Address",
            value=f"`{wallet_address}`",
            inline=False
        )
        
        embed.add_field(
            name="🔑 Important Reminder",
            value="If you saved your seed phrase, you can still access your funds using:\n• Keplr Wallet\n• Leap Wallet\n• Any other Cosmos-compatible wallet",
            inline=False
        )
        
        embed.add_field(
            name="🔄 Create New Wallet",
            value="Use `/create_wallet` to create a new wallet with a different seed phrase.",
            inline=False
        )
        
        embed.set_footer(text="This action cannot be undone")
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        log_wallet_action(interaction.user.id, interaction.user.display_name, "DELETE_WALLET", wallet_address, warning="PERMANENT_DELETION")
        
    except Exception as e:
        log_error("delete_wallet", str(e), interaction.user.id)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while deleting your wallet. Please try again.",
            color=0xff0000
        )
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="send", description="Send tokens to another user or address")
@app_commands.describe(
    recipient_user="Discord user to send tokens to",
    recipient_address="Or Osmosis address (osmo...)",
    amount="Amount to send (e.g., 1.5)",
    token="Token symbol (osmo, lab)"
)
@log_command
async def send_tokens(interaction: discord.Interaction, amount: str, token: str = "osmo", recipient_user: discord.User = None, recipient_address: str = None):
    """Send tokens to another user or address"""
    try:
        if not has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ No Wallet Found",
                description="You don't have a wallet yet. Use `/create_wallet` to create one.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "send_tokens", False, "Sender has no wallet")
            return
        

        osmjs_available, error_msg = await ensure_osmjs_available()
        if not osmjs_available:
            embed = discord.Embed(
                title="🔧 Service Unavailable",
                description=error_msg,
                color=0xff9800
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        # Check that exactly one recipient method is provided
        if (recipient_user is None and recipient_address is None) or (recipient_user is not None and recipient_address is not None):
            embed = discord.Embed(
                title="❌ Invalid Recipient",
                description="Please specify either a Discord user OR an Osmosis address, not both or neither.",
                color=0xff0000
            )
            embed.add_field(
                name="💡 Usage:",
                value="• For Discord user: Use the `recipient_user` parameter\n• For address: Use the `recipient_address` parameter",
                inline=False
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        wallet = get_user_wallet(interaction.user.id)
        final_recipient_address = None
        display_user = None
        
        # Handle Discord user
        if recipient_user is not None:
            # Special case: Sending to bot - use escrow address
            if recipient_user.id == 1404947324291252226:  # Bot user ID
                final_recipient_address = BotConfig.BOT_ADDRESS
                display_user = recipient_user
            else:
                # Check if recipient user has a wallet
                if not has_wallet(recipient_user.id):
                    embed = discord.Embed(
                        title="❌ User Has No Wallet",
                        description=f"{recipient_user.mention} doesn't have a wallet yet. They need to use `/create_wallet` first.",
                        color=0xff0000
                    )
                    await safe_interaction_response(interaction, embed=embed, ephemeral=True)
                    log_command_result(interaction.user.id, interaction.user.display_name, "send_tokens", False, "Recipient has no wallet", recipient=recipient_user.display_name)
                    return
                
                recipient_wallet = get_user_wallet(recipient_user.id)
                final_recipient_address = recipient_wallet["address"]
                display_user = recipient_user
        
        # Handle direct address
        else:  # recipient_address is not None
            # Validate recipient address
            if not WalletValidator.is_valid_osmosis_address(recipient_address):
                embed = discord.Embed(
                    title="❌ Invalid Address",
                    description="Please provide a valid Osmosis address (osmo...).",
                    color=0xff0000
                )
                await safe_interaction_response(interaction, embed=embed, ephemeral=True)
                log_command_result(interaction.user.id, interaction.user.display_name, "send_tokens", False, "Invalid recipient address", address=recipient_address)
                return
            
            final_recipient_address = recipient_address
        
        # Validate token
        supported_tokens = get_supported_token_list()
        if token.lower() not in supported_tokens:
            embed = discord.Embed(
                title="❌ Unsupported Token",
                description=f"Supported tokens: {', '.join(supported_tokens)}",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "send_tokens", False, "Unsupported token", token=token)
            return
        
        # Defer response since this might take time - make ephemeral for privacy
        await safe_defer(interaction, ephemeral=True)
        
        # Send the transaction using OsmoJS engine
        result = await osmjs_engine.send_tokens(
            sender_mnemonic=wallet["mnemonic"],
            recipient_address=final_recipient_address,
            amount=amount,
            token=token.lower()
        )
        
        if result.get("success"):
            # Special message for bot transfers
            if recipient_user and recipient_user.id == 1404947324291252226:
                embed = discord.Embed(
                    title="✅ Tokens Sent to Bot Escrow!",
                    description="Your tokens have been sent to the bot's escrow address successfully.",
                    color=0x00ff88
                )
                embed.add_field(name="📤 From", value=f"`{wallet['address']}`", inline=False)
                embed.add_field(name="🏦 To Escrow", value=f"{display_user.mention} (`{final_recipient_address}`)", inline=False)
                embed.add_field(name="ℹ️ Note", value="These tokens are now held in the bot's secure escrow for betting operations.", inline=False)
            else:
                embed = discord.Embed(
                    title="✅ Transaction Successful!",
                    description="Your tokens have been sent successfully.",
                    color=0x00ff00
                )
                embed.add_field(name="📤 From", value=f"`{wallet['address']}`", inline=False)
                
                # Show recipient info differently for Discord users vs addresses
                if display_user:
                    embed.add_field(name="📥 To", value=f"{display_user.mention} (`{final_recipient_address}`)", inline=False)
                else:
                    embed.add_field(name="📥 To", value=f"`{final_recipient_address}`", inline=False)
            
            embed.add_field(name="💰 Amount", value=f"{amount} {token.upper()}", inline=True)
            embed.add_field(name="⛽ Fee", value=result.get("fee_paid", "Unknown"), inline=True)
            embed.add_field(name="⛽ Gas Used", value=str(result.get("gas_used", "Unknown")), inline=True)
            embed.add_field(
                name="🔗 Transaction Hash",
                value=f"[View on Explorer](https://www.mintscan.io/osmosis/txs/{result['tx_hash']})",
                inline=False
            )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_transaction(interaction.user.id, "SEND_TOKENS", True, 
                          tx_hash=result['tx_hash'], amount=amount, token=token.upper(), 
                          recipient=final_recipient_address[:10] + "...", 
                          fee=result.get('fee_paid', 'Unknown'), gas_used=result.get('gas_used', 'Unknown'))
            log_command_result(interaction.user.id, interaction.user.display_name, "send_tokens", True, 
                             amount=amount, token=token.upper(), tx_hash=result['tx_hash'][:16])
            
        else:
            embed = discord.Embed(
                title="❌ Transaction Failed",
                description=f"Transaction failed: {result.get('error', 'Unknown error')}",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_transaction(interaction.user.id, "SEND_TOKENS", False, 
                          error=result.get('error', 'Unknown'), amount=amount, token=token.upper(), 
                          recipient=final_recipient_address[:10] + "...")
            log_command_result(interaction.user.id, interaction.user.display_name, "send_tokens", False, 
                             result.get('error', 'Transaction failed'), amount=amount, token=token.upper())
    
    except Exception as e:
        embed = discord.Embed(
            title="❌ Transaction Error",
            description="An error occurred while processing your transaction. Please try again.",
            color=0xff0000
        )
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)



@tree.command(name="makebet", description="Create a new bet with fixed bet amount")
@app_commands.describe(
    question="The question/topic for the bet",
    options="Betting options separated by commas (e.g., 'Option A, Option B, Option C')",
    bet_amount="Fixed amount each participant must bet (e.g., 1.0)",
    token="Token for betting (osmo, lab)",
    time_limit="How long until betting locks (e.g., 30m, 2h, 1d, 1w, never). Default: never"
)
@log_command
async def makebet(interaction: discord.Interaction, question: str, options: str, bet_amount: str, token: str = "osmo", time_limit: str = "never"):
    """Create a new bet with fixed amount"""
    option_list = [opt.strip() for opt in options.split(',') if opt.strip()]
    
    if len(option_list) < 2:
        await safe_interaction_response(interaction, content="❌ You need at least 2 options for a bet! Separate options with commas.", ephemeral=True)
        return
    
    if len(option_list) > 5:  # Reduced from 10 to 5 for better UX and security
        await safe_interaction_response(interaction, content="❌ Maximum 5 options allowed per bet.", ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Too many options (max 5)", options_count=len(option_list))
        return
    
    # SECURITY: Validate option lengths to prevent memory issues
    for option in option_list:
        if len(option) > 100:
            await safe_interaction_response(interaction, content="❌ Option text too long! Maximum 100 characters per option.", ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Option text too long", option_length=len(option))
            return
    
    if len(question) > 200:
        await safe_interaction_response(interaction, content="❌ Question too long! Maximum 200 characters.", ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Question too long", question_length=len(question))
        return
    try:
        amount_decimal = float(bet_amount)
        if amount_decimal <= 0:
            await safe_interaction_response(interaction, content="❌ Bet amount must be positive!", ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Bet amount must be positive", amount=bet_amount)
            return
        
        if amount_decimal < BotConfig.MIN_BET_AMOUNT:
            await safe_interaction_response(interaction, content=f"❌ Minimum bet amount is {BotConfig.MIN_BET_AMOUNT} {token.upper()}", ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Below minimum bet amount", amount=amount_decimal, min_amount=BotConfig.MIN_BET_AMOUNT)
            return
            
    except ValueError:
        await safe_interaction_response(interaction, content="❌ Invalid bet amount format!", ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Invalid bet amount format", amount=bet_amount)
        return
    
    supported_tokens = get_supported_token_list()
    if token.lower() not in supported_tokens:
        await safe_interaction_response(interaction, content=f"❌ Unsupported token! Supported tokens: {', '.join(supported_tokens)}", ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Unsupported token", token=token)
        return
    try:
        lock_minutes = parse_time_limit(time_limit)
    except ValueError as e:
        await safe_interaction_response(interaction, content=f"❌ Invalid time format: {str(e)}", ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "makebet", False, "Invalid time format", time_limit=time_limit)
        return
    
    from datetime import timedelta
    now = datetime.now()
    if lock_minutes == -1:
        lock_time_str = "indefinite"
    else:
        lock_time = now + timedelta(minutes=lock_minutes)
        lock_time_str = lock_time.isoformat()
    
    bet_id = get_next_bet_id()
    log_bet_action(interaction.user.id, interaction.user.display_name, "CREATE_BET", bet_id, 
                   question=question[:50] + "...", amount=amount_decimal, token=token.upper(), 
                   options_count=len(option_list), time_limit=time_limit, lock_minutes=lock_minutes)
    bet = {
        'id': bet_id,
        'question': question,
        'options': option_list,
        'creator': interaction.user.id,
        'participants': [],
        'is_active': True,
        'total_pool': 0,
        'bet_amount': amount_decimal,
        'bet_token': token.lower(),
        'created_at': now.isoformat(),
        'lock_time': lock_time_str
    }
    
    if not save_bet(bet):
        log_error("makebet_save_bet", f"Failed to save bet {bet_id} to storage", interaction.user.id)
    
    embed = create_bet_embed(bet)
    embed.set_footer(text=f"Use /bet {bet['id']} <option_number> to place your bet!")
    
    await safe_interaction_response(interaction, embed=embed)
    log_command_result(interaction.user.id, interaction.user.display_name, "makebet", True, bet_id=bet_id, amount=amount_decimal, token=token.upper())

@tree.command(name="bet", description="Place a bet on an existing question (amount is fixed by bet creator)")
@app_commands.describe(
    bet_id="The ID of the bet",
    option="Option number to bet on (1, 2, 3, etc.)"
)
@log_command
async def bet(interaction: discord.Interaction, bet_id: int, option: int):
    """Place a bet using fixed amount with blockchain escrow"""
    try:

        osmjs_available, error_msg = await ensure_osmjs_available()
        if not osmjs_available:
            embed = discord.Embed(
                title="🔧 Service Unavailable",
                description=error_msg,
                color=0xff9800
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "OsmoJS service unavailable", bet_id=bet_id)
            return
        
        await safe_defer(interaction, ephemeral=True)
        bet_data = get_bet_by_id(bet_id)
        
        if not bet_data:
            embed = discord.Embed(
                title="❌ Bet Not Found",
                description="Bet not found! Use `/betlist` to see available bets.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet not found", bet_id=bet_id)
            return
    
        if is_bet_locked(bet_data):
            from datetime import datetime
            lock_time_str = bet_data.get('lock_time', 'Unknown')
            try:
                lock_time = datetime.fromisoformat(lock_time_str.replace('Z', '+00:00'))
                formatted_time = lock_time.strftime('%Y-%m-%d %H:%M:%S UTC')
            except:
                formatted_time = lock_time_str
            
            embed = discord.Embed(
                title="🔒 Bet Locked",
                description=f"This bet is no longer accepting new participants.\n\nLocked at: {formatted_time}",
                color=0xff9800
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet locked", bet_id=bet_id)
            return
    
        if not bet_data['is_active']:
            if bet_data.get('cancelled', False):
                embed = discord.Embed(
                    title="❌ Bet Cancelled",
                    description="This bet was cancelled and is no longer accepting new bets.",
                    color=0xff9800
                )
                log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet cancelled", bet_id=bet_id)
            else:
                embed = discord.Embed(
                    title="❌ Bet Ended",
                    description="This bet has already ended!",
                    color=0xff0000
                )
                log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet already ended", bet_id=bet_id)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    
        option_index = option - 1  # Convert to 0-based index
        if option_index < 0 or option_index >= len(bet_data['options']):
            embed = discord.Embed(
                title="❌ Invalid Option",
                description=f"Invalid option! Choose a number between 1 and {len(bet_data['options'])}.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Invalid option number", bet_id=bet_id, option=option)
            return
    
        # CRITICAL: Race condition protection - check if user already bet
        user_already_bet = any(p['user_id'] == interaction.user.id for p in bet_data['participants'])
        bot_logger.debug(f"First check - User {interaction.user.id} already bet: {user_already_bet}")
    
        if user_already_bet:
            embed = discord.Embed(
                title="❌ Already Bet",
                description="You have already placed a bet on this question!",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_bet_action(interaction.user.id, interaction.user.display_name, "ALREADY_BET_FIRST_CHECK", bet_id)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "User already bet on this question", bet_id=bet_id)
            return
    
        # CRITICAL: Re-check after defer to prevent race conditions
        current_bet_data = get_bet_by_id(bet_id)
        if not current_bet_data:
            embed = discord.Embed(
                title="❌ Bet Not Found",
                description="This bet no longer exists!",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet no longer exists (race condition)", bet_id=bet_id)
            return
    
        if not current_bet_data['is_active']:
            if current_bet_data.get('cancelled', False):
                embed = discord.Embed(
                    title="❌ Bet Cancelled", 
                    description="This bet was cancelled and is no longer accepting new bets.",
                    color=0xff9800
                )
                log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet cancelled (race condition)", bet_id=bet_id)
            else:
                embed = discord.Embed(
                    title="❌ Bet Ended",
                    description="This bet has already ended!",
                    color=0xff0000
                )
                log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Bet ended (race condition)", bet_id=bet_id)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
    
        user_already_bet_recheck = any(p['user_id'] == interaction.user.id for p in current_bet_data['participants'])
        bot_logger.debug(f"Second check - User {interaction.user.id} already bet: {user_already_bet_recheck}")
    
        if user_already_bet_recheck:
            embed = discord.Embed(
                title="❌ Bet Already Placed",
                description="You have already placed a bet on this question!",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_bet_action(interaction.user.id, interaction.user.display_name, "ALREADY_BET_SECOND_CHECK", bet_id)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "User already bet (race condition check)", bet_id=bet_id)
            return
    
        amount_str = str(current_bet_data['bet_amount'])
        token = current_bet_data['bet_token']
        
        user_wallet = get_user_wallet(interaction.user.id)
        if not user_wallet:
            embed = discord.Embed(
                title="❌ No Wallet Found",
                description="You don't have a wallet. Use `/create_wallet` first.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "User has no wallet", bet_id=bet_id)
            return
    
        result = await osmjs_engine.place_bet_with_escrow(
            user_id=interaction.user.id,
            username=interaction.user.display_name,
            bet_id=bet_id,
            amount_str=amount_str,
            option_index=option_index,
            token=token,
            wallet=user_wallet
        )
    
        if not result.get("success"):
            error_msg = result.get("error", "Unknown error occurred")
        

            if "Do not know how to serialize a BigInt" in error_msg:
                embed = discord.Embed(
                    title="🔧 Temporary Service Issue",
                    description="The blockchain service is experiencing a temporary technical issue with number formatting. Please try again in a moment.",
                    color=0xff9800
                )
                embed.add_field(
                    name="💡 What to try:",
                    value="• Wait 30 seconds and try again\n• Try a different amount (e.g., 1.0 instead of 1)\n• Contact support if this persists",
                    inline=False
                )
                embed.add_field(
                    name="🔒 Your Funds",
                    value="Your tokens are safe - no transaction was processed",
                    inline=False
                )
            elif "insufficient funds" in error_msg.lower():

                balance_match = re.search(r'spendable balance (\d+)uosmo', error_msg)
                if balance_match:
                    balance_micro = int(balance_match.group(1))
                    balance_display = balance_micro / 1e6
                    balance_formatted = f"{balance_display:.6f}".rstrip('0').rstrip('.')
                else:
                    balance_formatted = "very low"
            
                embed = discord.Embed(
                    title="💰 Insufficient Balance",
                    description=f"You don't have enough {token.upper()} tokens to place this bet.",
                    color=0xff0000
                )
                embed.add_field(
                    name="💳 Current Balance",
                    value=f"~{balance_formatted} {token.upper()}",
                    inline=True
                )
                embed.add_field(
                    name="💸 Needed Amount",
                    value=f"{amount_str} {token.upper()}",
                    inline=True
                )
                embed.add_field(
                    name="💡 What to do:",
                    value=f"• Send more {token.upper()} to your wallet\n• Use `/balance` to check your exact balance\n• Try a smaller bet amount",
                    inline=False
                )
                embed.add_field(
                    name="📍 Your Wallet",
                    value=f"`{user_wallet['address']}`",
                    inline=False
                )
            elif "failed to execute message" in error_msg.lower():
                embed = discord.Embed(
                    title="⚠️ Transaction Failed",
                    description="The blockchain transaction could not be completed. This usually means insufficient balance or network issues.",
                    color=0xff0000
                )
                embed.add_field(
                    name="🔍 Common Causes:",
                    value="• Insufficient token balance\n• Network congestion\n• Gas estimation issues",
                    inline=False
                )
                embed.add_field(
                    name="💡 Try this:",
                    value="• Check your balance with `/balance`\n• Wait a few minutes and try again\n• Try a smaller amount",
                    inline=False
                )
            else:

                embed = discord.Embed(
                    title="❌ Bet Failed",
                    description="Sorry, we couldn't process your bet right now.",
                    color=0xff0000
                )
                embed.add_field(
                    name="🔍 Error Details",
                    value=f"```{error_msg[:500]}{'...' if len(error_msg) > 500 else ''}```",
                    inline=False
                )
                embed.add_field(
                    name="💡 What to try:",
                    value="• Check your wallet balance\n• Try again in a moment\n• Contact support if this persists",
                    inline=False
                )
        
            embed.set_footer(text="🔒 No tokens were transferred - your funds are safe")
            await interaction.followup.send(embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, error_msg[:100], bet_id=bet_id, amount=amount_str, token=token.upper())
            return
    

        bet_record = result["bet_record"]
    

        fresh_bet_data = get_bet_by_id(bet_id)
        if fresh_bet_data:
            # FINAL race condition check - critical security measure
            final_user_check = any(p['user_id'] == interaction.user.id for p in fresh_bet_data['participants'])
            bot_logger.debug(f"FINAL check - User {interaction.user.id} already bet: {final_user_check}")
        
            if final_user_check:
                log_bet_action(interaction.user.id, interaction.user.display_name, "RACE_CONDITION_PREVENTED", bet_id, 
                              tx_hash=result['transaction']['tx_hash'], 
                              severity="CRITICAL")
                embed = discord.Embed(
                    title="❌ Duplicate Bet Prevented",
                    description="You have already placed a bet on this question! Your transaction was successful but the duplicate bet was prevented for security.",
                    color=0xff9800
                )
                embed.add_field(
                    name="🔍 Transaction Hash", 
                    value=f"`{result['transaction']['tx_hash']}`",
                    inline=False
                )
                embed.add_field(
                    name="⚠️ Note",
                    value="Your funds are safe. The blockchain transaction succeeded but we prevented the duplicate entry.",
                    inline=False
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Race condition - duplicate bet prevented", bet_id=bet_id, tx_hash=result['transaction']['tx_hash'][:16])
                return
        
            fresh_bet_data['participants'].append(bet_record)
            fresh_bet_data['total_pool'] += bet_record["amount"]
        
            # Save updated bet data to JSON file - CRITICAL: Must succeed
            if not save_bet(fresh_bet_data):
                log_error("bet_critical_save_failure", f"Failed to save bet participation for bet {bet_id}", 
                         interaction.user.id)
                # This is a critical failure - blockchain succeeded but JSON save failed
                embed = discord.Embed(
                    title="⚠️ Data Save Error",
                    description=f"Your bet was recorded on the blockchain but there was an error saving the data. Please contact support immediately with this transaction hash: `{result['transaction']['tx_hash']}`",
                    color=0xff9800
                )
                embed.add_field(
                    name="🔍 Transaction Hash",
                    value=f"`{result['transaction']['tx_hash']}`",
                    inline=False
                )
                embed.add_field(
                    name="💰 Amount",
                    value=f"{amount_str} {token.upper()}",
                    inline=True
                )
                embed.add_field(
                    name="🎯 Bet ID",
                    value=f"#{bet_id}",
                    inline=True
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                log_command_result(interaction.user.id, interaction.user.display_name, "bet", False, "Data save error after blockchain success", bet_id=bet_id, tx_hash=result['transaction']['tx_hash'][:16])
                return
    

            transaction = result["transaction"]
            embed = discord.Embed(
                title="✅ Bet Placed Successfully!",
                description=f"Your {token.upper()} tokens have been transferred to escrow",
                color=0x00ff00
            )
        

            if fresh_bet_data and fresh_bet_data.get('question'):
                embed.add_field(
                    name="Bet", 
                    value=f"#{bet_id}: {fresh_bet_data['question']}", 
                    inline=False
                )
            else:
                embed.add_field(
                    name="Bet", 
                    value=f"#{bet_id}", 
                    inline=False
                )
        

            if fresh_bet_data and fresh_bet_data.get('options') and option_index < len(fresh_bet_data['options']):
                embed.add_field(
                    name="Your Choice", 
                    value=fresh_bet_data['options'][option_index], 
                    inline=True
                )
            else:
                embed.add_field(
                    name="Your Choice", 
                    value=f"Option {option}", 
                    inline=True
                )
            embed.add_field(
                name="Amount", 
                value=f"{amount_str} {token.upper()}", 
                inline=True
            )
            embed.add_field(
                name="Escrow Address", 
                value=f"`{BotConfig.BOT_ADDRESS}`", 
                inline=False
            )
            embed.add_field(
                name="🔗 Transaction",
                value=f"[View on Explorer](https://www.mintscan.io/osmosis/txs/{transaction['tx_hash']})",
                inline=False
            )
            embed.add_field(
                name="💡 Note",
                value="Your tokens are now held in escrow until the bet concludes. Winners will receive payouts automatically.",
                inline=False
            )
    

            await interaction.followup.send(embed=embed, ephemeral=True)
    

            public_embed = discord.Embed(
                title="🎯 New Bet Entry",
                description=f"{interaction.user.mention} entered the bet!",
                color=0x00aa00
            )
        

            if fresh_bet_data and fresh_bet_data.get('question'):
                public_embed.add_field(
                    name="Bet",
                    value=f"#{bet_id}: {fresh_bet_data['question']}",
                    inline=False
                )
            else:
                public_embed.add_field(
                    name="Bet",
                    value=f"#{bet_id}",
                    inline=False
                )
        

            if fresh_bet_data and fresh_bet_data.get('options') and option_index < len(fresh_bet_data['options']):
                public_embed.add_field(
                    name="Choice",
                    value=f"**{fresh_bet_data['options'][option_index]}**",
                    inline=True
                )
            else:
                public_embed.add_field(
                    name="Choice",
                    value=f"**Option {option}**",
                    inline=True
                )
            public_embed.add_field(
                name="Amount",
                value=f"{amount_str} {token.upper()}",
                inline=True
            )
        
            # Log bet action with defensive null checks (do this BEFORE attempting Discord response)
            option_name = fresh_bet_data['options'][option_index] if (fresh_bet_data and 
                                                                     fresh_bet_data.get('options') and 
                                                                     option_index < len(fresh_bet_data['options'])) else f"Option {option}"
            log_bet_action(interaction.user.id, interaction.user.display_name, "BET_PLACED", bet_id, 
                           amount=amount_str, token=token.upper(), option=option_name, 
                           tx_hash=transaction['tx_hash'])
            log_command_result(interaction.user.id, interaction.user.display_name, "bet", True, bet_id=bet_id, amount=amount_str, token=token.upper(), tx_hash=transaction['tx_hash'][:16])
            
            # Attempt to send public message to the channel (not as followup since main interaction is ephemeral)
            try:
                await interaction.channel.send(embed=public_embed)
            except discord.errors.Forbidden:

                log_error("bet_public_message_forbidden", "Bot lacks permission to send public bet confirmation", interaction.user.id, interaction.user.display_name)
            except Exception as e:

                log_error("bet_public_message_failed", f"Failed to send public bet confirmation: {e}", interaction.user.id, interaction.user.display_name)
        
    except Exception as e:
        log_error("bet_command", f"Unexpected error in bet command: {e}", interaction.user.id, interaction.user.display_name)
        

        embed = discord.Embed(
            title="❌ Unexpected Error",
            description="An unexpected error occurred while processing your bet. Your funds are safe.",
            color=0xff0000
        )
        embed.add_field(
            name="🔒 Your Funds",
            value="No tokens were transferred - your funds are safe",
            inline=False
        )
        embed.add_field(
            name="💡 What to try:",
            value="• Try again in a moment\n• Use `/balance` to verify your funds\n• Contact support if this persists",
            inline=False
        )
        embed.set_footer(text="Error ID: bet_command_exception")
        
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        except:

            log_error("bet_command_error_response_failed", "Could not send error response to user", interaction.user.id, interaction.user.display_name)

@tree.command(name="betlist", description="Show all active bets")
@log_command
async def betlist(interaction: discord.Interaction):
    """Show all active bets"""
    try:

        active_bets = get_active_bets()
        
        if not active_bets:
            embed = discord.Embed(
                title="📝 No Active Bets",
                description="There are no active bets available right now. Use `/makebet` to create one!",
                color=0x999999
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        

        embed = discord.Embed(
            title="📋 Active Bets",
            description=f"Found **{len(active_bets)}** active bets you can participate in:",
            color=0x0099ff
        )
        embed.set_footer(text="Individual bet details below ↓")
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        

        for bet in active_bets:
            participants = bet.get('participants', [])
            participant_count = len(participants)
            

            if 'bet_amount' in bet and 'bet_token' in bet:
                total_pool = participant_count * bet['bet_amount']
                amount_display = f"{format_token_amount(bet['bet_amount'])} {bet['bet_token'].upper()}"
                pool_display = f"{format_token_amount(total_pool)} {bet['bet_token'].upper()}"
            else:
                total_pool = sum(p.get('amount', 0) for p in participants)
                amount_display = "Variable"
                pool_display = f"{format_token_amount(total_pool)} tokens"
            

            creator = bet.get('creator', 'Unknown')
            if isinstance(creator, int):
                creator_display = f"<@{creator}>"
            else:
                creator_display = creator
            

            embed = discord.Embed(
                title=f"Bet #{bet['id']}",
                description=f"**{bet['question']}**",
                color=0x0099ff
            )
            
            embed.add_field(
                name="💰 Entry Amount",
                value=amount_display,
                inline=True
            )
            embed.add_field(
                name="🏆 Total Pool",
                value=pool_display,
                inline=True
            )
            embed.add_field(
                name="👥 Players",
                value=f"{participant_count}",
                inline=True
            )
            embed.add_field(
                name="👤 Created by",
                value=creator_display,
                inline=False
            )
            
            embed.set_footer(text=f"Use /bet {bet['id']} [option] to participate")
            await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        log_error("betlist", str(e), interaction.user.id, interaction.user.display_name)
        await safe_interaction_response(interaction, content=f"❌ Error loading bet list: {str(e)}", ephemeral=True)

@tree.command(name="betinfo", description="Get detailed information about a specific bet")
@app_commands.describe(id="The bet ID")
@log_command
async def betinfo(interaction: discord.Interaction, id: int):
    """Get detailed bet information"""

    bet = get_bet_by_id(id)
    

    log_bet_action(interaction.user.id, interaction.user.display_name, "VIEW_BET_INFO", bet_id=id, found=bet is not None)
    
    if not bet:

        current_bets = get_current_bets()
        available_ids = list(current_bets.keys())
        log_bet_action(interaction.user.id, interaction.user.display_name, "VIEW_BET_INFO_NOT_FOUND", available_bets=available_ids)
        await safe_interaction_response(interaction, content=f"❌ Bet #{id} not found! Available bets: {', '.join(available_ids)}", ephemeral=True)
        return
    
    embed = create_bet_embed(bet)
    

    if bet.get('participants'):
        participant_info = []
        for p in bet['participants']:

            option_index = p.get('option', 0)
            options = bet.get('options', [])
            if option_index < len(options):
                option_name = options[option_index]
            else:
                option_name = f"Option {option_index + 1}"
            

            if 'bet_amount' in bet and 'bet_token' in bet:
                amount_display = f"{format_token_amount(bet['bet_amount'])}"
            else:
                amount_display = f"{format_token_amount(p.get('amount', 0))}"
            

            user_display = f"<@{p['user_id']}>" if 'user_id' in p else p.get('username', 'Unknown User')
            
            participant_info.append(
                f"{user_display}: {amount_display} on {option_name}"
            )
        
        participants_text = '\n'.join(participant_info)
        if len(participants_text) > 1024:
            participants_text = participants_text[:1021] + "..."
        
        embed.add_field(
            name="👥 Participants",
            value=participants_text,
            inline=False
        )
    else:
        embed.add_field(
            name="👥 Participants",
            value="No participants yet",
            inline=False
        )
    
    await safe_interaction_response(interaction, embed=embed)

@tree.command(name="endbet", description="End a bet, calculate payouts, and distribute winnings")
@app_commands.describe(
    bet_id="The ID of the bet to end",
    winning_option="The winning option number"
)
@log_command
async def endbet(interaction: discord.Interaction, bet_id: int, winning_option: int):
    """End a bet with automated blockchain payouts"""
    bet = get_bet_by_id(bet_id)
    
    if not bet:
        await safe_interaction_response(interaction, content="❌ Bet not found!", ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "endbet", False, "Bet not found", bet_id=bet_id)
        return
    

    log_bet_action(interaction.user.id, interaction.user.display_name, "END_BET_ATTEMPT", bet_id=bet_id, creator=bet['creator'], is_admin=is_admin(interaction))
    

    try:
        bet_creator_id = int(bet['creator']) if bet['creator'] else 0
    except (ValueError, TypeError):

        log_error("endbet_invalid_creator", f"Bet {bet_id} has invalid creator ID: {bet['creator']} (probably wallet address)", interaction.user.id, interaction.user.display_name)
        bet_creator_id = 0  # Treat as unknown creator, only admins can end
    
    user_id = int(interaction.user.id)
    user_is_admin = is_admin(interaction)
    

    if bet_creator_id != user_id and not user_is_admin:
        embed = discord.Embed(
            title="❌ Permission Denied",
            color=0xff0000
        )
        
        if bet_creator_id == 0:

            embed.description = "This bet has an invalid creator ID (possibly created with old system). Only authorized admins can end this bet."
            embed.add_field(
                name="Stored Creator", 
                value=f"`{bet['creator']}`", 
                inline=True
            )
            embed.add_field(
                name="Your Status", 
                value="Not an admin", 
                inline=True
            )
        else:

            embed.description = f"Only the bet creator or authorized admins can end this bet!"
            embed.add_field(
                name="Bet Creator", 
                value=f"<@{bet['creator']}>", 
                inline=True
            )
            embed.add_field(
                name="Your ID", 
                value=f"{interaction.user.id}", 
                inline=True
            )
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "endbet", False, "Permission denied - not creator or admin", bet_id=bet_id, creator=bet['creator'])
        return
    
    if not bet['is_active']:
        if bet.get('cancelled', False):
            embed = discord.Embed(
                title="❌ Bet Cancelled",
                description="This bet was cancelled and cannot be ended. It was already cancelled.",
                color=0xff9800
            )
            log_command_result(interaction.user.id, interaction.user.display_name, "endbet", False, "Bet was cancelled", bet_id=bet_id)
        else:
            embed = discord.Embed(
                title="❌ Bet Already Ended",
                description="This bet has already ended!",
                color=0xff0000
            )
            log_command_result(interaction.user.id, interaction.user.display_name, "endbet", False, "Bet already ended", bet_id=bet_id)
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        return
    

    await safe_defer(interaction, ephemeral=False)
    
    winning_index = winning_option - 1  # Convert to 0-based
    if winning_index < 0 or winning_index >= len(bet['options']):
        embed = discord.Embed(
            title="❌ Invalid Option",
            description=f"Invalid winning option! Choose a number between 1 and {len(bet['options'])}.",
            color=0xff0000
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        log_command_result(interaction.user.id, interaction.user.display_name, "endbet", False, "Invalid winning option", bet_id=bet_id, winning_option=winning_option)
        return
    
    # DO NOT mark bet as ended yet - wait until distribution succeeds!
    

    payout_data = await osmjs_engine.calculate_payouts(bet, winning_index)
    
    log_bet_action(interaction.user.id, interaction.user.display_name, "PAYOUT_CALCULATION", bet_id=bet_id, success=payout_data.get('success'), no_participants=payout_data.get('no_participants'))
    
    if not payout_data.get("success"):
        embed = discord.Embed(
            title="❌ Payout Calculation Failed - Bet Still Active!",
            description=f"{payout_data.get('error', 'Unknown error')}\n\n**IMPORTANT:** The bet remains active and can be retried. User funds are safe in escrow.",
            color=0xff0000
        )
        embed.add_field(
            name="🔄 Next Steps", 
            value="• Admin can retry `/endbet` command\n• Check participant data integrity\n• Contact support if issue persists",
            inline=False
        )
        await interaction.followup.send(embed=embed)
        return
    

    if payout_data.get("no_participants"):

        bet['is_active'] = False
        bet['winning_option'] = winning_index
        bet['ended_at'] = datetime.now().isoformat()
        bet['payout_data'] = payout_data
        

        if not save_bet(bet):
            embed = discord.Embed(
                title="❌ Save Failed",
                description="Failed to save bet closure data",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="✅ Bet Closed Successfully",
            description=f"**Bet #{bet_id}** has been closed with no participants.",
            color=0x00ff00
        )
        embed.add_field(
            name="📊 Final Results",
            value=f"• Winning Option: {winning_index + 1}\n• Participants: 0\n• Total Pool: 0 tokens\n• Status: Closed",
            inline=False
        )
        embed.add_field(
            name="💡 Note",
            value="No payouts were needed since no one participated in this bet.",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        log_bet_action(interaction.user.id, interaction.user.display_name, "BET_CLOSED_NO_PARTICIPANTS", bet_id=bet_id)
        return
    
    if payout_data.get("no_winners"):

        bet['is_active'] = False
        bet['winning_option'] = winning_index
        bet['ended_at'] = datetime.now().isoformat()
        

        if user_is_admin and bet_creator_id != user_id:
            bet['ended_by'] = f"Admin: {interaction.user.display_name}"
        else:
            bet['ended_by'] = f"Creator: {interaction.user.display_name}"
        
        embed = discord.Embed(
            title="🔄 Bet Ended - No Winners",
            color=0xffaa00,
            description=f"**{bet['question']}**\n\nWinning option: **{bet['options'][winning_index]}**\nNo one bet on the winning option."
        )
        embed.add_field(
            name="Total Pool", 
            value=f"{format_token_amount(payout_data['total_pool'])} tokens", 
            inline=True
        )
        embed.add_field(
            name="Bot Fee", 
            value=f"{format_token_amount(payout_data['bot_fee'])} tokens (100% - no winners)", 
            inline=True
        )
        

        bet['payout_data'] = payout_data
        if not save_bet(bet):
            log_error("bet_ending_save_failed", f"Failed to save bet {bet_id} ending to storage", interaction.user.id, interaction.user.display_name)
        
        await interaction.followup.send(embed=embed)
        return
    

    distribution_result = await osmjs_engine.distribute_payouts_multisend(payout_data, get_user_wallet)
    
    # CRITICAL: If distribution completely failed, keep bet active!
    if not distribution_result.get("success") and len(distribution_result.get("successful_payouts", [])) == 0:
        embed = discord.Embed(
            title="❌ Payout Distribution Failed - Bet Still Active!", 
            description=f"{distribution_result.get('error', 'Unknown error')}\n\n**IMPORTANT:** The bet remains active and can be retried. User funds are safe in escrow.",
            color=0xff0000
        )
        embed.add_field(
            name="🔄 Next Steps", 
            value="• Admin can retry `/endbet` command\n• Use `/manual_payout` for individual payments\n• Contact support if issue persists",
            inline=False
        )
        await interaction.followup.send(embed=embed)
        return
    

    bet['is_active'] = False
    bet['winning_option'] = winning_index
    bet['ended_at'] = datetime.now().isoformat()
    

    if user_is_admin and bet_creator_id != user_id:
        bet['ended_by'] = f"Admin: {interaction.user.display_name}"
    else:
        bet['ended_by'] = f"Creator: {interaction.user.display_name}"
    

    bet['payout_data'] = payout_data
    bet['distribution_result'] = distribution_result
    if not save_bet(bet):
        log_error("bet_ending_save_failed", f"Failed to save bet {bet_id} ending to storage", interaction.user.id, interaction.user.display_name)
    

    successful_payouts = distribution_result.get("successful_payouts", [])
    failed_payouts = distribution_result.get("failed_payouts", [])
    total_winners = distribution_result.get("total_winners", len(successful_payouts) + len(failed_payouts))
    

    if len(failed_payouts) == 0:
        embed_color = 0x00ff88  # Elegant teal-green
        embed_title = "🏆 Bet Complete - Winners Paid!"
    elif len(successful_payouts) > 0:
        embed_color = 0xff8800  # Vibrant orange
        embed_title = "⚠️ Bet Complete - Partial Payout"
    else:
        embed_color = 0xff4444  # Soft red
        embed_title = "❌ Bet Complete - Payout Issues"
    
    embed = discord.Embed(
        title=embed_title,
        color=embed_color,
        description=f"**{bet['question']}**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    embed.add_field(
        name="🎯 Winning Option", 
        value=f"**{bet['options'][winning_index]}**", 
        inline=True
    )
    embed.add_field(
        name="💎 Total Pool", 
        value=f"**{format_token_amount(payout_data['total_pool'])}** tokens", 
        inline=True
    )
    embed.add_field(
        name="💼 Platform Fee (5%)", 
        value=f"**{format_token_amount(payout_data['bot_fee'])}** tokens", 
        inline=True
    )
    

    if user_is_admin and bet_creator_id != user_id:
        embed.add_field(
            name="Ended By", 
            value="Administrator", 
            inline=True
        )
    

    embed.add_field(
        name="⚡ Transaction Summary",
        value=f"✅ {len(successful_payouts)}/{total_winners} winners paid\n🔗 Single efficient transaction\n💎 Optimized blockchain settlement",
        inline=True
    )
    
    if successful_payouts:
        winner_info = []
        for payout in successful_payouts[:5]:  # Show first 5 to avoid embed limits
            winner_info.append(
                f"<@{payout['user_id']}>: {format_token_amount(payout['amount'])} {payout['token'].upper()}"
            )
        
        embed.add_field(
            name=f"💰 Prize Distribution ({len(successful_payouts)} winners)",
            value='\n'.join(winner_info) + (f"\n... and {len(successful_payouts)-5} more" if len(successful_payouts) > 5 else ""),
            inline=False
        )
        

        tx_hash = distribution_result.get('tx_hash')
        if tx_hash:
            embed.add_field(
                name="🔍 Blockchain Verification",
                value=f"[View Transaction on Explorer](https://www.mintscan.io/osmosis/txs/{tx_hash})",
                inline=False
            )
    
    if failed_payouts:
        failed_info = []
        for failure in failed_payouts[:3]:  # Show first 3 failures
            failed_info.append(f"<@{failure['user_id']}>: {failure.get('error', 'Unknown error')}")
        
        embed.add_field(
            name=f"⚠️ Payment Issues ({len(failed_payouts)})",
            value='\n'.join(failed_info) + (f"\n... and {len(failed_payouts)-3} more" if len(failed_payouts) > 3 else ""),
            inline=False
        )
        
        embed.add_field(
            name="🛠️ Support Available",
            value="• Issues being resolved automatically\n• Contact support if needed\n• Your prizes are guaranteed",
            inline=False
        )
    
    embed.set_footer(text="⚡ Secure blockchain settlement • Instant prize distribution")
    
    await interaction.followup.send(embed=embed)
    log_bet_action(interaction.user.id, interaction.user.display_name, "BET_ENDED_WITH_PAYOUTS", bet_id=bet_id, successful_payouts=len(successful_payouts), failed_payouts=len(failed_payouts))
    log_command_result(interaction.user.id, interaction.user.display_name, "endbet", True, bet_id=bet_id, winning_option=winning_option, successful_payouts=len(successful_payouts), failed_payouts=len(failed_payouts))

@tree.command(name="balance", description="Check your token balances on Osmosis")
@log_command
async def balance(interaction: discord.Interaction):
    """Check user's blockchain balance"""
    try:
        if not has_wallet(interaction.user.id):
            embed = discord.Embed(
                title="❌ No Wallet Found",
                description="You don't have a wallet yet. Use `/create_wallet` to create one.",
                color=0xff0000
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "balance", False, "User has no wallet")
            return
        

        osmjs_available, error_msg = await ensure_osmjs_available()
        if not osmjs_available:
            embed = discord.Embed(
                title="🔧 Service Unavailable",
                description=error_msg,
                color=0xff9800
            )
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            return
        
        wallet = get_user_wallet(interaction.user.id)
        

        await safe_defer(interaction, ephemeral=True)
        

        embed = discord.Embed(
            title="💰 Your Token Balances",
            color=0x0099ff,
            description=f"Address: `{wallet['address']}`"
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        

        supported_tokens = get_supported_token_list()
        balance_text = ""
        has_balances = False
        
        for token in supported_tokens:
            try:
                balance_info = await osmjs_engine.get_balance(wallet["address"], token)
                if balance_info and balance_info["amount"] > 0:
                    balance_text += f"• **{balance_info['formatted']}**\n"
                    has_balances = True
                elif balance_info:
                    balance_text += f"• **0 {token.upper()}**\n"
            except Exception as e:
                log_error("get_balance", f"Error getting {token} balance: {e}", interaction.user.id, interaction.user.display_name)
                balance_text += f"• **Error checking {token.upper()}**\n"
        
        if has_balances or balance_text:
            embed.add_field(
                name="🪙 Token Balances",
                value=balance_text if balance_text else "No balances available",
                inline=False
            )
        else:
            embed.add_field(
                name="📭 Empty Wallet",
                value="Your wallet doesn't have any supported tokens yet.\nSend some OSMO, ION, or ATOM to get started!",
                inline=False
            )
        
        embed.add_field(
            name="🔗 View on Explorer",
            value=f"[Mintscan](https://www.mintscan.io/osmosis/account/{wallet['address']})",
            inline=False
        )
        
        await interaction.followup.send(embed=embed)
        log_command_result(interaction.user.id, interaction.user.display_name, "balance", True, has_balances=has_balances)
    
    except Exception as e:
        log_error("get_balance", f"Error getting balance: {e}", interaction.user.id, interaction.user.display_name)
        log_command_result(interaction.user.id, interaction.user.display_name, "balance", False, str(e)[:100])
        embed = discord.Embed(
            title="❌ Balance Check Failed",
            description="Could not fetch balance from blockchain. Please try again.",
            color=0xff0000
        )
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)



@tree.command(name="bot_balance", description="Check bot's escrow balance")
@log_command
async def bot_balance(interaction: discord.Interaction):
    """Check bot's escrow balance - public command"""
    try:
        await safe_defer(interaction, ephemeral=True)
        
        embed = discord.Embed(
            title="🏦 Bot Escrow Balance",
            color=0x0099ff,
            description=f"Bot Address: `{BotConfig.BOT_ADDRESS}`"
        )
        

        supported_tokens = get_supported_token_list()
        balance_text = ""
        has_balances = False
        
        for token in supported_tokens:
            try:
                balance_info = await osmjs_engine.get_bot_balance(token.lower())
                if balance_info and balance_info["amount"] > 0:
                    balance_text += f"• **{balance_info['formatted']}**\n"
                    has_balances = True
                elif balance_info:
                    balance_text += f"• **0 {token.upper()}**\n"
            except Exception as e:
                log_error("get_bot_balance", f"Error getting {token} balance: {e}", interaction.user.id, interaction.user.display_name)
                balance_text += f"• **Error checking {token.upper()}**\n"
        
        if balance_text:
            embed.add_field(
                name="🪙 Token Balances",
                value=balance_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📭 Empty Escrow",
                value="No tokens found in bot escrow wallet",
                inline=False
            )
        
        embed.add_field(
            name="🔗 View on Explorer",
            value=f"[Mintscan](https://www.mintscan.io/osmosis/account/{BotConfig.BOT_ADDRESS})",
            inline=False
        )
        embed.set_footer(text="This represents funds held in escrow + collected fees")
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        log_error("bot_balance", f"Error checking bot balance: {e}", interaction.user.id, interaction.user.display_name)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while checking bot balance",
            color=0xff0000
        )
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="cancel_bet", description="Cancel an active bet and refund participants (creator or admin only)")
@app_commands.describe(bet_id="The ID of the bet to cancel")
@log_command
async def cancel_bet(interaction: discord.Interaction, bet_id: int):
    """Cancel a bet and refund all participants - creator or admin only"""
    log_bet_action(interaction.user.id, interaction.user.display_name, "CANCEL_BET_ATTEMPT", bet_id=bet_id)
    try:
        bet = get_bet_by_id(bet_id)
        
        if not bet:
            await safe_interaction_response(interaction, content="❌ Bet not found!", ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "cancel_bet", False, "Bet not found", bet_id=bet_id)
            return
        

        log_bet_action(interaction.user.id, interaction.user.display_name, "CANCEL_BET_PERMISSION_CHECK", bet_id=bet_id, creator=bet['creator'], is_admin=is_admin(interaction))
        

        try:
            bet_creator_id = int(bet['creator']) if bet['creator'] else 0
        except (ValueError, TypeError):

            log_error("cancel_bet_invalid_creator", f"Bet {bet_id} has invalid creator ID: {bet['creator']} (probably wallet address)", interaction.user.id, interaction.user.display_name)
            bet_creator_id = 0  # Treat as unknown creator, only admins can cancel
        
        user_id = int(interaction.user.id)
        user_is_admin = is_admin(interaction)
        

        if bet_creator_id != user_id and not user_is_admin:
            embed = discord.Embed(
                title="❌ Permission Denied",
                color=0xff0000
            )
            
            if bet_creator_id == 0:

                embed.description = "This bet has an invalid creator ID (possibly created with old system). Only authorized admins can cancel this bet."
                embed.add_field(
                    name="Stored Creator", 
                    value=f"`{bet['creator']}`", 
                    inline=True
                )
            else:

                embed.description = "You can only cancel bets that you created or if you are an administrator."
                embed.add_field(
                    name="Bet Creator", 
                    value=f"<@{bet_creator_id}>", 
                    inline=True
                )
            
            embed.add_field(
                name="Your User ID", 
                value=f"`{user_id}`", 
                inline=True
            )
            embed.add_field(
                name="Admin Status", 
                value="✅ Yes" if user_is_admin else "❌ No", 
                inline=True
            )
            
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)
            log_command_result(interaction.user.id, interaction.user.display_name, "cancel_bet", False, "Permission denied - not creator or admin", bet_id=bet_id)
            return
        

        log_bet_action(interaction.user.id, interaction.user.display_name, "CANCEL_BET_STATUS_CHECK", bet_id=bet_id, is_active=bet.get('is_active'), cancelled=bet.get('cancelled', False))
        
        if not bet['is_active']:

            if bet.get('cancelled', False):
                embed = discord.Embed(
                    title="❌ Bet Already Cancelled",
                    description=f"**{bet['question']}**\n\nThis bet was already cancelled.",
                    color=0xff9800
                )
                embed.add_field(
                    name="Cancelled At",
                    value=bet.get('cancelled_at', 'Unknown'),
                    inline=True
                )
                embed.add_field(
                    name="Cancelled By", 
                    value=bet.get('cancelled_by', 'Unknown'),
                    inline=True
                )
                await safe_interaction_response(interaction, embed=embed, ephemeral=True)
                log_command_result(interaction.user.id, interaction.user.display_name, "cancel_bet", False, "Bet already cancelled", bet_id=bet_id)
            else:
                embed = discord.Embed(
                    title="❌ Bet Already Ended",
                    description=f"**{bet['question']}**\n\nThis bet has already ended and cannot be cancelled.",
                    color=0xff0000
                )
                if bet.get('ended_at'):
                    embed.add_field(name="Ended At", value=bet['ended_at'], inline=True)
                if bet.get('winning_option') is not None:
                    options = bet.get('options', [])
                    if bet['winning_option'] < len(options):
                        embed.add_field(name="Winner", value=options[bet['winning_option']], inline=True)
                await safe_interaction_response(interaction, embed=embed, ephemeral=True)
                log_command_result(interaction.user.id, interaction.user.display_name, "cancel_bet", False, "Bet already ended", bet_id=bet_id)
            return
        
        participants = bet.get('participants', [])
        log_bet_action(interaction.user.id, interaction.user.display_name, "CANCEL_BET_PARTICIPANTS_FOUND", bet_id=bet_id, participant_count=len(participants))
        
        if not participants:

            log_bet_action(interaction.user.id, interaction.user.display_name, "CANCEL_BET_NO_PARTICIPANTS", bet_id=bet_id)
            bet['is_active'] = False
            bet['cancelled'] = True
            bet['cancelled_at'] = datetime.now().isoformat()

            if user_is_admin and bet_creator_id != user_id:
                bet['cancelled_by'] = f"Admin: {interaction.user.display_name}"
            else:
                bet['cancelled_by'] = f"Creator: {interaction.user.display_name}"
            
            if not save_bet(bet):
                log_error("bet_cancellation_save_failed", f"Failed to save bet {bet_id} cancellation", interaction.user.id, interaction.user.display_name)
            else:
                log_bet_action(interaction.user.id, interaction.user.display_name, "BET_CANCELLATION_SAVED", bet_id=bet_id)
            
            embed = discord.Embed(
                title="🚫 Bet Cancelled Successfully",
                description=f"**{bet['question']}**\n\n✅ Bet has been cancelled by administrator.\n\n**No participants needed refunding.**",
                color=0x00ff00  # Green color for success
            )
            embed.add_field(
                name="📊 Final Status",
                value="• Participants: 0\n• Refunds needed: None\n• Action: Cancelled",
                inline=False
            )
            embed.add_field(
                name="⏰ Cancelled At",
                value=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
                inline=True
            )
            embed.add_field(
                name="👤 Cancelled By",
                value="Administrator",
                inline=True
            )
            await safe_interaction_response(interaction, embed=embed)
            log_bet_action(interaction.user.id, interaction.user.display_name, "CANCEL_BET_MESSAGE_SENT", bet_id=bet_id)
            return
        
        await safe_defer(interaction, ephemeral=False)
        
        log_transaction(interaction.user.id, "MULTISEND_REFUND_START", True, participant_count=len(participants))
        

        distribution_result = await osmjs_engine.distribute_refunds_multisend(bet, get_user_wallet)
        
        successful_refunds = distribution_result.get("successful_refunds", [])
        failed_refunds = distribution_result.get("failed_refunds", [])
        
        log_transaction(interaction.user.id, "MULTISEND_REFUND_COMPLETE", True, successful_refunds=len(successful_refunds), failed_refunds=len(failed_refunds))
        
        # CRITICAL: Only mark bet as cancelled if refunds were at least partially successful
        if not distribution_result.get("success") and len(successful_refunds) == 0:
            embed = discord.Embed(
                title="❌ Refund Distribution Failed - Bet Still Active!", 
                description=f"{distribution_result.get('error', 'Unknown error')}\n\n**IMPORTANT:** The bet remains active and can be retried. User funds are safe in escrow.",
                color=0xff0000
            )
            embed.add_field(
                name="🔄 Next Steps", 
                value="• Admin can retry `/cancel_bet` command\n• Use `/manual_payout` for individual refunds\n• Contact support if issue persists",
                inline=False
            )
            await interaction.followup.send(embed=embed)
            return
        

        bet['is_active'] = False
        bet['cancelled'] = True
        bet['cancelled_at'] = datetime.now().isoformat()
        bet['cancelled_by'] = f"Admin: {interaction.user.display_name}"
        bet['refund_results'] = {
            "successful_refunds": successful_refunds,
            "failed_refunds": failed_refunds
        }
        
        if not save_bet(bet):
            log_error("bet_cancellation_save_failed_final", f"Failed to save bet {bet_id} cancellation", interaction.user.id, interaction.user.display_name)
        
        embed = discord.Embed(
            title="✅ Bet Cancelled Successfully - Refunds Processed",
            color=0x00ff00,  # Green color for success
            description=f"**{bet['question']}**\n\n🔄 All participants have been refunded their tokens."
        )
        embed.add_field(
            name="Successful Refunds",
            value=f"{len(successful_refunds)} participants",
            inline=True
        )
        embed.add_field(
            name="Failed Refunds", 
            value=f"{len(failed_refunds)} participants",
            inline=True
        )
        
        if successful_refunds:
            refund_info = []
            for refund in successful_refunds[:5]:  # Show first 5
                refund_info.append(
                    f"<@{refund['user_id']}>: {format_token_amount(refund['amount'])} {refund['token'].upper()}"
                )
            
            embed.add_field(
                name="🔄 Refunds Processed",
                value='\n'.join(refund_info) + (f"\n... and {len(successful_refunds)-5} more" if len(successful_refunds) > 5 else ""),
                inline=False
            )
        

        if user_is_admin and bet_creator_id != user_id:
            embed.set_footer(text="Cancelled by Administrator")
        else:
            embed.set_footer(text="Cancelled by Creator")
        
        await interaction.followup.send(embed=embed)

        if user_is_admin and bet_creator_id != user_id:
            log_bet_action(interaction.user.id, interaction.user.display_name, "ADMIN_CANCELLED_BET", bet_id=bet_id, successful_refunds=len(successful_refunds))
        else:
            log_bet_action(interaction.user.id, interaction.user.display_name, "CREATOR_CANCELLED_BET", bet_id=bet_id, successful_refunds=len(successful_refunds))
        log_command_result(interaction.user.id, interaction.user.display_name, "cancel_bet", True, bet_id=bet_id, participants=len(participants), successful_refunds=len(successful_refunds))
        
    except Exception as e:
        log_error("cancel_bet", f"Error cancelling bet: {e}", interaction.user.id, interaction.user.display_name)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while cancelling the bet",
            color=0xff0000
        )
        
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await safe_interaction_response(interaction, embed=embed, ephemeral=True)

@tree.command(name="who_can_override", description="Show who has admin permissions to override bet creators")
@log_command
async def who_can_override(interaction: discord.Interaction):
    """Display information about admin permissions"""
    try:
        embed = discord.Embed(
            title="🛡️ Admin Override Permissions",
            description="Users with these permissions can override bet creators using admin commands",
            color=0x9C27B0
        )
        

        if BotConfig.ADMIN_USER_IDS:
            embed.add_field(
                name="👤 Authorized Admin Users",
                value=f"{len(BotConfig.ADMIN_USER_IDS)} user(s) authorized to override bet creators",
                inline=False
            )
        else:
            embed.add_field(
                name="👤 Authorized Admin Users", 
                value="No admin users configured",
                inline=False
            )
        

        user_is_admin = is_admin(interaction)
        admin_status = "✅ You have admin permissions" if user_is_admin else "❌ You do not have admin permissions"
        embed.add_field(
            name="🔍 Your Status",
            value=admin_status,
            inline=False
        )
        

        embed.add_field(
            name="⚡ Admin Override Commands",
            value=(
                "• `/endbet` - End any bet and declare winner (admins can override creators)\n"
                "• `/cancel_bet` - Cancel any bet and refund participants\n"
                "• `/bot_balance` - Check bot's escrow wallet balances for all supported tokens"
            ),
            inline=False
        )
        

        if hasattr(interaction, 'guild') and interaction.guild:
            try:

                current_admins = []
                for member in interaction.guild.members:
                    if member.id in BotConfig.ADMIN_USER_IDS:
                        current_admins.append(f"• {member.display_name}")
                
                if current_admins:
                    admin_list = "\n".join(current_admins)
                    embed.add_field(
                        name=f"🌟 Current Server Admins ({len(current_admins)})",
                        value=admin_list,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🌟 Current Server Admins",
                        value="No authorized admin users found in this server",
                        inline=False
                    )
                    
            except Exception as e:
                log_error("get_server_members", f"Error getting server members: {e}", interaction.user.id, interaction.user.display_name)
                embed.add_field(
                    name="🌟 Current Server Admins",
                    value="Unable to check server members (missing permissions)",
                    inline=False
                )
        
        embed.add_field(
            name="💡 How to Get Admin Rights",
            value=(
                "**Bot owner can:**\n"
                "• Add your user ID to the bot configuration\n\n"
                "**Bet creators can always:**\n"
                "• End their own bets with `/endbet`\n"
                "• Admins can also use `/endbet` to end any bet"
            ),
            inline=False
        )
        
        embed.set_footer(text="Admin permissions allow overriding any bet creator's decisions")
        
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)
        
    except Exception as e:
        log_error("who_can_override", f"Error in who_can_override: {e}", interaction.user.id, interaction.user.display_name)
        embed = discord.Embed(
            title="❌ Error",
            description="An error occurred while checking admin permissions",
            color=0xff0000
        )
        await safe_interaction_response(interaction, embed=embed, ephemeral=True)




if __name__ == "__main__":
    try:
        log_bot_startup()
        bot.run(TOKEN)
    except KeyboardInterrupt:
        log_bot_shutdown()
        print("Bot shutdown by user")
    except Exception as e:
        log_error("bot_main", f"Bot crashed: {e}")
        raise
    finally:
        log_bot_shutdown()
