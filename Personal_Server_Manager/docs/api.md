# Personal Server Manager (PSM) API Reference

Base API Path: `/api/v1`

## 1. Authentication (`/auth`)
- `POST /auth/login`: Authenticate with email and password. Returns access and refresh tokens.
- `POST /auth/logout`: Revoke all sessions for current user.
- `POST /auth/refresh`: Issue new access token using refresh token.
- `GET /auth/me`: Get authenticated user profile.
- `POST /auth/change-password`: Update password.

## 2. Server Management (`/servers`)
- `GET /servers`: List all managed servers with dynamic online/offline status and latest metrics.
- `POST /servers`: Register new server. Returns server ID and installation command with secure agent token.
- `GET /servers/{id}`: Detailed server metadata.
- `PATCH /servers/{id}`: Edit server name, hostname, description.
- `DELETE /servers/{id}`: Remove server.
- `GET /servers/{id}/status`: Real-time online/offline status.
- `GET /servers/{id}/metrics`: Recent metric snapshots.
- `POST /servers/{id}/reconnect`: Trigger agent reconnect ping.

## 3. Agent Protocol (`/agents`)
- `POST /agents/register`: Agent registration handshake.
- `POST /agents/heartbeat`: Periodic heartbeat (15s interval).
- `POST /agents/metrics`: Telemetry upload (5s interval).
- `POST /agents/jobs/claim`: Fallback polling queue.
- `POST /agents/jobs/{id}/complete`: Record job result and deployment status.
- `POST /agents/jobs/{id}/logs`: Ingest build/execution logs.
- `WebSocket /agents/connect`: Bi-directional real-time communication channel.

## 4. Docker Management (`/servers/{id}`)
- `GET /servers/{id}/containers`: Inventory of Docker containers.
- `GET /servers/{id}/containers/{cid}`: Container details.
- `POST /servers/{id}/containers/{cid}/start`: Start container.
- `POST /servers/{id}/containers/{cid}/stop`: Stop container.
- `POST /servers/{id}/containers/{cid}/restart`: Restart container.
- `DELETE /servers/{id}/containers/{cid}`: Remove container.
- `GET /servers/{id}/images`: Cached images list.
- `GET /servers/{id}/volumes`: Mounted volumes list.
- `GET /servers/{id}/networks`: Docker bridge and overlay networks.

## 5. Projects (`/projects`)
- `GET /projects`: List configured projects.
- `POST /projects`: Create project.
- `GET /projects/{id}`: Project detail.
- `PATCH /projects/{id}`: Update project source configuration.
- `DELETE /projects/{id}`: Delete project.
- `GET /projects/{id}/environment`: List environment variables (masked).
- `PUT /projects/{id}/environment`: Update and encrypt secrets.
- `GET /projects/{id}/deployments`: Project deployment history.

## 6. Deployments (`/deployments`)
- `POST /deployments/git`: Trigger build from Git repository.
- `POST /deployments/upload-sessions`: Initialize ZIP upload session.
- `POST /deployments/{id}/finalize-upload`: Upload archive and initiate deployment.
- `GET /deployments`: List recent deployments across all projects.
- `GET /deployments/{id}`: Release details.
- `POST /deployments/{id}/rollback`: Rollback to a specific release.
- `GET /deployments/{id}/logs`: Deployment logs.

## 7. WebSockets
- `/ws/servers/{server_id}/metrics`: Live server metrics streaming.
- `/ws/servers/{server_id}/events`: Cluster events.
- `/ws/deployments/{deployment_id}/logs`: Live streaming terminal build logs.

