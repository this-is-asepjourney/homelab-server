# Authentication & Authorization

PAP implements hybrid authentication supporting human users, backend services, and IoT devices:

1. **User Authentication (`Authorization: Bearer <jwt>`)**:
   - Passwords hashed with Argon2id (`pwdlib[argon2]`).
   - Short-lived JWT access tokens (`15m` default) validated for signature, `iss`, `aud`, and `exp`.
   - Refresh tokens (`7d` default) stored as SHA-256 hashes with strict **refresh-token rotation** and reuse detection.

2. **Machine-to-Machine Authentication (`X-API-Key` or `/api/v1/auth/token`)**:
   - Hashed API keys (`pap_key_...`) issued per `ApiClient` and stored only as SHA-256 hashes.
   - OAuth2 Client Credentials (`POST /api/v1/auth/token`) for backend-to-backend JWT issuance.

3. **IoT Device Credentials (`X-Device-Credential`)**:
   - Per-device credentials (`pap_dev_...`) stored as hashes and rotatable via `POST /api/v1/iot/devices/{id}/credentials/rotate`.
   - Strict anti-spoofing verification ensures authenticated device identity matches the telemetry payload `device_id`.

