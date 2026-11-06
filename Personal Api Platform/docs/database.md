# Hybrid Database Strategy

## 1. Core Database (`pap_core`)

PAP stores its own identity, project registry, API key hashes, device registry, webhooks, and audit logs in a dedicated PostgreSQL database named `pap_core` owned by `pap_user`.

- **Protection of `psm`**: PAP validates `PAP_DATABASE_URL` and refuses to run migrations or runtime operations against `psm` unless `ALLOW_PSM_AS_PAP_CORE=true` is explicitly set.

## 2. Project Databases (`stock_umkm`)

- Each project retains ownership of its business schema.
- MySQL integration uses a restricted `pap_stock_reader` account (`SELECT` only). Runtime use of `root` is forbidden.
- Database connection records store only an uppercase environment variable `secret_reference` (never plaintext passwords).
- Schema metadata inspection (`GET /api/v1/database/sources/{id}/schema`) is validated against a per-connection `allowed_tables` allowlist.
- Unrestricted SQL execution (`/api/v1/database/query`) is explicitly blocked.

