# PSM Database Design & Schema

The PSM Control Plane uses PostgreSQL managed via SQLAlchemy 2.0 ORM. All entities utilize UUID primary keys and timezone-aware UTC timestamps.

## Entity-Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ PROJECTS : owns
    USERS ||--o{ SERVERS : registers
    USERS ||--o{ AUDIT_LOGS : creates
    SERVERS ||--|| AGENTS : has
    SERVERS ||--o{ PROJECTS : hosts
    SERVERS ||--o{ SERVER_METRICS : reports
    SERVERS ||--o{ CONTAINERS : runs
    PROJECTS ||--o{ DEPLOYMENTS : has
    PROJECTS ||--o{ ENVIRONMENT_VARIABLES : configures
    DEPLOYMENTS ||--o{ DEPLOYMENT_LOGS : generates
    DEPLOYMENTS ||--o{ JOBS : schedules

    USERS {
      uuid id PK
      string name
      string email
      string password_hash
      string role
      string theme
      timestamp created_at
    }
    SERVERS {
      uuid id PK
      uuid owner_id FK
      string name
      string hostname
      string status
      string os_name
      timestamp created_at
    }
    AGENTS {
      uuid id PK
      uuid server_id FK
      string agent_version
      timestamp last_seen
    }
    PROJECTS {
      uuid id PK
      uuid server_id FK
      uuid owner_id FK
      string name
      string framework
      string source_type
      string status
    }
    DEPLOYMENTS {
      uuid id PK
      uuid project_id FK
      string commit_hash
      string image_tag
      string status
      timestamp started_at
      timestamp finished_at
    }
    JOBS {
      uuid id PK
      uuid server_id FK
      uuid deployment_id FK
      string job_type
      string status
      json payload
      timestamp created_at
    }
```

## Core Tables

1. `users`: System operators with Argon2id password hashes and role-based permissions (`owner`, `admin`, `operator`, `viewer`).
2. `user_sessions`: Active user sessions with SHA-256 hashed refresh tokens and IP addresses.
3. `servers`: Managed nodes with hardware architecture, OS, last seen timestamp, and online/offline status.
4. `agents`: Agent authentication credentials and versions.
5. `agent_tokens`: Cryptographically secure registration tokens for onboarding servers.
6. `projects`: Application projects mapped to target servers.
7. `project_sources`: Git repository branches or uploaded ZIP metadata.
8. `deployments`: Release records, version tracking, image tags, duration, and status.
9. `deployment_logs`: Append-only build and execution logs with sequence numbers.
10. `jobs`: Queue table using `FOR UPDATE SKIP LOCKED` for task dispatching.
11. `environment_variables`: Sensitive secrets encrypted with AES-Fernet.
12. `containers`: Inventory of running and stopped Docker containers.
13. `server_metrics`: Snapshots of CPU, memory, disk, network, and uptime.
14. `audit_logs`: Audit trail for security actions, logins, container restarts, and deployments.
