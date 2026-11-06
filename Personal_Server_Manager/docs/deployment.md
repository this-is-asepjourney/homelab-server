# PSM Deployment Engine

PSM supports two deployment source providers: **Git Repositories** and **ZIP Archives**.

```
User selects repo/branch or uploads ZIP
                 |
                 v
           Control Plane
                 |
          Creates Deployment
                 |
          Dispatches Job
                 |
                 v
               Agent
                 |
         Clone / Fetch or Extract
                 |
         Docker build & Compose
                 |
            Health check
                 |
          Success / Failed
                 |
         Stream logs & update status
```

## 1. Git Deployments
1. User provides a Git repository URL (e.g., `https://github.com/example/app.git`) and branch.
2. Control Plane calculates the release version (e.g., `v1`, `v2`) and dispatches a `deployment.git` job.
3. The server agent fetches the repository, streams build logs to the Control Plane in real-time, builds the container image with a release tag, and runs Docker Compose.
4. On completion, the agent reports success or failure.

## 2. ZIP Upload Deployments
1. User uploads a `.zip` archive via the web interface.
2. The Control Plane verifies the archive structure and protects against Zip Slip attacks.
3. The agent receives the archive in an isolated workspace (`/opt/psm/workspaces/<project-id>`).
4. The agent extracts the source files and triggers the Docker build and Compose execution.

## 3. Rollbacks
1. Every successful deployment records the Docker image tag (e.g., `sample-app:v1`).
2. When the operator triggers a rollback, PSM creates a new deployment version pointing to the previous image tag.
3. The agent restores the containers immediately without re-compiling from source.

