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

## 8. Check the `secrets.json` file (top level)

Gitignored — doesn't come with `git pull`, and holds *everything* config-ish
that used to be split across `.env` and `api/users.json`: ports, hosts, API
keys, and the `users` map. Create it from `secrets.json.example`:

```bash
cd ~/Documents/sharedCode/CyanHouse
cp secrets.json.example secrets.json
nano secrets.json
```

Fill in for *this* machine specifically: `PUBLIC_HOST`,
`CONTROLS_FN_HOST`/`CONTROLS_FN_PORT`,
`DATA_DIR` (blank unless you want data elsewhere), `SERPER_API_KEY`,
`OPENROUTER_KEY`/`LLM_FOOD_MODEL`.

And real user credentials under `"users"` — without at least one entry, the
app falls back to `dev`/`dev` (logs a warning), not something you want exposed
once this is live behind nginx:

```bash
python3 -c "import secrets; print(secrets.token_hex(16))"   # generate a token
```

```json
{
  "...": "... (ports/hosts/keys above) ...",
  "users": {
    "claudio": { "token": "the-token-you-just-generated", "permissions": {} }
  }
}
```

Each user's `permissions` dict optionally takes a `visibility` list (panel
ids: `controls`, `environment`, `personal`, `food`, `calendar`) restricting
which panels/APIs that user can reach — omit it entirely for "sees everything"
(the default).

## 9. Backend as a service

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

## 10. nginx + HTTPS (Docker)

Same reverse-proxy setup as the Windows `nginx/` folder (`/ui`, `/api`,
`/cyan_pc`), containerized instead of installing an nginx binary on the box.
Runs with `network_mode: host`, so it reaches the FastAPI backend
(`python -m api`, port 8000) on this same machine at `127.0.0.1:8000`
unchanged, and binds 80/443 directly on the host.

Prerequisites: Docker + Docker Compose installed, DNS (your `PUBLIC_HOST`
from `secrets.json`, step 8) pointing at this machine's public IP, and ports
80/443 forwarded to it (step 7, above).

### Render the nginx config

`docker/nginx.conf` and `docker/nginx-bootstrap.conf` are generated,
gitignored files — the tracked source is `docker/nginx.conf.template` /
`docker/nginx-bootstrap.conf.template`, with `${PUBLIC_HOST}`, `${API_PORT}`,
`${CONTROLS_FN_HOST}` and `${CONTROLS_FN_PORT}` placeholders filled in from
`secrets.json` so the domain/ports live in exactly one place. Render (or
re-render, after editing `secrets.json` or either `.template`) with:

```bash
python3 scripts/render_nginx_conf.py
```

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
PUBLIC_HOST=$(python3 -c "import json; print(json.load(open('secrets.json'))['PUBLIC_HOST'])")
docker run --rm \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v "$(pwd)/docker/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d "$PUBLIC_HOST" --email YOUR_EMAIL --agree-tos --no-eff-email --non-interactive

