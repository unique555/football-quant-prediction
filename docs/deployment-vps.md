# Ubuntu VPS Deployment

This project can run on a 4H4G Ubuntu 22.04 server with Docker Compose.

## Services

- `nginx`: public reverse proxy on port `80`
- `frontend`: production Next.js app
- `backend`: FastAPI API
- `bot`: Telegram long-polling worker
- `postgres`: application database
- `redis`: Celery broker/result backend
- `worker`: Celery worker, enabled by `--profile full`
- `beat`: Celery scheduler, enabled by `--profile full`
- `mlflow`: experiment tracking, enabled by `--profile full`, with metadata
  and artifacts persisted in the `mlflow_data` Docker volume

## First Deploy

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Clone the repo and create server secrets:

```bash
git clone https://github.com/unique555/football-quant-prediction.git
cd football-quant-prediction
cp .env.example .env
nano .env
```

Required values:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `API_FOOTBALL_KEYS`
- `API_FOOTBALL_HOST=v3.football.api-sports.io`
- `POSTGRES_PASSWORD`
- `SECRET_KEY`

Start the full deployment:

```bash
bash scripts/deploy_vps.sh
```

## Verify

```bash
docker compose --profile full ps
curl http://127.0.0.1/health
docker compose logs --tail=100 backend
docker compose logs --tail=100 bot
```

Open:

- `http://SERVER_IP/`
- `http://SERVER_IP/docs`
- `http://SERVER_IP/health`
- `http://SERVER_IP:5000` for MLflow

## Update

```bash
git pull
bash scripts/deploy_vps.sh
```

## Notes

Secrets must stay in `.env` and must not be committed. If a domain is added later,
point DNS to the server IP and add HTTPS with Certbot or a TLS-enabled reverse
proxy.
