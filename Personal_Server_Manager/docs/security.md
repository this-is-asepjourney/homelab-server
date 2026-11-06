# PSM Security Architecture

Managing Docker on remote servers involves high host privileges. PSM applies defense-in-depth principles across all components:

## 1. Authentication & Sessions
- **Passwords**: Hashed with Argon2id using unique salts.
- **Tokens**: Access tokens expire after short durations.
- **Refresh Tokens**: Revocable and stored as SHA-256 hashes in the database.
- **Session Invalidation**: Password changes immediately revoke all active sessions.

## 2. Authorization (RBAC)
- **Owner**: Full access, server deletion, user management, credentials revocation.
- **Admin**: Create and manage servers, projects, and deployments.
- **Operator**: Trigger builds, start/stop/restart containers, inspect logs.
- **Viewer**: Read-only access to dashboards and monitoring metrics.

## 3. Agent Security
- **No Arbitrary Command Execution**: PSM does not provide arbitrary shell endpoints (`/execute`).
- **Handler Allowlist**: The agent only executes pre-authorized job handlers (`server.ping`, `container.start`, `container.stop`, `container.restart`, `container.remove`, `deployment.git`, `deployment.zip`, `deployment.rollback`).
- **Outbound Only**: Agents connect outbound via WebSocket to the Control Plane. Managed servers never need to expose agent ports to the public internet.
- **Token Rotation**: Every server generates a cryptographically random token (`psm_agent_<token>`) stored as a hash. Tokens can be revoked anytime from the Control Plane.

## 4. Deployment Security
- **Zip Slip Prevention**: All uploaded archives undergo canonical path resolution before extraction, preventing directory traversal (`../`) attacks.
- **Environment Encryption**: All environment variables are encrypted at rest using AES-Fernet with a master encryption key separate from database storage.
- **Masked Secrets**: Secret environment values are masked (`********`) in API responses and frontend views.

## 5. Audit Logging
Every sensitive action (logins, logouts, container state changes, server registration/deletion, deployment triggers, rollbacks, and credential rotations) is permanently recorded in `audit_logs` with timestamps and client IP addresses.

