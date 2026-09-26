# Pangea HDD — setup for a smooth boot

Pangea is a 4 TB Seagate (NTFS, label `PANGEA`, UUID `E408CE9E08CE6F5C`) in a
powered Ugreen USB3-SATA dock (Innostor bridge `1f75:0611`). It is mounted
at `/mnt/pangea`. Everything media-related depends on it:

| Consumer | How it sees the drive |
|---|---|
| Plex (`plexmediaserver.service`) | `/mnt/pangea/Video/*`, `/mnt/pangea/Music` |
| CyanHouse API (Movies/Music panels) | `MOVIES_DIR=/mnt/pangea/Video/Movies`, etc. |
| qBittorrent container | bind `/mnt/pangea` → `/mnt/pangea` (`rslave`) |
| pyLoad container | bind `/mnt/pangea` → `/pangea` |

The machine reboots every night at 03:00 (root crontab, DEPLOY.md §13), so
this boot sequence runs every day.

## What a boot looks like (measured)

- The dock is slow. The kernel sees `sdb` at ~6 s, then a command times out
  (`waited 15s`), and the partition only reaches systemd at **38–76 s**.
- The NTFS mount itself takes **33–40 s**. The volume is flagged dirty
  (`ntfs3: It is recommended to use chkdsk`) and mounts only because of
  `force`.
- So the drive is ready ~80–110 s after boot. By then Docker and its
  containers are long up, and NordVPN has connected (~45 s).

Anything started before that sees an empty `/mnt/pangea`, and anything that
reacts to the mount at the same moment can collide. That collision caused the
"Plex libraries empty after reboot" bug; see the next section.

## The Plex "empty libraries" bug (fixed 2026-09-26)

When Plex starts it registers with plex.tv in two calls about 15 s apart:
the second is `POST servers.plex.tv/servers.xml → 201`. That registration is
how every app finds the server. **If the second call fails, Plex never
retries.** It stays in `Mapped - Not Published (No server)`, and every app
shows empty libraries until Plex is restarted by hand.

At boot, `automount-pangea.service` used to restart Plex and then
`docker restart cyanhouse-pyload` at the same moment. pyload takes 10 s to
stop and is force-killed, and Docker then rebuilds its network, which cut
Plex's open connection to plex.tv. So the 26 Sep boot log shows
`servers.xml … Broken pipe` → `No server`.

Fixed by (all installed on cyanserver):
1. `automount-pangea.service` restarts pyload **before** Plex.
2. `plex-publish-check.timer` runs 5 min after boot and then every 30 min.
   If the Plex log's latest state is `No server`, it restarts Plex.
3. `RequiresMountsFor=/mnt/pangea` moved out of the vendor unit (which every
   Plex update overwrites) into
   `/etc/systemd/system/plexmediaserver.service.d/override.conf`.

How to check it after a reboot:
```bash
grep -E 'servers.xml|No server' "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log" | head
```
You want a `201 response from POST https://servers.plex.tv/servers.xml` and no `No server`.

## Current state: what is fine, what still isn't

| Piece | State |
|---|---|
| fstab entry (`nofail,force`) | OK, and it is what actually mounts the drive at boot |
| Plex waits for the mount | OK (override.conf) |
| Plex registration safety net | OK (plex-publish-check.timer) |
| udev `systemd-run … mount /dev/sdb2` rule | **Redundant, remove.** It races the fstab mount (each boot logs 2 failed `run-p…` units, "already mounted") and uses the unstable name `sdb2` |
| udev `hdparm -S 0 -B 255 /dev/sdb` rule | **Useless, remove.** It fails every boot (`exit code 22`) because the USB bridge does not pass APM commands |
| `automount-pangea.service` mounts with its own `mount` command | **Duplicate** of the fstab line; should just start `mnt-pangea.mount` |
| pyLoad bind mount has no `rslave` | **Root cause of the Docker restart.** pyLoad starts before the drive, keeps the empty mount point, and has to be restarted. With `rslave` (like qBittorrent) the mount reaches it on its own, and the restart, the network churn and the Plex race all go away |
| NTFS dirty flag | **Needs chkdsk on Windows.** `force` hides it; a dirty NTFS mounted read-write can lose data |
| Dock idle resets | Still happening: 65 `reset SuperSpeed USB device` in one day despite `keep_pangea_awake.py`. Harmless while they don't turn into a disconnect (DEPLOY.md §11) |
| Boot `timing out command, waited 15s` | The dock; costs ~30 s per boot, nothing to fix in software |

