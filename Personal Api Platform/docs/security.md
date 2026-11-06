# Security Architecture

- **Network Binding**: Bound to `192.168.25.101:8000` in `docker-compose.yml` (LAN-only; no public port forwarding).
- **Zero Plaintext Secrets in Database**: `database_connections`, `integrations`, and `webhook_subscriptions` store environment variable `secret_reference` names only.
- **Structured Log Redaction**: `StructuredJsonFormatter` automatically masks any field or pattern matching `password`, `secret`, `token`, `api_key`, `credential`, or `authorization`.
- **Docker Isolation**: Runs as non-root `appuser`, capped at `256m` RAM and `0.50` CPU, without mounting `/var/run/docker.sock`.
- **Auditability**: Every privileged operation (logins, key issuance/revocation, scope changes, device registration, credential rotation, command creation) is recorded in `audit_logs`.
