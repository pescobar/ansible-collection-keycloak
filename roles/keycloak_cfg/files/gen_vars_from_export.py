#!/usr/bin/env python3
"""Seed keycloak_cfg variables from a Keycloak realm export.

ONE-OFF, OFFLINE convenience. Reads a ``kc.sh export`` realm JSON and emits the
flat ``keycloak_cfg_*`` variables for that realm, ready to drop into group_vars
for the keycloak_cfg role. By default, secrets and private keys are replaced with
Ansible Vault placeholders — the default output never contains real secrets.

Pass ``--with-secrets`` to emit the real secret values inline instead (client
secrets, OIDC broker secrets and realm-key private keys). This is a convenience
for seeding, but the output then contains PLAINTEXT secrets: encrypt it
(``ansible-vault encrypt``) and never commit it as-is.

Unlike the REST-based playbooks/export_realm.yml (which needs only admin API
access but produces a raw, review-heavy scaffold), this consumes the native
export — the only source that contains realm-key *private* material — and maps
each field to the module-native option names the keycloak_cfg role passes through
to community.general.keycloak_*. It is still a starting point: review the output
and define the listed vault_* variables before applying.

Get an export first (needs host/container access):

    docker compose exec keycloak /opt/keycloak/bin/kc.sh export \\
        --dir /tmp/kc-export --realm myapp --users skip
    docker compose cp keycloak:/tmp/kc-export ./kc-export   # -> myapp-realm.json

Then, one file per realm:

    gen_vars_from_export.py myapp-realm.json > group_vars/keycloak/myapp.yml

A multi-realm export file (a JSON list of realms) is also accepted; its realms
are merged into the same flat lists.
"""
import argparse
import json
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")


def _str_representer(dumper, data):
    # Multiline strings (PEM certs / keys) -> literal block scalar, no quotes.
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


yaml.add_representer(str, _str_representer, Dumper=yaml.SafeDumper)

# Keycloak built-in clients we never want to manage.
BUILTIN_CLIENTS = ("account", "account-console", "admin-cli", "broker",
                   "realm-management", "security-admin-console")

# Realm-representation (camelCase) -> keycloak_realm module option (snake_case).
# Only a curated, widely-supported subset is emitted; extend as needed.
REALM_FIELDS = [
    ("enabled", "enabled"),
    ("displayName", "display_name"),
    ("displayNameHtml", "display_name_html"),
    ("loginWithEmailAllowed", "login_with_email_allowed"),
    ("registrationAllowed", "registration_allowed"),
    ("registrationEmailAsUsername", "registration_email_as_username"),
    ("resetPasswordAllowed", "reset_password_allowed"),
    ("rememberMe", "remember_me"),
    ("verifyEmail", "verify_email"),
    ("editUsernameAllowed", "edit_username_allowed"),
    ("sslRequired", "ssl_required"),
    ("loginTheme", "login_theme"),
    ("accountTheme", "account_theme"),
    ("adminTheme", "admin_theme"),
    ("emailTheme", "email_theme"),
]

# clientRepresentation (camelCase) -> keycloak_client module option (snake_case).
CLIENT_FIELDS = [
    ("name", "name"),
    ("description", "description"),
    ("enabled", "enabled"),
    ("protocol", "protocol"),
    ("publicClient", "public_client"),
    ("bearerOnly", "bearer_only"),
    ("standardFlowEnabled", "standard_flow_enabled"),
    ("implicitFlowEnabled", "implicit_flow_enabled"),
    ("directAccessGrantsEnabled", "direct_access_grants_enabled"),
    ("serviceAccountsEnabled", "service_accounts_enabled"),
    ("frontchannelLogout", "frontchannel_logout"),
    ("rootUrl", "root_url"),
    ("baseUrl", "base_url"),
    ("adminUrl", "admin_url"),
    ("redirectUris", "redirect_uris"),
    ("webOrigins", "web_origins"),
]

# Collected vault placeholder names, reported in the header so the user knows
# exactly which secrets to define.
VAULT_VARS = set()

# Free-text notes about what was skipped/simplified, reported in the header.
# Kept out of the emitted data so every item stays a valid module argument set.
NOTES = []