# 3. Tear down the bootstrap container — the real stack takes over from here.
docker stop nginx-bootstrap
```

### Normal operation

```bash
docker compose up -d
```

Starts the real `nginx` (full config, HTTPS + `/ui`/`/api`/`/cyan_pc`) and
`certbot` (renews automatically every ~12h, no-ops until the cert is close to
expiry). After editing `secrets.json` or either `.template` file, re-render
(above) and redeploy with a full recreate rather than a restart, so any
changed bind mounts or volumes actually take effect:

```bash
docker compose down
docker compose up -d
```

Containers use `restart: unless-stopped`, so they also come back
automatically after a reboot as long as the Docker daemon itself is running
(it normally is, via its own systemd service) — no extra systemd unit needed
for those.


## 11. Mount the Pangea drive (NTFS, auto-mount on access)

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

### Troubleshooting: Pangea randomly disconnects, needs a physical replug

Pangea is a HDD in a powered Ugreen USB3-to-SATA dock, not an internal SATA
drive. `journalctl -k` shows its USB bridge chip (`idVendor=1f75`, an
Innostor bridge) issuing a `reset SuperSpeed USB device` on an almost exact
10-minute cadence whenever the drive has been idle -- with no correlation to
any actual read/write activity, cron job, or systemd timer on this box.
That points at the dock's own firmware: a built-in idle-link-reset timer
that renegotiates its internal USB<->SATA link to save power. Usually that
renegotiation is harmless, but it occasionally fails outright and drops the
whole USB device, which is what looks like a random disconnect and needs a
physical unplug/replug to recover (that power-cycles the bridge chip).

Workaround: `scripts/keep_pangea_awake.py`, run every 5 minutes via crontab
(`crontab -l` to check it's there), writes and `fsync`s a tiny file on
Pangea so the drive never idles long enough for the dock's timer to fire.
It's a mitigation for the dock's firmware behavior, not a real fix -- if a
full disconnect still happens occasionally, a replug is still the recovery.

## 12. Automated database backups (OneDrive via rclone)

Backs up all of `data/` (the three SQLite DBs + food images + anything else
under it, except `data/forecast/`'s regenerable API cache) to OneDrive, once
per server restart rather than on a fixed clock schedule. See
`scripts/backup_dbs.py`'s own module docstring for exactly how retention
works (geometric/logarithmic bucketing, same-day dedup, a rolling `current/`
snapshot) — this section is just the one-time machine setup.

### Install rclone (no root needed — a static binary, not an apt package)

```bash
mkdir -p ~/.local/bin
curl -sL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip
cd /tmp && unzip -q rclone.zip && cd rclone-*-linux-amd64
cp rclone ~/.local/bin/rclone && chmod +x ~/.local/bin/rclone
~/.local/bin/rclone version   # confirm it runs
```

### Configure the OneDrive remote (one-time, interactive, needs a browser)

cyanserver is headless, so the OAuth login has to happen on a *different*
machine that has both a browser and rclone installed:

```bash
~/.local/bin/rclone config
```

Walk the wizard: `n` (new remote) → name it exactly `onedrive` → pick
**Microsoft OneDrive** from the storage list (the type string must come out
as `onedrive` — don't confuse it with "OpenDrive", an unrelated service with
a near-identical name in the same list) → leave client_id/client_secret
blank (Enter) → region `1` (global) → tenant blank → "Edit advanced config?"
→ `n` → "Use web browser to automatically authenticate?" → `n` (no browser
here) → it prints a command like:

```
Please run rclone authorize "onedrive" on your machine with web browser access
```

Run *that* on the other machine, sign in, approve access, and it prints a
JSON token blob — paste that back into cyanserver's prompt exactly as
printed (nothing before/after it). Finish by picking the actual
**OneDrive (personal)** drive from the list it shows (not the other
cryptic-GUID / "Bundles_..." entries, which are other apps' hidden storage on
the same account). Verify:

```bash
~/.local/bin/rclone lsd onedrive:
```

Should list your real OneDrive folders. This only needs doing once — the
stored refresh token renews itself silently on every subsequent backup run,
so it won't ask for credentials again as long as the cron job below keeps
running at least occasionally.

### Wire up the backup

```bash
crontab -e
```

Add:

```
@reboot /usr/bin/python3 /home/claudio/Documents/sharedCode/CyanHouse/scripts/backup_dbs.py >> /home/claudio/Documents/sharedCode/CyanHouse/scripts/backup.log 2>&1
```

This is in *your own* crontab (not root's) — the script only reads project
files and writes to `~/backups/cyanhouse/` + OneDrive, nothing that needs
root. Verify after the next restart:

```bash
cat scripts/backup.log                                 # should show "backed up N files to ..."
~/.local/bin/rclone lsf onedrive:CyanHouseBackups/ --dirs-only   # timestamped snapshots + current/
```

To back up on demand without waiting for a restart: `python3 scripts/backup_dbs.py`.

## 13. Daily automatic restart

Root's crontab (not yours — rebooting needs root):

```bash
sudo crontab -e
```

Add:

```
0 3 * * * /usr/sbin/reboot
```

This reboots the *whole machine* at 3am daily, not just the API process —
nginx and any other containers/services on cyanserver go down and back up
with it, not just CyanHouse. Everything that needs to survive a reboot
already does, and needs no further setup:

- `cyanhouse-api.service` is `enabled` (see step 9) and starts on boot.
- The two Docker containers (`cyanhouse-nginx`, `cyanhouse-certbot`) use
  `restart: unless-stopped` (see step 10) and come back once Docker's own
  systemd service starts.
- The reboot itself also fires the `@reboot` backup job from step 12, so the
  daily restart doubles as a daily backup trigger for free.

### Troubleshooting: `cyanhouse-api.service` shows `inactive` but the site half-works

If it was ever manually recovered by starting the tmux session directly
(`tmux new -s cyanhouse-api -d '.../python -m api'`) instead of through
`systemctl`, systemd loses track of it — `systemctl status` will say
`inactive` even though the backend is actually running. Left alone, the
*next* reboot's `systemctl start` will then fail outright, because
`ExecStart`'s `tmux new -s cyanhouse-api` errors out when a session by that
name already exists. Reconcile it:

```bash
tmux kill-session -t cyanhouse-api
sudo systemctl start cyanhouse-api.service
```

Brief downtime during the handoff, then it's back under proper supervision.
