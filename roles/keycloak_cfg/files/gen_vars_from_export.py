#!/usr/bin/env python3
"""Seed keycloak_cfg variables from a Keycloak realm export.

ONE-OFF, OFFLINE convenience. Reads a ``kc.sh export`` realm JSON and emits the
flat ``keycloak_cfg_*`` variables for that realm, ready to drop into group_vars
for the keycloak_cfg role. Secrets and private keys are replaced with Ansible
Vault placeholders — this never prints real secret material.

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
import json
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

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


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(name))


def _vault(var: str) -> str:
    VAULT_VARS.add(var)
    return "{{ %s }}" % var


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
            item["secret"] = _vault("vault_kc_client_secret_%s" % _slug(cid))
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
        if "clientSecret" in cfg:  # OIDC broker secret -> vault
            cfg["clientSecret"] = _vault("vault_kc_idp_%s_client_secret" % _slug(idp["alias"]))
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
                "private_key": _vault("vault_kc_%s_%s_private_key" % (_slug(realm), _slug(name))),
                "certificate": _first(cfg.get("certificate")),
                "active": _first(cfg.get("active"), "true") == "true",
                "enabled": _first(cfg.get("enabled"), "true") == "true",
                "priority": int(_first(cfg.get("priority"), "100")),
                "algorithm": _first(cfg.get("algorithm")),
            },
            "state": "present",
        })

    # --- declarative user profile ---
    for comp in comps.get("org.keycloak.userprofile.UserProfileProvider", []) or []:
        raw = comp.get("config", {}).get("kc.user.profile.config")
        if raw:
            out["keycloak_cfg_user_profiles"].append({
                "parent_id": realm,
                "config": {"kc_user_profile_config": [json.loads(_first(raw))]},
                "state": "present",
            })


def main(path: str) -> None:
    with open(path) as f:
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
    print("#  * Fill the vault_* variables below (kept out of this file).")
    print("#  * Curated field subset: uncommon options and client protocol")
    print("#    mappers are omitted — add them by hand if you need them.")
    if VAULT_VARS:
        print("#")
        print("# Vault variables to define:")
        for v in sorted(VAULT_VARS):
            print("#   %s" % v)
    if NOTES:
        print("#")
        print("# Skipped / needs attention:")
        for n in NOTES:
            print("#   - %s" % n)
    yaml.safe_dump(doc, sys.stdout, sort_keys=False, default_flow_style=False,
                   width=100, allow_unicode=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
