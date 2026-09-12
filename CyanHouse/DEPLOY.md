# Ubuntu server setup

Checklist for standing up CyanHouse on a fresh Ubuntu machine (e.g. `cyanserver`).

## 1. Install python3 / pip

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

## 2. Install tmux

```bash
sudo apt install -y tmux
```

## 3. Install a .venv

Shared across the `sharedCode` monorepo, one level above `CyanHouse` (matches
`source ../.venv/bin/activate`):

```bash
cd ~/Documents/sharedCode
python3 -m venv .venv
source .venv/bin/activate
```

## 4. Install requirements.txt

From inside `CyanHouse`, venv still active:

```bash
cd ~/Documents/sharedCode/CyanHouse
pip install -r requirements.txt
```

## 5. Install npm

Ubuntu's `apt` version tends to be old — NodeSource gives a current one. Skip
straight to `sudo apt install -y nodejs npm` instead if you don't care about
the version.

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
cd ~/Documents/sharedCode/CyanHouse/react_ui
npm install
npm run build
```

## 6. Add user to docker's group

```bash
sudo usermod -aG docker $USER
```

Then **log out and back in** — a new terminal in the same session isn't
enough, group membership only refreshes on a fresh login.

## 7. Make sure ports 80 and 443 are open on the server

Router admin panel → port-forwarding rules for external `80` and `443`, both
targeting this machine's LAN IP (`hostname -I` to confirm it). Verify
externally with `canyouseeme.org` (or similar) — testing from inside the same
network can give a false positive via NAT hairpinning.

## 8. Check the `.env` file (top level)

Gitignored — doesn't come with `git pull`. Create it from `.env.example`:

```bash
cd ~/Documents/sharedCode/CyanHouse
cp .env.example .env
nano .env
```

Fill in for *this* machine specifically: `PUBLIC_HOST`, `ARDUINO_DEVICE`
(e.g. `/dev/ttyUSB0`, or blank if no Arduino attached yet), `CONTROLS_FN_HOST`,
`DATA_DIR` (blank unless you want data elsewhere), `SERPER_API_KEY`.

## 9. Check `users.json` in `/api`

Also gitignored. Without it, the app falls back to `dev`/`dev` credentials
(logs a warning) — not something you want exposed once this is live behind
nginx. Create real credentials:

```bash
cd ~/Documents/sharedCode/CyanHouse/api
python3 -c "import secrets; print(secrets.token_hex(16))"   # generate a token
nano users.json
```

Same shape either way — one entry per user, `token` plus a `permissions` dict
(not enforced anywhere yet, just carried through for later):

```json
{ "claudio": { "token": "the-token-you-just-generated", "permissions": {} } }
```

## 10. Backend as a service

```bash
sudo nano /etc/systemd/system/cyanhouse-api.service
```

```ini
[Unit]
Description=CyanHouse API (FastAPI backend) in tmux
After=network.target

[Service]
Type=forking
User=claudio
WorkingDirectory=/home/claudio/Documents/sharedCode/CyanHouse
ExecStart=/usr/bin/tmux new -s cyanhouse-api -d '/home/claudio/Documents/sharedCode/.venv/bin/python -m api'
ExecStop=/usr/bin/tmux kill-session -t cyanhouse-api
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable cyanhouse-api.service
sudo systemctl start cyanhouse-api.service
```

Check it: `sudo systemctl status cyanhouse-api.service`, or attach to the live
process with `tmux attach -t cyanhouse-api` (detach again with `Ctrl+b d`
without killing it).

## 11. nginx + HTTPS (Docker)

Same reverse-proxy setup as the Windows `nginx/` folder (`/ui`, `/api`,
`/cyan_pc`), containerized instead of installing an nginx binary on the box.
Runs with `network_mode: host`, so it reaches the FastAPI backend
(`python -m api`, port 8000) on this same machine at `127.0.0.1:8000`
unchanged, and binds 80/443 directly on the host.

Prerequisites: Docker + Docker Compose installed, DNS
(`cyanroomserver.duckdns.org`) pointing at this machine's public IP, and ports
80/443 forwarded to it (step 7, above).

### First-time cert issuance (one-time, chicken-and-egg problem)

`docker/nginx.conf`'s port-443 server block references a certificate that
doesn't exist yet — nginx refuses to even start with a `ssl_certificate`
pointing at a missing file, which would also take down the port-80 block
needed to serve the ACME challenge. So the very first certificate has to be
obtained with a throwaway HTTP-only nginx first:

```bash
# 1. Bootstrap nginx: HTTP only, just enough to answer the ACME challenge.
docker run --rm -d --name nginx-bootstrap --network host \
  -v "$(pwd)/docker/nginx-bootstrap.conf:/etc/nginx/nginx.conf:ro" \
  -v "$(pwd)/docker/certbot/www:/var/www/certbot:ro" \
  nginx:stable-alpine

# 2. Issue the certificate (writes to /etc/letsencrypt on the host).
docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v "$(pwd)/docker/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d cyanroomserver.duckdns.org --email YOUR_EMAIL --agree-tos --no-eff-email --non-interactive

# 3. Tear down the bootstrap container — the real stack takes over from here.
docker stop nginx-bootstrap
```

### Normal operation

```bash
docker compose up -d
```

Starts the real `nginx` (full config, HTTPS + `/ui`/`/api`/`/cyan_pc`) and
`certbot` (renews automatically every ~12h, no-ops until the cert is close to
expiry). After editing `docker/nginx.conf` or `docker-compose.yml`, redeploy
with a full recreate rather than a restart, so any changed bind mounts or
volumes actually take effect:

```bash
docker compose down
docker compose up -d
```

Containers use `restart: unless-stopped`, so they also come back
automatically after a reboot as long as the Docker daemon itself is running
(it normally is, via its own systemd service) — no extra systemd unit needed
for those.


## 12. Mount the Pangea drive (NTFS, auto-mount on access)

> **Before you start:** migrate `/var/lib/plexmediaserver/Library/Application Support/Plex Media Server` from the old server — Plex metadata lives there and won't carry over automatically.

Install ffmpeg if needed:
```bash
sudo apt update && sudo apt install -y ffmpeg
```

Add `x-systemd.automount` to the Pangea fstab entry so the drive mounts on first access rather than at boot:
```bash
sudo sed -i 's|UUID=E408CE9E08CE6F5C /mnt/pangea ntfs3 rw,uid=1000,gid=1000,umask=002,nofail 0 0|UUID=E408CE9E08CE6F5C /mnt/pangea ntfs3 rw,uid=1000,gid=1000,umask=002,nofail,x-systemd.automount 0 0|' /etc/fstab
sudo systemctl daemon-reload
sudo mount /mnt/pangea
ls /mnt/pangea
```
