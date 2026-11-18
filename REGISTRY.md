# REGISTRY — identifiers. Names only, never values of secrets. Last checked: YYYY-MM-DD

One row per thing. An id is pasted from the tool that printed it, never retyped. Each row says how it was checked.
If an id is also a production or development marker, it must be in `factory.conf` too (PROD_MARKERS / DEV_MARKERS).

## People

| Name | Role | Address | Writes to us about | Style file |
|---|---|---|---|---|
| <contact name> | <role at the client> | <address, also in CLIENT_CONTACT_EMAILS> | <topics> | style/<contact>.md |

## Repos

| Checkout | Remote | Owner | Our rights | Long-lived branches |
|---|---|---|---|---|
| ../<client-app> | <remote url> | client | <push / PR only / admin> | <dev branch>, <prod branch> |

## Accounts and access

| System | Account or tenant | How we log in | Our role | Verified how | Date |
|---|---|---|---|---|---|
| <cloud> production | <id> | <profile name> | <role> | `<identity command>` | YYYY-MM-DD |
| <cloud> development | <id> | <profile name> | <role> | `<identity command>` | YYYY-MM-DD |

## Production resources

| Kind | Name or id | Region | What it does | Verified how |
|---|---|---|---|---|
| <database / queue / job / bucket> | <name> | <region> | <one line> | `<describe command>` |

## Development resources

| Kind | Name or id | Region | What it does | Verified how |
|---|---|---|---|---|

## Secrets (names and locations only)

| Secret name | Where it lives | Used by | Who can rotate it |
|---|---|---|---|

## Where the project's own documents are

| Document | Path or link | Owner |
|---|---|---|
