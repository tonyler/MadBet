#!/bin/bash

# Activate virtual environment
source venv/bin/activate

echo "--- Starting all services ---"

# Start the Flask Web App in the background
echo "Starting web_app.py..."
nohup env PYTHONPATH=. python3 -u src/web_app.py > logs/web_app.log 2>&1 &

# Start the Discord Bot in the background
echo "Starting bot.py..."
nohup env PYTHONPATH=. python3 -u src/bot.py > logs/bot.log 2>&1 &

# Start the keeper using the existing script
echo "Starting OsmoJS keeper..."
nohup env PYTHONPATH=. python3 src/keep_osmjs_alive.py > logs/osmjs_keeper.log 2>&1 &

echo "---"
echo "All services are starting in the background."
echo "You can monitor the logs with the following command:"
echo "tail -f logs/web_app.log logs/bot.log logs/osmjs_keeper.log"
