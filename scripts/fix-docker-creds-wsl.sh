#!/bin/bash
# Временно отключает credsStore в ~/.docker/config.json, чтобы исправить
# "error getting credentials" при сборке из WSL2 (credential helper desktop.exe недоступен).

set -e
CONFIG="$HOME/.docker/config.json"

if [ ! -f "$CONFIG" ]; then
  echo "Файл $CONFIG не найден."
  exit 1
fi

cp "$CONFIG" "${CONFIG}.bak"
echo '{}' > "$CONFIG"
echo "Готово: credsStore отключён, бэкап: ${CONFIG}.bak"
echo "Содержимое $CONFIG:"
cat "$CONFIG"
