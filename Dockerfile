# Dockerfile

# Используем официальный образ Python 3.11 в slim-версии для уменьшения размера
FROM python:3.11-slim

# Устанавливаем переменные окружения, чтобы Python работал в "дружелюбном" для Docker режиме
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 1. Устанавливаем системные зависимости, ВКЛЮЧАЯ Node.js.
# Это нужно, чтобы в контейнере были команды 'npm' и 'node' для сборки фронтенда.
# Объединяем команды в один RUN, чтобы уменьшить количество слоев в образе.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    netcat-openbsd && \
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs && \
    # Очищаем кэш apt, чтобы итоговый образ был меньше
    rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 2. Копируем файлы зависимостей Python и Node.js
# Этот шаг кэшируется Docker'ом. Он будет выполнен заново только если
# изменятся requirements.txt или package.json.
COPY requirements.txt package.json package-lock.json ./

# 3. Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# 4. Устанавливаем зависимости Node.js
RUN npm install

# 5. Копируем ВСЕ остальные файлы проекта в рабочую директорию
COPY . .

# 6. Собираем CSS для production-окружения
# Этот шаг использует зависимости из установленной ранее папки node_modules
RUN npm run css:build

# --- ИЗМЕНЕНИЕ: Заменяем CMD на ENTRYPOINT ---
# ENTRYPOINT указывает на исполняемый файл/скрипт, который будет запущен при старте контейнера.
# Это делает контейнер похожим на исполняемый файл.
# Наш скрипт entrypoint.sh ждет готовности БД, применяет миграции и затем запускает основной процесс.
ENTRYPOINT ["/app/entrypoint.sh"]

# CMD указывает команду и/или аргументы по умолчанию для ENTRYPOINT.
# Это позволяет легко переопределить команду при запуске контейнера (docker run ... <другая_команда>).
# Здесь мы оставляем запуск Gunicorn как команду по умолчанию.
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "wsgi:app"]