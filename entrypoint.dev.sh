#!/bin/sh

# Немедленно завершать работу, если какая-либо команда завершается с ошибкой
set -e

# Запускаем сборку и отслеживание CSS в фоновом режиме
# Знак '&' в конце отправляет команду в фон
echo "--> Starting PostCSS watcher in the background..."
npm run css:watch &

# Запускаем Flask-сервер на переднем плане.
# Контейнер будет работать, пока жив этот процесс.
echo "--> Starting Flask development server..."
npm run start:flask