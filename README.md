# 🧪 MadBet - Osmosis Betting Platform

A Discord betting bot with web interface and transactions on the Osmosis blockchain. Create, manage, and participate in decentralized betting pools with OSMO and LAB tokens.
<img width="1200" height="630" alt="image" src="https://github.com/user-attachments/assets/6e602ddf-931b-4311-95e6-cd9672b0dc57" />

**🌐 WebApp:** [madbet.xyz](https://madbet.xyz)

## ⚙️ Setup

### 1. Clone & Configure
```bash
git clone https://github.com/tonyler/MadBet.git
cd madv2

# Copy and configure settings
cp config_template.py config.py
# Edit config.py with your bot token, wallet details, etc.
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Application
```bash
# Start everything (bot, web app, services)
./run_all.sh

# Stop everything
./stop_all.sh
```

## 📁 Project Structure
```
madv2/
├── README.md                 # This file
├── requirements.txt          # Python dependencies  
├── config.py                 # Main configuration
├── run_all.sh               # Start all services
├── stop_all.sh              # Stop all services
│
├── data/                    # Data storage
│   ├── bets_data.json       # Betting data (circular buffer, max 100)
│   └── user_wallets.json    # User wallet data
│
├── logs/                    # All log files
│   ├── bot_activity.log     # Bot operations
│   ├── webapp.logs          # Web app activity
│   └── osmjs_keeper.log     # Service keeper logs
│
├── src/                     # Source code
│   ├── bot.py               # Discord bot
│   ├── web_app.py           # Flask web interface
│   ├── keep_osmjs_alive.py  # Service keeper
│   ├── osmjs_betting_engine.py # Betting logic
│   └── osmosis_wallet.py    # Wallet utilities
│
├── services/                # External services
│   └── osmjs-service/       # OsmoJS multisend service
│       ├── package.json
│       └── simple_service.js
│
├── web/                     # Web assets
│   ├── templates/           # HTML templates
│   │   ├── index.html       # Home page
│   │   ├── active_bets.html # Active bets
│   │   └── ...
│   └── static/              # CSS, JS, images
│       ├── css/style.css
│       ├── js/
│       ├── osmo-logo.png
│       └── lab-logo.png
│
└── tests/                   # Test files
    └── test_circular_buffer.py
```

## 🎮 Features

### 🤖 Discord Bot
- `/makebet` - Create new bets (OSMO/LAB tokens)
- `/bet` - Join existing bets
- `/balance` - Check token balances
- `/betlist` - View active bets
- `endbet` - Automatically distribute rewards to winner (by Admins and bet's creator) 
- `/cancel_bet` - Cancel a bet and return all players (by Admins or bet's creator)

### 🌐 Web Interface
- Active bets display with real-time data
- Bet creation interface
- Past results and statistics
- Mobile-responsive design

## 🛡️ Reliability
The system ensures **maximum uptime**:
- Service keeper monitors OsmoJS every 10 seconds
- Automatic restart on crashes or unresponsiveness  
- Circular buffer prevents data bloat
- Clean error handling and logging

## 💰 Supported Tokens
- **OSMO**: Native Osmosis token
- **LAB**: Factory token (factory/osmo17fel472lgzs87ekt9dvk0zqyh5gl80sqp4sk4n/LAB)

*Note: OSMO is always used for gas fees*

## 🔄 Operation
1. **Start**: `./run_all.sh`
2. **Monitor**: `tail -f logs/web_app.log logs/bot.log logs/osmjs_keeper.log`
3. **Stop**: `./stop_all.sh`

## 🚀 Coming Soon
- Keplr and Leap wallet integrations on webapp (Discord is not needed anymore for betting)
- Recreating whole app in CosmWasm (decentralizing it)
- Ability to bet dynamic amounts of money (currently a fixed entry can be bet)
- Increased security in saving discord wallet-created seed prhrases
