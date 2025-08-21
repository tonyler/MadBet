#!/bin/bash
echo "--- Stopping all services ---"

echo "Stopping Web App..."
pkill -f "web_app.py" || echo "Web App was not running."

echo "Stopping Bot..."
pkill -f "bot.py" || echo "Bot was not running."

echo "Stopping OsmoJS Keeper..."
pkill -f "keep_osmjs_alive.py" || echo "Keeper was not running."
pkill -f "npm start" || echo "OsmoJS service was not running."

echo "--- All services stopped ---"
