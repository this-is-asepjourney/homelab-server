import time
import httpx
from typing import Dict, Any, List
from apps.agent.app.jobs.handlers import HANDLERS, ALLOWED_JOB_TYPES
from apps.agent.app.core.config import agent_settings

class JobExecutor:
    @staticmethod
    def execute_job(job_id: str, job_type: str, server_id: str, payload: Dict[str, Any]):
        if job_type not in ALLOWED_JOB_TYPES or job_type not in HANDLERS:
            raise ValueError(f"Job type '{job_type}' is not allowed or not recognized")

        start_time = time.time()
        log_sequence = 0
        buffered_logs: List[Dict[str, Any]] = []

        def log_callback(level: str, message: str):
            nonlocal log_sequence
            log_sequence += 1
            entry = {"sequence": log_sequence, "level": level, "message": message}
            buffered_logs.append(entry)
            # Batch send every 5 logs or immediately if needed
            if len(buffered_logs) >= 5:
                JobExecutor.send_logs(job_id, list(buffered_logs))
                buffered_logs.clear()

        handler = HANDLERS[job_type]
        status = "success"
        err_msg = None
        output = {}

        try:
            output = handler(payload, log_callback)
        except Exception as e:
            status = "failed"
            err_msg = str(e)
            log_callback("error", f"Job failed: {err_msg}")

        # Flush remaining logs
        if buffered_logs:
            JobExecutor.send_logs(job_id, buffered_logs)

        duration = int(time.time() - start_time)
        JobExecutor.report_complete(job_id, status, output, err_msg, duration)

    @staticmethod
    def send_logs(job_id: str, logs: List[Dict[str, Any]]):
        url = f"{agent_settings.CONTROL_PLANE_URL}/api/v1/agents/jobs/{job_id}/logs"
        headers = {
            "X-Agent-Token": agent_settings.AGENT_TOKEN,
            "X-Server-Id": agent_settings.SERVER_ID
        }
        try:
            with httpx.Client(timeout=5) as client:
                client.post(url, json={"logs": logs}, headers=headers)
        except Exception:
            pass

    @staticmethod
    def report_complete(job_id: str, status: str, output: Dict[str, Any], error_message: str, duration: int):
        url = f"{agent_settings.CONTROL_PLANE_URL}/api/v1/agents/jobs/{job_id}/complete"
        headers = {
            "X-Agent-Token": agent_settings.AGENT_TOKEN,
            "X-Server-Id": agent_settings.SERVER_ID
        }
        try:
            with httpx.Client(timeout=5) as client:
                client.post(
                    url,
                    json={
                        "status": status,
                        "output": output,
                        "error_message": error_message,
                        "duration_seconds": duration
                    },
                    headers=headers
                )
        except Exception:
            pass