# When True, emit real secret values instead of vault_* placeholders (set from
# the --with-secrets flag). Default False keeps secrets out of the output.
INCLUDE_SECRETS = False

# In --with-secrets mode, the suggested Vault var name for each inlined secret,
# reported in the header so it is obvious which values are secrets to move out.
SECRETS_INLINED = set()


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(name))


def _secret(real, vault_var: str):
    """Real secret value when --with-secrets, else a named vault placeholder.

    Either way the secret is tracked by the ``vault_var`` name it should map to,
    reported in the header (as a placeholder to define, or as an inlined
    plaintext value to move into Vault).
    """
    if INCLUDE_SECRETS:
        SECRETS_INLINED.add(vault_var)
        return real if real is not None else ""
    VAULT_VARS.add(vault_var)
    return "{{ %s }}" % vault_var


def _first(v, default=""):
    """Component config values are single-element lists in exports."""
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _pick(src: dict, fields, dst: dict) -> None:
    for src_key, dst_key in fields:
        if src.get(src_key) is not None:
            dst[dst_key] = src[src_key]


def convert(realm_rep: dict, out: dict) -> None:
    realm = realm_rep["realm"]

    # --- realm settings ---
    realm_item = {"realm": realm}
    _pick(realm_rep, REALM_FIELDS, realm_item)
    if realm_rep.get("attributes"):
        realm_item["attributes"] = realm_rep["attributes"]
    realm_item["state"] = "present"
    out["keycloak_cfg_realms"].append(realm_item)

    # --- groups (top-level only; subgroups are noted, not expanded) ---
    for g in realm_rep.get("groups", []) or []:
        out["keycloak_cfg_groups"].append(
            {"realm": realm, "name": g["name"], "state": "present"})
        if g.get("subGroups"):
            NOTES.append("group '%s/%s' has subgroups (%s) — add them by hand." % (
                realm, g["name"], ", ".join(sg["name"] for sg in g["subGroups"])))

    # --- clients (skip built-ins) ---
    for c in realm_rep.get("clients", []) or []:
        cid = c.get("clientId", "")
        if cid in BUILTIN_CLIENTS:
            continue
        item = {"realm": realm, "client_id": cid}
        _pick(c, CLIENT_FIELDS, item)
        if c.get("attributes"):
            item["attributes"] = c["attributes"]
        if not c.get("publicClient", False):
            item["secret"] = _secret(c.get("secret"), "vault_kc_client_secret_%s" % _slug(cid))
        item["state"] = "present"
        out["keycloak_cfg_clients"].append(item)

    # --- identity providers + their mappers (provider-agnostic) ---
    mappers_by_alias = {}
    for m in realm_rep.get("identityProviderMappers", []) or []:
        mappers_by_alias.setdefault(m["identityProviderAlias"], []).append({
            "name": m["name"],
            "identityProviderMapper": m["identityProviderMapper"],
            "config": m.get("config", {}) or {},
        })
    for idp in realm_rep.get("identityProviders", []) or []:
        cfg = dict(idp.get("config", {}) or {})
        if "clientSecret" in cfg:  # OIDC broker secret
            cfg["clientSecret"] = _secret(
                cfg["clientSecret"], "vault_kc_idp_%s_client_secret" % _slug(idp["alias"]))
        item = {
            "realm": realm,
            "alias": idp["alias"],
            "provider_id": idp["providerId"],
            "enabled": idp.get("enabled", True),
            "config": cfg,
            "mappers": mappers_by_alias.get(idp["alias"], []),
            "state": "present",
        }
        if idp.get("displayName"):
            item["display_name"] = idp["displayName"]
        out["keycloak_cfg_identity_providers"].append(item)

    # --- realm keys: imported rsa / rsa-enc only (generated keys need no seeding) ---
    comps = realm_rep.get("components", {}) or {}
    for kp in comps.get("org.keycloak.keys.KeyProvider", []) or []:
        pid = kp.get("providerId")
        if pid not in ("rsa", "rsa-enc"):
            continue
        name = kp.get("name", pid)
        cfg = kp.get("config", {}) or {}
        out["keycloak_cfg_realm_keys"].append({
            "parent_id": realm,
            "name": name,
            "provider_id": pid,
            # imported keys are not drift-detectable; force re-applies the value
            "force": True,
            "config": {
                "private_key": _secret(_first(cfg.get("privateKey")),
                                       "vault_kc_%s_%s_private_key" % (_slug(realm), _slug(name))),
                "certificate": _first(cfg.get("certificate")),
                "active": _first(cfg.get("active"), "true") == "true",
                "enabled": _first(cfg.get("enabled"), "true") == "true",
                "priority": int(_first(cfg.get("priority"), "100")),
                "algorithm": _first(cfg.get("algorithm")),
            },
            "state": "present",
        })

    # --- declarative user profile ---
    # The stored kc.user.profile.config JSON *is* the exact representation the
    # /admin/realms/{realm}/users/profile REST endpoint accepts (camelCase keys,
    # kebab-case validator ids), which is how the keycloak_cfg role applies it.
    # Emit it verbatim; there is one effective profile per realm.
    up_comps = comps.get("org.keycloak.userprofile.UserProfileProvider", []) or []
    raw = up_comps[0].get("config", {}).get("kc.user.profile.config") if up_comps else None
    if raw:
        out["keycloak_cfg_user_profiles"].append({
            "realm": realm,
            "profile": json.loads(_first(raw)),
        })


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed keycloak_cfg variables from a Keycloak realm export.")
    parser.add_argument("export_json",
                        help="path to a kc.sh export realm JSON (or a JSON list of realms)")
    parser.add_argument("--with-secrets", action="store_true",
                        help="emit real secret values instead of vault_* placeholders "
                             "(DANGER: writes PLAINTEXT secrets to the output)")
    args = parser.parse_args()

    global INCLUDE_SECRETS
    INCLUDE_SECRETS = args.with_secrets
    if INCLUDE_SECRETS:
        sys.stderr.write(
            "WARNING: --with-secrets set: output contains PLAINTEXT secrets. "
            "Encrypt it (ansible-vault encrypt) and do not commit it as-is.\n")

    with open(args.export_json) as f:
        data = json.load(f)
    realms = data if isinstance(data, list) else [data]

    out = {
        "keycloak_cfg_realms": [],
        "keycloak_cfg_groups": [],
        "keycloak_cfg_clients": [],
        "keycloak_cfg_identity_providers": [],
        "keycloak_cfg_realm_keys": [],
        "keycloak_cfg_user_profiles": [],
    }
    for r in realms:
        convert(r, out)

    # Drop empty lists (always keep realms).
    doc = {k: v for k, v in out.items() if v or k == "keycloak_cfg_realms"}

    names = ", ".join(r["realm"] for r in out["keycloak_cfg_realms"])
    print("---")
    print("# Generated by gen_vars_from_export.py from realm(s): %s" % names)
    print("#")
    print("# SCAFFOLD — review before applying with the keycloak_cfg role:")
    if INCLUDE_SECRETS:
        print("#  * WARNING: contains PLAINTEXT secrets (--with-secrets). Encrypt")
        print("#    this file (ansible-vault encrypt) and do NOT commit it as-is.")
    else:
        print("#  * Fill the vault_* variables below (kept out of this file).")
    print("#  * Curated field subset: uncommon options and client protocol")
    print("#    mappers are omitted — add them by hand if you need them.")
    if VAULT_VARS:
        print("#")
        print("# Vault variables to define:")
        for v in sorted(VAULT_VARS):
            print("#   %s" % v)
    if SECRETS_INLINED:
        print("#")
        print("# >>> PLAINTEXT SECRETS below — move each value into Vault. The")
        print("#     suggested variable name for each secret is:")
        for v in sorted(SECRETS_INLINED):
            print("#   %s" % v)
    if NOTES:
        print("#")
        print("# Skipped / needs attention:")
        for n in NOTES:
            print("#   - %s" % n)
    yaml.safe_dump(doc, sys.stdout, sort_keys=False, default_flow_style=False,
                   width=100, allow_unicode=True)


if __name__ == "__main__":
    main()
