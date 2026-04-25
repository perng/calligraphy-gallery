# Deployment guide — Ubuntu server

This guide covers setting up a fresh Ubuntu 22.04 (or 24.04) machine to run the Calligraphy Gallery app under systemd with Nginx as a reverse proxy.

---

## 1. Install system packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx
```

Verify Python 3.11+:

```bash
python3 --version
```

---

## 2. Create a dedicated user

Running the app as a non-root user limits blast radius if anything goes wrong.

```bash
sudo useradd --system --create-home --shell /bin/bash gallery
```

---

## 3. Deploy the application

```bash
sudo -u gallery git clone https://github.com/your-org/calligraphy-gallery.git /home/gallery/app
cd /home/gallery/app
sudo -u gallery python3 -m venv .venv
sudo -u gallery .venv/bin/pip install -r requirements.txt
```

Copy your archive directory and SQLite database to the server, then set ownership:

```bash
sudo chown -R gallery:gallery /home/gallery/app/data
sudo chown -R gallery:gallery /path/to/archive
```

---

## 4. Configure environment variables

Create `/home/gallery/app/.env`:

```bash
sudo -u gallery tee /home/gallery/app/.env <<'EOF'
CALLIGRAPHY_ARCHIVE_DIR=/path/to/archive
CALLIGRAPHY_DB_PATH=/home/gallery/app/data/calligraphy.sqlite3
CALLIGRAPHY_METADATA_JSON_PATH=/home/gallery/app/calligraphy_title_extracted.json
CALLIGRAPHY_HOST=127.0.0.1
CALLIGRAPHY_PORT=8000
EOF
```

Restrict permissions so only the `gallery` user can read it:

```bash
sudo chmod 600 /home/gallery/app/.env
```

---

## 5. Create a systemd service

Create `/etc/systemd/system/calligraphy-gallery.service`:

```bash
sudo tee /etc/systemd/system/calligraphy-gallery.service <<'EOF'
[Unit]
Description=Calligraphy Gallery
After=network.target

[Service]
User=gallery
WorkingDirectory=/home/gallery/app
EnvironmentFile=/home/gallery/app/.env
ExecStart=/home/gallery/app/.venv/bin/uvicorn app.main:app \
    --host ${CALLIGRAPHY_HOST} \
    --port ${CALLIGRAPHY_PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now calligraphy-gallery
sudo systemctl status calligraphy-gallery
```

Check logs:

```bash
journalctl -u calligraphy-gallery -f
```

---

## 6. Configure Nginx

Create `/etc/nginx/sites-available/calligraphy-gallery`:

```bash
sudo tee /etc/nginx/sites-available/calligraphy-gallery <<'EOF'
server {
    listen 80;
    server_name your-domain-or-ip;

    client_max_body_size 50M;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
EOF
```

Enable the site and reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/calligraphy-gallery /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. (Optional) TLS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com
```

Certbot edits the Nginx config and sets up automatic renewal.

---

## 8. Updating the app

```bash
cd /home/gallery/app
sudo -u gallery git pull
sudo -u gallery .venv/bin/pip install -r requirements.txt
sudo systemctl restart calligraphy-gallery
```

---

## Troubleshooting

| Symptom | Where to look |
|---|---|
| App won't start | `journalctl -u calligraphy-gallery -n 50` |
| Nginx 502 Bad Gateway | App not running — check systemd status |
| Images not loading | Verify `CALLIGRAPHY_ARCHIVE_DIR` path and `gallery` user read access |
| Database errors | Check `CALLIGRAPHY_DB_PATH` exists and is writable by `gallery` |
