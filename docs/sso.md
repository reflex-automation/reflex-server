# SSO login

Reflex supports SSO login through the django-ansible-base authenticator
framework. OIDC, Keycloak, GitHub (all variants), Azure AD and Google work out
of the box. LDAP, SAML, RADIUS and TACACS+ plugins exist in DAB but their
python dependencies (python-ldap, python3-saml, xmlsec) are not installed in
the Reflex image; the plugins show as unavailable until they are.

## Bootstrap

After migrations, create the local (password) authenticator once, so existing
username/password login keeps working alongside SSO:

```sh
aap-eda-manage authenticators --initialize
```

## Configuring an authenticator

Authenticators live in the database and are managed via the API (superuser
required), no restart needed:

```sh
curl -s -u admin:PASSWORD -X POST https://<eda-host>/api/eda/v1/authenticators/ \
  -H 'Content-Type: application/json' -d '{
    "name": "Corp SSO",
    "type": "ansible_base.authentication.authenticator_plugins.oidc",
    "enabled": true,
    "create_objects": true,
    "configuration": {
      "OIDC_ENDPOINT": "https://keycloak.example.com/realms/corp",
      "KEY": "<client-id>",
      "SECRET": "<client-secret>"
    }
  }'
```

`GET /api/eda/v1/authenticator_plugins/` lists available plugin types and
their configuration schemas.

The redirect URI to register in the IdP is:

```
https://<eda-host>/api/eda/social/complete/<authenticator-slug>/
```

The slug is returned by the authenticators API. The external hostname must be
in `EDA_ALLOWED_HOSTS` and `EDA_CSRF_TRUSTED_ORIGINS`, and
`EDA_FRONT_END_URL` should be set to the external URL so callback URLs are
built correctly.

## Login flow

`GET /api/eda/v1/ui_auth/` (unauthenticated) returns the enabled
authenticators; the UI login page renders a button per SSO entry pointing at
its `login_url` (`/api/eda/social/login/<slug>/`). On completion the user is
created (if `create_objects` is true) and a session cookie is issued, same as
password login.

Group/organization/team mapping rules are configured per authenticator via
`/api/eda/v1/authenticator_maps/`.
