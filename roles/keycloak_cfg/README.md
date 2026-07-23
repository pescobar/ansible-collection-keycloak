# keycloak_cfg

Configure a **running** Keycloak instance declaratively through its admin REST
API: realms, groups and clients. Part of the `pescobar.keycloak` collection;
pair it with [`keycloak_deploy`](../keycloak_deploy/README.md), which stands the
server up.

This role does **not** deploy Keycloak and does not install anything on a host —
it makes HTTP calls to the Keycloak admin API using the
[`community.general.keycloak_*`](https://docs.ansible.com/ansible/latest/collections/community/general/)
modules.

## Requirements

- A reachable, running Keycloak instance.
- The `community.general` collection on the controller (declared as a collection
  dependency in `galaxy.yml`).
- Admin credentials for a realm with cross-realm admin rights (normally the
  bootstrap admin in the `master` realm).

## How it works

The role authenticates **once** against the admin realm
(`keycloak_cfg_admin_realm`, default `master`) and then applies each declared
resource. Because a `master`-realm admin can manage every realm in the instance,
a single run can configure **multiple realms** — each realm/group/client item
names its own target `realm`. The admin login is separate from the target realm.

## Role variables

See [`defaults/main.yml`](defaults/main.yml) for the full list.

| Variable | Default | Description |
| --- | --- | --- |
| `keycloak_cfg_url` | `https://{{ keycloak_deploy_hostname \| default('localhost:8080') }}` | Base URL of Keycloak (no trailing slash, no `/admin`). |
| `keycloak_cfg_admin_realm` | `master` | Realm to authenticate against. |
| `keycloak_cfg_admin_client_id` | `admin-cli` | Client used for the admin API. |
| `keycloak_cfg_admin_user` | `{{ keycloak_deploy_admin_user \| default('admin') }}` | Admin username. |
| `keycloak_cfg_admin_password` | `{{ keycloak_deploy_admin_password \| default('') }}` | Admin password (use Vault). **Required.** |
| `keycloak_cfg_validate_certs` | `true` | Verify the TLS cert (set `false` for staging/self-signed). |
| `keycloak_cfg_wait_timeout` | `300` | Seconds to wait for Keycloak to answer. |
| `keycloak_cfg_no_log` | `true` | Hide task output (it contains the admin password). Set `false` to debug. |
| `keycloak_cfg_realms` | `[]` | List of realm definitions. |
| `keycloak_cfg_groups` | `[]` | List of group definitions. |
| `keycloak_cfg_clients` | `[]` | List of client definitions. |
| `keycloak_cfg_identity_providers` | `[]` | List of identity provider definitions, each with inline `mappers`. |
| `keycloak_cfg_realm_keys` | `[]` | List of realm key-provider definitions (signing / encryption keys). |
| `keycloak_cfg_user_profiles` | `[]` | List of per-realm declarative User Profile definitions. |

Each item in `keycloak_cfg_realms` / `keycloak_cfg_groups` / `keycloak_cfg_clients`
/ `keycloak_cfg_identity_providers` / `keycloak_cfg_realm_keys` /
`keycloak_cfg_user_profiles` is passed **verbatim** to the matching
`community.general.keycloak_realm` / `keycloak_group` / `keycloak_client` /
`keycloak_identity_provider` / `keycloak_realm_key` / `keycloak_userprofile`
module, so every parameter those modules accept is valid — consult their module
docs for the full option set.

> **Note:** `keycloak_cfg_user_profiles` uses `community.general.keycloak_userprofile`,
> added in **community.general 9.4.0** — this collection requires `>= 9.4.0`.

### Identity providers and mappers

IdP mappers are declared **inline** inside each identity provider via its
`mappers:` list — the role configures the IdP and all its mappers in one
idempotent step. Removing a mapper from the list removes it from Keycloak on the
next run.

```yaml
keycloak_cfg_identity_providers:
  - realm: myapp
    alias: corporate-oidc
    display_name: "Corporate SSO"
    provider_id: oidc
    enabled: true
    config:
      clientId: "keycloak-broker"
      clientSecret: "{{ vault_idp_client_secret }}"
      authorizationUrl: "https://idp.example.com/authorize"
      tokenUrl: "https://idp.example.com/token"
      userInfoUrl: "https://idp.example.com/userinfo"
      defaultScope: "openid email profile"
    mappers:
      - name: email
        identityProviderMapper: oidc-user-attribute-idp-mapper
        config:
          claim: email
          user.attribute: email
          syncMode: INHERIT
      - name: admins-group
        identityProviderMapper: oidc-advanced-group-idp-mapper
        config:
          claims: '[{"key":"groups","value":"admins"}]'
          group: "/administrators"
          syncMode: INHERIT
    state: present
```

### Realm keys

Realm signing/encryption keys are key-provider components attached to a realm.
The **target realm is `parent_id`** (not `realm`), which is separate from the
admin `auth_realm`, so one admin login manages keys across every realm.

```yaml
keycloak_cfg_realm_keys:
  # Imported RSA signing key (private key + cert from Vault)
  - parent_id: myapp
    name: rsa-imported
    provider_id: rsa
    force: true               # imported keys are not drift-detectable (see below)
    config:
      active: true
      enabled: true
      priority: 100
      algorithm: RS256
      private_key: "{{ vault_myapp_realm_private_key }}"
      certificate: "{{ vault_myapp_realm_certificate }}"
    state: present

  # Keycloak-generated fallback key
  - parent_id: myapp
    name: rsa-generated
    provider_id: rsa-generated
    config:
      active: false
      enabled: true
      priority: 90
    state: present
```

- **`provider_id`** selects the key type: `rsa`, `rsa-enc`, `rsa-generated`,
  `rsa-enc-generated`, `hmac-generated`, `aes-generated`, `ecdsa-generated`,
  `java-keystore`.
- **Imported keys aren't drift-detectable:** Keycloak never returns the private
  key, so for `rsa` / `rsa-enc` / `java-keystore` the module can't tell whether
  the stored value changed. Set `force: true` on those items to update
  unconditionally. Generated keys are unaffected.

### Realm user profiles

The declarative **User Profile** (Realm Settings → User profile) is a realm
component, so — like realm keys — the target realm is `parent_id`. There is one
profile per realm; its attributes and groups are declared inline under
`config.kc_user_profile_config`.

```yaml
keycloak_cfg_user_profiles:
  - parent_id: myapp
    config:
      kc_user_profile_config:
        - unmanaged_attribute_policy: DISABLED
          attributes:
            - name: username
              displayName: "${username}"
              permissions:
                view: ["admin", "user"]
                edit: ["admin"]
            - name: email
              displayName: "${email}"
              required:
                roles: ["user"]
              permissions:
                view: ["admin", "user"]
                edit: ["admin", "user"]
            - name: department
              displayName: "Department"
              validations:
                length: { max: 255 }
              permissions:
                view: ["admin", "user"]
                edit: ["admin"]
          groups:
            - name: organization
              displayHeader: "Organization"
    state: present
```

`unmanaged_attribute_policy` controls whether attributes not declared here are
allowed (`DISABLED` = strict; other values permit unmanaged attributes with
varying visibility). Requires `community.general >= 9.4.0`.

## Example: configuring multiple realms

```yaml
- hosts: keycloak
  gather_facts: false
  roles:
    - role: pescobar.keycloak.keycloak_cfg
      vars:
        keycloak_cfg_url: "https://auth.example.com"
        keycloak_cfg_admin_password: "{{ vault_keycloak_admin_password }}"

        keycloak_cfg_realms:
          - realm: shop
            enabled: true
            display_name: "Shop"
            state: present
          - realm: intranet
            enabled: true
            state: present

        keycloak_cfg_groups:
          - realm: intranet
            name: staff
            state: present

        keycloak_cfg_clients:
          - realm: shop
            client_id: shop-frontend
            name: "Shop Frontend"
            public_client: true
            redirect_uris:
              - "https://shop.example.com/*"
            web_origins:
              - "https://shop.example.com"
            state: present
          - realm: intranet
            client_id: intranet-api
            name: "Intranet API"
            public_client: false
            service_accounts_enabled: true
            state: present
```

One admin login, two realms configured in a single run.

## Notes

- **Where it runs:** the tasks only make HTTP calls, so they can run on the
  Keycloak host or be delegated to `localhost` — whichever can reach
  `keycloak_cfg_url`.
- **Idempotency:** the underlying modules are idempotent; re-running only
  reports changes when the desired state differs.
- **Debugging:** set `keycloak_cfg_no_log: false` temporarily to see which item
  failed (this will expose the admin password in output).

## License

MIT
