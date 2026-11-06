import os
import time
import subprocess
from typing import Dict, Any, Callable
from apps.agent.app.docker.client import docker_manager
from apps.agent.app.deployment.builder import DeploymentEngine
from apps.agent.app.core.config import agent_settings

# Allowlist of executable handlers
ALLOWED_JOB_TYPES = {
    "server.ping",
    "container.start",
    "container.stop",
    "container.restart",
    "container.remove",
    "system.prune",
    "deployment.git",
    "deployment.zip",
    "deployment.compose",
    "deployment.rollback",
}

def handle_server_ping(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    log_cb("info", "Server ping received. Agent is healthy and responsive.")
    return {"status": "pong", "time": time.time()}

def handle_container_start(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    cid = payload.get("container_id")
    if not cid:
        raise ValueError("container_id is required")
    log_cb("info", f"Starting container {cid}...")
    success = docker_manager.start_container(cid)
    return {"success": success}

def handle_container_stop(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    cid = payload.get("container_id")
    if not cid:
        raise ValueError("container_id is required")
    log_cb("info", f"Stopping container {cid}...")
    success = docker_manager.stop_container(cid)
    return {"success": success}

def handle_container_restart(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    cid = payload.get("container_id")
    if not cid:
        raise ValueError("container_id is required")
    log_cb("info", f"Restarting container {cid}...")
    success = docker_manager.restart_container(cid)
    return {"success": success}

def handle_container_remove(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    cid = payload.get("container_id")
    force = payload.get("force", False)
    if not cid:
        raise ValueError("container_id is required")
    log_cb("info", f"Removing container {cid} (force={force})...")
    success = docker_manager.remove_container(cid, force=force)
    return {"success": success}

def handle_system_prune(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    all_images = payload.get("all_images", False)
    log_cb("info", f"Running Docker system prune (all_images={all_images})...")
    res = docker_manager.prune_system(all_images=all_images)
    log_cb("info", f"Prune completed. Output: {res.get('output', 'Success')}")
    return res

def handle_deployment_git(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    project_id = payload.get("project_id")
    project_name = payload.get("project_name", f"proj-{project_id}")
    repo_url = payload.get("repository_url")
    branch = payload.get("branch", "main")
    commit_hash = payload.get("commit_hash")
    compose_path = payload.get("compose_path", "docker-compose.yml")
    dockerfile_path = payload.get("dockerfile_path", "Dockerfile")
    port_mappings = payload.get("port_mappings", "3000:3000")
    image_tag = payload.get("image_tag", f"{project_name}:latest")
    env_vars = payload.get("environment_variables", {})
    db_config = payload.get("database_config", {})

    target_dir = os.path.join(agent_settings.WORKSPACE_DIR, project_id)
    log_cb("info", f"[Deploy] Memulai deployment Git untuk project '{project_name}'...")

    # 1. Clone or pull repository
    cloned = DeploymentEngine.clone_or_pull_git(repo_url, branch, target_dir, log_cb, commit_hash=commit_hash)
    if not cloned:
        raise RuntimeError("Gagal clone atau pull git repository")

    # 2. Ensure PostgreSQL database exists & auto-connect environment secrets
    merged_env = DeploymentEngine.ensure_project_postgres_db(project_name, env_vars, db_config, log_cb)
    log_cb("info", f"[Deploy] Menyiapkan {len(merged_env)} variabel environment ke .env...")
    DeploymentEngine.write_env_file(target_dir, merged_env)

    # 3. Determine target container port from port_mappings
    _, _, container_port = DeploymentEngine.parse_port_mappings(
        explicit_mappings=port_mappings,
        full_df_path=os.path.join(target_dir, dockerfile_path),
        workspace_dir=target_dir,
        log_callback=lambda *_: None
    )

    # 4. Check for Compose vs Dockerfile (auto-generating if missing)
    resolved_path = DeploymentEngine.ensure_dockerfile_or_generate(
        workspace_dir=target_dir,
        dockerfile_path=dockerfile_path,
        compose_path=compose_path,
        container_port=container_port,
        log_callback=log_cb
    )

    deployed = False
    if resolved_path == compose_path or resolved_path.endswith(".yml") or resolved_path.endswith(".yaml"):
        log_cb("info", f"[Deploy] Menjalankan Docker Compose stack dari '{resolved_path}'...")
        deployed = DeploymentEngine.build_and_deploy_compose(target_dir, resolved_path, log_cb)
    else:
        log_cb("info", f"[Deploy] Membangun image dan menjalankan container Docker dari '{resolved_path}'...")
        deployed = DeploymentEngine.build_and_run_dockerfile(
            workspace_dir=target_dir,
            dockerfile_path=resolved_path,
            image_tag=image_tag,
            container_name=project_name,
            log_callback=log_cb,
            port_mappings=port_mappings
        )

    if not deployed:
        raise RuntimeError("Proses build atau peluncuran container gagal. Lihat log deployment.")

    log_cb("info", f"[Deploy] Project '{project_name}' berhasil di-deploy ke Docker!")
    return {"success": True, "workspace": target_dir, "image_tag": image_tag}

def handle_deployment_zip(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    project_id = payload.get("project_id")
    project_name = payload.get("project_name", f"proj-{project_id}")
    zip_path = payload.get("zip_path")
    image_tag = payload.get("image_tag", f"{project_name}:latest")
    dockerfile_path = payload.get("dockerfile_path", "Dockerfile")
    compose_path = payload.get("compose_path", "docker-compose.yml")
    port_mappings = payload.get("port_mappings", "3000:3000")
    env_vars = payload.get("environment_variables", {})
    db_config = payload.get("database_config", {})

    target_dir = os.path.join(agent_settings.WORKSPACE_DIR, project_id)

    log_cb("info", f"[Deploy] Mengekstrak paket ZIP ke workspace {target_dir}...")
    DeploymentEngine.safe_extract_zip(zip_path, target_dir)

    merged_env = DeploymentEngine.ensure_project_postgres_db(project_name, env_vars, db_config, log_cb)
    log_cb("info", f"[Deploy] Menyiapkan {len(merged_env)} variabel environment ke .env...")
    DeploymentEngine.write_env_file(target_dir, merged_env)

    # Determine target container port from port_mappings
    _, _, container_port = DeploymentEngine.parse_port_mappings(
        explicit_mappings=port_mappings,
        full_df_path=os.path.join(target_dir, dockerfile_path),
        workspace_dir=target_dir,
        log_callback=lambda *_: None
    )

    resolved_path = DeploymentEngine.ensure_dockerfile_or_generate(
        workspace_dir=target_dir,
        dockerfile_path=dockerfile_path,
        compose_path=compose_path,
        container_port=container_port,
        log_callback=log_cb
    )

    deployed = False
    if resolved_path == compose_path or resolved_path.endswith(".yml") or resolved_path.endswith(".yaml"):
        log_cb("info", f"[Deploy] Menjalankan Docker Compose stack dari '{resolved_path}'...")
        deployed = DeploymentEngine.build_and_deploy_compose(target_dir, resolved_path, log_cb)
    else:
        log_cb("info", f"[Deploy] Membangun image Docker dan meluncurkan container...")
        deployed = DeploymentEngine.build_and_run_dockerfile(
            workspace_dir=target_dir,
            dockerfile_path=resolved_path,
            image_tag=image_tag,
            container_name=project_name,
            log_callback=log_cb,
            port_mappings=port_mappings
        )

    if not deployed:
        raise RuntimeError("Proses build atau peluncuran container ZIP gagal")

    log_cb("info", f"[Deploy] Project '{project_name}' ZIP berhasil di-deploy ke Docker!")
    return {"success": True, "workspace": target_dir}

def handle_deployment_rollback(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    target_image = payload.get("target_image_tag")
    project_name = payload.get("project_name", "app")
    log_cb("warning", f"[Rollback] Initiating rollback to image: {target_image}...")
    sanitized_name = project_name.lower().replace(" ", "-")

    # Stop current container and run previous image tag
    subprocess.run(["docker", "stop", sanitized_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "rm", "-f", sanitized_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = ["docker", "run", "-d", "--restart", "unless-stopped", "--name", sanitized_name, target_image]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log_cb("info", proc.stdout.strip() if proc.stdout else "Container restarted with previous release image.")
    return {"success": True, "restored_image": target_image}

def handle_deployment_compose(payload: Dict[str, Any], log_cb: Callable) -> Dict[str, Any]:
    project_id = payload.get("project_id")
    project_name = payload.get("project_name", f"proj-{project_id}")
    compose_content = payload.get("compose_content", "")
    env_vars = payload.get("environment_variables", {})

    target_dir = os.path.join(agent_settings.WORKSPACE_DIR, project_id)
    os.makedirs(target_dir, exist_ok=True)

    log_cb("info", f"[Deploy] Writing docker-compose.yml for template project '{project_name}'...")
    compose_path = os.path.join(target_dir, "docker-compose.yml")
    with open(compose_path, "w", encoding="utf-8") as f:
        f.write(compose_content)

    if env_vars:
        log_cb("info", f"[Deploy] Injecting {len(env_vars)} environment configuration variables...")
        DeploymentEngine.write_env_file(target_dir, env_vars)

    log_cb("info", f"[Deploy] Starting containers via docker compose up -d...")
    deployed = DeploymentEngine.build_and_deploy_compose(target_dir, "docker-compose.yml", log_cb)
    if not deployed:
        raise RuntimeError(f"Failed to deploy compose stack '{project_name}'")

    log_cb("info", f"[Deploy] Template stack '{project_name}' successfully deployed and operational!")
    return {"success": True, "workspace": target_dir}

HANDLERS = {
    "server.ping": handle_server_ping,
    "container.start": handle_container_start,
    "container.stop": handle_container_stop,
    "container.restart": handle_container_restart,
    "container.remove": handle_container_remove,
    "system.prune": handle_system_prune,
    "deployment.git": handle_deployment_git,
    "deployment.zip": handle_deployment_zip,
    "deployment.compose": handle_deployment_compose,
    "deployment.rollback": handle_deployment_rollback,
}
