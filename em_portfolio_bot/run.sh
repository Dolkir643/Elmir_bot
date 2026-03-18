#!/usr/bin/with-contenv bashio

export BOT_TOKEN=$(bashio::config 'bot_token')
export TELEGRAM_PROXY=$(bashio::config 'telegram_proxy')
export DATA_PATH="/data"

mkdir -p /data
cd /usr/src/app
python -u tg_bot.py
