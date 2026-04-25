# Deployment guide — Ubuntu server

This guide covers setting up a fresh Ubuntu 22.04 (or 24.04) machine to run the Calligraphy Gallery app under systemd with Nginx as a reverse proxy, accessed over HTTPS via Tailscale.

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

## 2. Install and connect Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

After running `tailscale up`, follow the login URL printed in the terminal to authenticate the machine to your Tailnet. Once connected, note the MagicDNS hostname assigned to this machine (e.g. `happysaurlinux.tail1d9bfd.ts.net`) — you'll use it throughout the rest of this guide.

Enable HTTPS in the Tailscale admin console: **DNS → Enable HTTPS Certificates**.

---

## 3. Create a dedicated user

Running the app as a non-root user limits blast radius if anything goes wrong.

```bash
sudo useradd --system --create-home --shell /bin/bash gallery
```

---

## 4. Deploy the application

```bash
sudo -u gallery git clone https://github.com/your-org/calligraphy-gallery.git /home/gallery/app
cd /home/gallery/app
sudo -u gallery python3 -m venv .venv
sudo -u gallery .venv/bin/pip install -r requirements.txt
```

Grant the `gallery` user read access to the archive and the data directory:

```bash
sudo chown -R gallery:gallery /home/gallery/app/data
sudo chown -R gallery:gallery /mnt/data/Calligraphy_Archive
```

---

## 5. Configure environment variables

Create `/home/gallery/app/.env`:

```bash
sudo -u gallery tee /home/gallery/app/.env <<'EOF'
CALLIGRAPHY_ARCHIVE_DIR=/mnt/data/Calligraphy_Archive
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

## 6. Create a systemd service

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

## 7. Provision a TLS certificate via Tailscale

```bash
sudo tailscale cert happysaurlinux.tail1d9bfd.ts.net
```

Tailscale stores the cert and key under `/var/lib/tailscale/certs/`. Allow Nginx to read them:

```bash
sudo chmod 0755 /var/lib/tailscale/certs
sudo chmod 0644 /var/lib/tailscale/certs/happysaurlinux.tail1d9bfd.ts.net.crt
sudo chmod 0640 /var/lib/tailscale/certs/happysaurlinux.tail1d9bfd.ts.net.key
sudo chgrp www-data /var/lib/tailscale/certs/happysaurlinux.tail1d9bfd.ts.net.key
```

The certificate expires every 90 days. Renew it by re-running `tailscale cert` — add a monthly cron job to keep it fresh:

```bash
sudo tee /etc/cron.monthly/tailscale-cert <<'EOF'
#!/bin/sh
tailscale cert happysaurlinux.tail1d9bfd.ts.net
EOF
sudo chmod +x /etc/cron.monthly/tailscale-cert
```

---

## 8. Open the firewall port

Allow port 8963 through UFW:

```bash
sudo ufw allow 8963/tcp
sudo ufw status
```

If your Tailnet has a custom ACL policy, also confirm port 8963 is permitted in the Tailscale admin console under **Access Controls**.

---

## 9. Configure Nginx

Create `/etc/nginx/sites-available/calligraphy-gallery`:

```bash
sudo tee /etc/nginx/sites-available/calligraphy-gallery <<'EOF'
server {
    listen 8963 ssl;
    server_name happysaurlinux.tail1d9bfd.ts.net;

    ssl_certificate     /var/lib/tailscale/certs/happysaurlinux.tail1d9bfd.ts.net.crt;
    ssl_certificate_key /var/lib/tailscale/certs/happysaurlinux.tail1d9bfd.ts.net.key;

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

The gallery is now accessible at `https://happysaurlinux.tail1d9bfd.ts.net:8963` from any device on your Tailnet.

---

## 10. Updating the app

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
| Nginx SSL error | Re-run `tailscale cert` and check file permissions |
| Images not loading | Verify `CALLIGRAPHY_ARCHIVE_DIR` path and `gallery` user read access |
| Database errors | Check `CALLIGRAPHY_DB_PATH` exists and is writable by `gallery` |
| Can't reach the site | Confirm the machine is connected: `tailscale status` |
