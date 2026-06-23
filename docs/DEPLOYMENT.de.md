# Deployment – RRZE VM chatbot-wiso.de

Schritt-für-Schritt Anleitung zum Deployment auf der RRZE-VM.

## Voraussetzungen

- SSH-Zugang zu chatbot-wiso.de (RRZE VM)
- Docker & Docker Compose installiert
- Git installiert
- GitHub Token im .env oder gh auth konfiguriert

## Schritt 1: VM vorbereiten

```bash
# SSH auf die VM
ssh admin@chatbot-wiso.de

# System updaten
sudo apt update && sudo apt upgrade -y
sudo apt install -y git docker.io docker-compose

# Benutzer zur docker Gruppe hinzufügen
sudo usermod -aG docker admin
newgrp docker

# Verify
docker --version
docker-compose --version
```

## Schritt 2: Repository klonen

```bash
cd /opt
sudo mkdir -p wiesel
sudo chown admin:admin wiesel

git clone https://github.com/TIllAd/wiesel.git
cd wiesel
```

## Schritt 3: Umgebungsvariablen

Erstelle `.env` für Production:

```bash
cat > .env << 'EOF'
# FastAPI
ENVIRONMENT=production
DEBUG=false
BACKEND_PORT=8000
BACKEND_WORKERS=4

# SQLite
DATABASE_PATH=/data/wiesel.db

# Frontend
FRONTEND_PORT=3000
REACT_APP_API_URL=https://chatbot-wiso.de/api

# Optional: OpenAI GPT-4o-mini
OPENAI_API_KEY=sk-...
USE_GPT_FOR_GENERATION=true

# Logging
LOG_LEVEL=INFO
EOF
chmod 600 .env
```

## Schritt 4: Docker Compose (Production)

Verwende die `docker-compose.yml` für Multi-Container:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    environment:
      - ENVIRONMENT=production
      - DATABASE_PATH=/data/wiesel.db
    ports:
      - "8000:8000"
    volumes:
      - ./knowledge_base:/app/knowledge_base:ro
      - /data/wiesel.db:/data/wiesel.db
    restart: always
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1'
          memory: 1G

  frontend:
    build: ./frontend
    environment:
      - REACT_APP_API_URL=https://chatbot-wiso.de/api
    ports:
      - "3000:3000"
    restart: always

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - backend
      - frontend
    restart: always

volumes:
  data:
    driver: local
```

## Schritt 5: Nginx Setup (SSL/TLS)

Erstelle `nginx.conf`:

```nginx
upstream backend {
    least_conn;
    server backend:8000;
}

server {
    listen 80;
    server_name chatbot-wiso.de;
    
    # Redirect zu HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name chatbot-wiso.de;
    
    ssl_certificate /etc/letsencrypt/live/chatbot-wiso.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chatbot-wiso.de/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # API
    location /api {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # WebSocket support (für Live-Updates)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Schritt 6: SSL Certificate (Let's Encrypt)

```bash
# Certbot installieren
sudo apt install -y certbot python3-certbot-nginx

# Zertifikat anfordern
sudo certbot certonly --standalone -d chatbot-wiso.de -d www.chatbot-wiso.de

# Auto-Renewal konfigurieren
sudo systemctl enable certbot.timer
```

## Schritt 7: Starten

```bash
cd /opt/wiesel

# Environment laden
export $(cat .env | xargs)

# Docker Container starten
docker-compose up -d --scale backend=3

# Status prüfen
docker-compose ps
docker-compose logs -f backend
```

## Schritt 8: Monitoring & Logs

```bash
# Alle Container sehen
docker ps

# Backend-Logs
docker-compose logs -f backend

# Frontend-Logs
docker-compose logs -f frontend

# In Echtzeit monitoren (Optional)
docker stats
```

## Updates durchführen

```bash
cd /opt/wiesel

# Neueste Version pullen
git pull origin main

# Neubauen
docker-compose build

# Neue Container starten (mit Blue-Green Deployment)
docker-compose up -d --no-deps --build
```

## Backup

```bash
# Tägliches Backup der SQLite DB
0 2 * * * cp /data/wiesel.db /backup/wiesel-$(date +\%Y\%m\%d).db

# In crontab hinzufügen
crontab -e
```

## Troubleshooting

**Backend startet nicht:**
```bash
docker-compose logs backend
# Prüfe: OPENAI_API_KEY, DATABASE_PATH, Requirements
```

**Keine Verbindung zu API:**
```bash
curl -X GET https://chatbot-wiso.de/api/health
# Sollte {"status": "ok"} zurückgeben
```

**Hohe CPU-Last:**
```bash
docker stats
# Ggf. mehr Backend-Replicas: docker-compose up -d --scale backend=5
```

## Performance-Tuning

Für 500 concurrent users:

```yaml
backend:
  deploy:
    replicas: 3  # Oder mehr bei >400 users
    resources:
      limits:
        cpus: '2'
        memory: 2G

# Datenbank WAL-Mode aktivieren
sqlite3 /data/wiesel.db "PRAGMA journal_mode=WAL;"
```

---

**Fragen?** Kontakt: Till (tilt@fau.de) oder erstelle ein Issue.
