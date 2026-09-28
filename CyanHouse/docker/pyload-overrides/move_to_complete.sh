#!/bin/sh
# pyLoad ExternalScripts hook: runs once a package is done *and* ExtractArchive
# has dealt with it (extracted it, or skipped it as not an archive) — the
# moment it is really complete. Moves its folder from the in-progress area
# (/mnt/earth/CYAN/temp/pyload, pyLoad's storage_folder) to the finished
# one (/mnt/earth/CYAN/downloads, qBittorrent's completed-downloads folder).
# The container sees the drive at its host path.
# Args: package id, package name, package folder, archive password.
src="$3"
[ -d "$src" ] || exit 0
case "$src" in /mnt/earth/CYAN/temp/pyload/?*) ;; *) exit 0 ;; esac  # never the root itself
name=$(basename "$src")
dest="/mnt/earth/CYAN/downloads/$name"
n=1
while [ -e "$dest" ]; do dest="/mnt/earth/CYAN/downloads/$name ($n)"; n=$((n + 1)); done
mv "$src" "$dest"