## Target setup (do these once)

### 1. fstab: the single place the drive is described

`/etc/fstab`:
```
UUID=E408CE9E08CE6F5C /mnt/pangea ntfs3 rw,uid=1000,gid=1000,umask=002,nofail,force,x-systemd.device-timeout=180s 0 0
```
`nofail`: the boot doesn't hang if the dock is off. `device-timeout=180s`:
the partition can take 76 s to appear, so waiting only the default 90 s
is too close.

### 2. udev: keep only the power rule

`/etc/udev/rules.d/99-ugreen-no-autosuspend.rules` should contain just:
```
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="1f75", ATTR{idProduct}=="0611", TEST=="power/control", ATTR{power/control}="on"
```
Delete the `hdparm` and `systemd-run … mount` lines. Then:
```bash
sudo udevadm control --reload
```

### 3. pyLoad: `rslave` like qBittorrent

In `docker-compose.yml`, replace pyLoad's `- /mnt/pangea:/pangea` with:
```yaml
      - type: bind
        source: /mnt/pangea
        target: /pangea
        bind:
          propagation: rslave
```
Then apply it:
```bash
docker compose up -d pyload
```

### 4. automount-pangea.service: for replugs only

The fstab mount covers boot. This unit covers the dock being unplugged and
plugged back in while the server runs (systemd doesn't remount an fstab
entry on hot-plug). Once step 3 is done, it no longer needs to restart
pyLoad, and it mounts via the fstab unit instead of its own command.

`/etc/systemd/system/automount-pangea.service`:
```ini
[Unit]
Description=Mount Pangea when its drive appears, then restart Plex
BindsTo=dev-disk-by\x2duuid-E408CE9E08CE6F5C.device
After=dev-disk-by\x2duuid-E408CE9E08CE6F5C.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/systemctl start mnt-pangea.mount
ExecStartPost=/bin/systemctl --no-block restart plexmediaserver.service

[Install]
WantedBy=dev-disk-by\x2duuid-E408CE9E08CE6F5C.device
```

### 5. Plex (already done, for a fresh machine)

`/etc/systemd/system/plexmediaserver.service.d/override.conf`:
```ini
[Unit]
RequiresMountsFor=/mnt/pangea
```

`/etc/systemd/system/plex-publish-check.service`:
```ini
[Unit]
Description=Restart Plex if it failed to register with plex.tv
After=plexmediaserver.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'grep "mapping state set to" "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log" | tail -1 | grep -q "No server" && systemctl restart plexmediaserver.service || true'
```

`/etc/systemd/system/plex-publish-check.timer`:
```ini
[Unit]
Description=Check Plex's plex.tv registration after boot and every 30 min

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now plex-publish-check.timer
```

Don't edit `/usr/lib/systemd/system/plexmediaserver.service`: Plex updates
replace it.

### 6. Apply and reboot

```bash
sudo systemctl daemon-reload
```
```bash
sudo reboot
```

### 7. Once: chkdsk on Windows

Plug the dock into a Windows machine and run `chkdsk X: /f` (X = Pangea's
letter). Afterwards the kernel stops printing `It is recommended to use
chkdsk`, and the mount should also get faster.

## After a reboot: health check

```bash
journalctl -b -o short-monotonic | grep -E 'Mounted mnt-pangea|Started plexmediaserver|run-p.*mount'
```
The mount should come first, then Plex, and there should be no `run-p…` mount units.

```bash
systemctl --failed
```
Nothing Pangea-related should be listed.

```bash
docker exec cyanhouse-pyload ls /pangea
```
It should list the drive's folders, not nothing.

Plus the `servers.xml` / `201` check from the Plex section above.
