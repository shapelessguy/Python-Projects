# Earth HDD — layout, mount, share

Earth is an 8 TB Seagate IronWolf (NTFS, label `EARTH`, UUID
`BEB01463B0142505`) in a USB3-SATA dock (ASMedia bridge `174c:55aa`, UAS).
It replaced Pangea (4 TB, UUID `E408CE9E08CE6F5C`) in September 2026. It is
mounted at `/mnt/earth` and split in two top-level folders:

| Folder | Who uses it |
|---|---|
| `/mnt/earth/EARTH` | The Windows PC, as drive **E:** over SMB (`\\cyanserver\EARTH`). Nothing on the server points here |
| `/mnt/earth/CYAN` | This server only; not shared |

What lives in CYAN and who reads it:

| Consumer | How it sees the drive |
|---|---|
| Plex (`plexmediaserver.service`) | `/mnt/earth/CYAN/Video/*`, `/mnt/earth/CYAN/Music` |
| CyanHouse API (Movies/Music/Images panels) | `MOVIES_DIR=/mnt/earth/CYAN/Video/Movies`, etc. in `secrets.json` |
| qBittorrent container | bind `/mnt/earth` → `/mnt/earth` (`rslave`) |
| pyLoad container | bind `/mnt/earth` → `/mnt/earth` (`rslave`) |

Keeping CYAN out of the share means the PC and the server never work on the
same files. Windows never touches the disk itself: it talks to Samba, and
only Linux reads and writes the NTFS.

## Mount

One line in `/etc/fstab` mounts it at boot (Pangea's udev mount rule and
automount unit were removed). After a replug the API mounts it again (next
section), since systemd doesn't remount an fstab entry on hot-plug:
```
UUID=BEB01463B0142505 /mnt/earth ntfs3 rw,uid=1000,gid=1000,umask=002,nofail,force,x-systemd.device-timeout=180s 0 0
```
`nofail`: the boot doesn't hang if the dock is off. `device-timeout=180s`:
the dock can be slow to present the partition. `force`: mounts even when the
volume is flagged dirty (fix that with `chkdsk E: /f` on Windows with the
disk plugged in directly, never while this server has it mounted).

## The API runs what needs the drive

The CyanHouse API is the lead: it always runs, and a loop in it
(`api/services/drive_watch.py`, every 10 s, status at `GET /api/drive`)
decides for the rest. The condition is `/mnt/earth/CYAN` being there.

| Event | What happens |
|---|---|
| Partition appears (boot, replug), not mounted | API runs `systemctl start mnt-earth.mount` |
| `/mnt/earth/CYAN` becomes readable | API starts qBittorrent + pyLoad, then Plex |
| `/mnt/earth/CYAN` gone | API stops them, and keeps them stopped |
| Mounted device isn't the plugged-in one (pulled while busy, came back as a new `sdX`) | API stops them, unmounts the dead mount, mounts the drive again next round |
| API stops, restarts or dies | `ExecStopPost` of `cyanhouse-api.service` stops them (DEPLOY.md §9); a restarted API starts them again if the drive is there |

Once started they are left alone: stopping Plex by hand while the drive is
there is not undone. The services and containers are settings
(`MEDIA_DRIVE_*` in `api/config.py`).

One-time system setup:

1. Polkit, so the API (user `claudio`) may start and stop the mount and Plex
   without a password — `/etc/polkit-1/rules.d/50-cyanhouse-drive.rules`:
   ```js
   // CyanHouse API: runs Plex and mounts Earth while the drive is there (EARTH.md)
   polkit.addRule(function (action, subject) {
       if (action.id == "org.freedesktop.systemd1.manage-units" && subject.user == "claudio") {
           var unit = action.lookup("unit"), verb = action.lookup("verb");
           if ((unit == "plexmediaserver.service" || unit == "mnt-earth.mount") &&
               (verb == "start" || verb == "stop" || verb == "restart"))
               return polkit.Result.YES;
       }
   });
   ```
2. A lazy unmount, so a drive pulled while files are open doesn't leave a
   dead mount behind (systemd's unmount otherwise fails with "target is
   busy") — `/etc/systemd/system/mnt-earth.mount.d/lazy.conf`:
   ```ini
   [Mount]
   LazyUnmount=yes
   ```
3. Plex is started by the API, not by the boot:
   `sudo systemctl disable plexmediaserver`. (A Plex update may enable it
   again; harmless — without the drive the API stops it within 10 s.)
4. The `ExecStopPost` lines in `cyanhouse-api.service` (DEPLOY.md §9).

qBittorrent and pyLoad keep compose's `restart: unless-stopped`: a
`docker stop` from the API counts as a manual stop, so Docker doesn't start
them on its own at boot, but still restarts one that crashes.

In Plex, keep *Settings → Library → Empty trash automatically after every
scan* **off** anyway: it is what would drop the whole library, watch history
included, if a scan ever ran against a missing folder.

## Permissions

The NTFS driver maps everything to `claudio` (`uid=1000`), mode 775. Windows
marks many folders Read-only (those with a custom icon), and ntfs3 turns that
into "not writable" — clear it with:
```bash
find /mnt/earth/EARTH /mnt/earth/CYAN -type d ! -perm -u+w -exec chmod u+w {} +
```
Explorer only reads a folder's `desktop.ini` (custom icon) when the folder is
Read-only or System. Samba keeps its own copy of the DOS flags in an extended
attribute, so the folders get the System flag instead, set from the PC:
```powershell
Get-ChildItem E:\ -Recurse -Force -Filter desktop.ini -ErrorAction SilentlyContinue | ForEach-Object { attrib +s "$($_.DirectoryName)"; attrib +h +s "$($_.FullName)" }
```
Only needed for folders copied onto the drive from the server side; a custom
icon set from the PC through E: gets its flag from Windows.

## SMB share

Samba (`smbd`), share defined at the end of `/etc/samba/smb.conf`:
```ini
[EARTH]
   path = /mnt/earth/EARTH
   browseable = yes
   read only = no
   valid users = claudio
   force user = claudio
   force group = claudio
```
The Samba password is separate from the Linux one: `sudo smbpasswd -a claudio`.
On the PC: *Map network drive* → `E:` → `\\cyanserver\EARTH` (or
`\\192.168.178.192\EARTH`), *Connect using different credentials*, user
`claudio`, *Remember my credentials*.

## Plex registration safety net (from Pangea, still installed)

When Plex starts it registers with plex.tv in two calls about 15 s apart;
if the second (`POST servers.plex.tv/servers.xml → 201`) fails, Plex never
retries and every app shows empty libraries. `plex-publish-check.timer`
runs 5 min after boot and then every 30 min, and restarts Plex if its log's
latest mapping state is `No server`.

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

## Health check

```bash
findmnt /mnt/earth
```
```bash
docker exec cyanhouse-pyload ls /mnt/earth/CYAN
```
It should list CYAN's folders, not nothing.
```bash
grep -E 'servers.xml|No server' "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Logs/Plex Media Server.log" | head
```
You want a `201 response from POST https://servers.plex.tv/servers.xml` and no `No server`.
