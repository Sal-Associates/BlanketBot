FROM python:3.12-slim

WORKDIR /app

RUN groupadd --system bot && useradd --system --gid bot bot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data && chown bot:bot /data

USER bot

ENV DB_PATH=/data/bot.db

CMD ["python", "bot.py"]

