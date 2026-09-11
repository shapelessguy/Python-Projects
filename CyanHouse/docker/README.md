# nginx in Docker (Ubuntu)

Same reverse-proxy setup as the Windows `nginx/` folder (`/ui`, `/api`,
`/cyan_pc`), containerized instead of installing an nginx binary on the box.
Runs with `network_mode: host`, so it reaches the FastAPI backend
(`python -m api`, port 8000) on this same machine at `127.0.0.1:8000`
unchanged, and binds 80/443 directly on the host.

Prerequisites: Docker + Docker Compose installed, DNS
(`cyanroomserver.duckdns.org`) pointing at this machine's public IP, and ports
80/443 forwarded to it.

## First-time cert issuance (one-time, chicken-and-egg problem)

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
  -d cyanroomserver.duckdns.org --email YOUR_EMAIL --agree-tos --no-eff-email

# 3. Tear down the bootstrap container — the real stack takes over from here.
docker stop nginx-bootstrap
```

## Normal operation

```bash
docker compose up -d
```

Starts the real `nginx` (full config, HTTPS + `/ui`/`/api`/`/cyan_pc`) and
`certbot` (renews automatically every ~12h, no-ops until the cert is close to
expiry). After editing `docker/nginx.conf`, reload with:

```bash
docker compose restart nginx
```
