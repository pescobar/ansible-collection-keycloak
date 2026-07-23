# keycloak_deploy

Deploys [Keycloak](https://www.keycloak.org/) in **production mode** behind a
[Caddy](https://caddyserver.com/) reverse proxy that terminates TLS with
**automatic HTTPS (Let's Encrypt)**, backed by **PostgreSQL** — all as a single
Docker Compose stack. Part of the `pescobar.keycloak` collection.

```
                 :443 / :80
   Internet ───────────────▶  Caddy  ──http──▶  Keycloak  ──▶  PostgreSQL
                          (Let's Encrypt TLS)    (:8080)         (:5432)
```

## What this role does and does not do

- **Does:** verify Docker is present, render a `docker-compose.yml`, `Caddyfile`
  and `.env`, and bring the stack up idempotently.
- **Does NOT:** install Docker. Docker Engine and the Compose v2 plugin must
  already be installed on the target host. The role runs preflight checks and
  fails with a clear message if either is missing.

## Requirements

- **Target host:** Docker Engine + `docker compose` (Compose v2 plugin) already
  installed and running; the connecting user able to use the Docker socket.
- **Controller:** the `community.docker` collection (a dependency of this
  collection).
- **DNS & firewall:** for Let's Encrypt, `keycloak_deploy_hostname` must resolve
  publicly to the host and ports **80** and **443** must be reachable from the
  internet. (Port 80 is needed for the ACME challenge and HTTP→HTTPS redirect.)

## Role variables

See [`defaults/main.yml`](defaults/main.yml) for the full list. The ones you
**must** set:

| Variable | Description |
| --- | --- |
| `keycloak_deploy_hostname` | Public FQDN Keycloak is served on (cert is issued for it). |
| `keycloak_deploy_acme_email` | Email for the Let's Encrypt account. |
| `keycloak_deploy_admin_password` | Bootstrap admin password (use Vault). |
| `keycloak_deploy_db_password` | PostgreSQL password (use Vault). |

The role refuses to run while these still hold their placeholder defaults.

Commonly tuned optional variables:

| Variable | Default | Description |
| --- | --- | --- |
| `keycloak_deploy_version` | `26.6.2-2` | Keycloak image tag. |
| `keycloak_deploy_caddy_version` | `2` | Caddy image tag. |
| `keycloak_deploy_postgres_version` | `18` | PostgreSQL image tag (tracks latest 18.x). |
| `keycloak_deploy_admin_hostname` | `""` | Optional separate public FQDN for the admin console. When set, the role adds `KC_HOSTNAME_ADMIN` and Caddy serves + gets a cert for this domain too. Must resolve publicly to the host. |
| `keycloak_deploy_admin_hostname_allowed_ips` | `[]` | Optional CIDR/IP (string) or list of them. When set (and `keycloak_deploy_admin_hostname` is set), Caddy returns 403 to any client outside these subnets before the request reaches Keycloak. |
| `keycloak_deploy_dir` | `/opt/keycloak` | Where artifacts are rendered. |
| `keycloak_deploy_acme_ca` | `""` | Set to the LE **staging** URL while testing to avoid rate limits. |
| `keycloak_deploy_http_port` / `keycloak_deploy_https_port` | `80` / `443` | Host ports Caddy binds. |
| `keycloak_deploy_extra_env` | `{}` | Extra `KC_*` env vars for Keycloak. |

## Usage

```yaml
- hosts: keycloak
  become: true
  roles:
    - role: pescobar.keycloak.keycloak_deploy
      vars:
        keycloak_deploy_hostname: "auth.example.com"
        keycloak_deploy_acme_email: "admin@example.com"
        keycloak_deploy_admin_password: "{{ vault_keycloak_admin_password }}"
        keycloak_deploy_db_password: "{{ vault_keycloak_db_password }}"
```

Generate strong secrets, e.g.:
```bash
openssl rand -base64 24
```
and store them in an Ansible Vault file. Then:
```bash
ansible-playbook -i inventory playbook.yml --ask-vault-pass
```

## Notes & tips

- **Testing certificates:** set
  `keycloak_deploy_acme_ca: "https://acme-staging-v02.api.letsencrypt.org/directory"`
  to use Let's Encrypt staging while you iterate, then remove it for a trusted
  production cert.
- **Bootstrap admin:** `keycloak_deploy_admin_user`/`keycloak_deploy_admin_password`
  create Keycloak 26's *temporary* bootstrap admin. Log in, create a permanent
  admin account, and remove/rotate the bootstrap one.
- **Reverse proxy:** Keycloak runs with `KC_PROXY_HEADERS=xforwarded` and
  `KC_HOSTNAME=https://<hostname>`; Caddy forwards the original `Host` and
  `X-Forwarded-*` headers so login/redirect URLs are correct.
- **Data persistence:** PostgreSQL data and Caddy's certificates live in named
  Docker volumes (`*_postgres_data`, `*_caddy_data`) and survive restarts.

## License

MIT
