#!/usr/bin/env python3
"""
PSM Dockerfile & Context Setup Assistant (Professional Deployer CLI)
Auto-detects project stack and generates a multi-stage production Dockerfile and .dockerignore
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PSM_ROOT = SCRIPT_DIR.parents[1]
if str(PSM_ROOT) not in sys.path:
    sys.path.insert(0, str(PSM_ROOT))

from apps.agent.app.deployment.dockerfile_generator import (
    detect_project_stack,
    generate_dockerfile,
    generate_dockerignore,
    ensure_dockerfile_and_ignore,
    get_available_templates,
)


def main():
    parser = argparse.ArgumentParser(description="PSM Professional Dockerfile Setup Assistant")
    parser.add_argument("path", nargs="?", default=".", help="Project workspace path (default: current directory)")
    parser.add_argument("--framework", "-f", default="auto", help="Force specific framework (nextjs, vite, node, fastapi, django, flask, laravel, go, static)")
    parser.add_argument("--port", "-p", type=int, default=None, help="Container target port (defaults to stack standard)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing Dockerfile if already present")
    parser.add_argument("--preview", action="store_true", help="Print preview without writing files")

    args = parser.parse_args()
    target_dir = os.path.abspath(args.path)

    if not os.path.exists(target_dir):
        print(f"[Error] Directory not found: {target_dir}")
        sys.exit(1)

    print("==================================================================")
    print("      PSM PROFESSIONAL DOCKERFILE & SETUP ASSISTANT")
    print("==================================================================")
    print(f"Target Directory: {target_dir}")

    stack = detect_project_stack(target_dir)
    print(f"\n[1] Stack Detection:")
    print(f"    - Detected Stack    : {stack.get('detected_stack')}")
    print(f"    - Framework         : {stack.get('framework')}")
    print(f"    - Package Manager   : {stack.get('package_manager')}")
    print(f"    - Recommended Port  : {stack.get('recommended_port')}")

    tmpl_key = stack.get("template_key", "nextjs")
    if args.framework and args.framework != "auto":
        fw_clean = args.framework.lower()
        if "next" in fw_clean:
            tmpl_key = "nextjs"
        elif "vite" in fw_clean or "react" in fw_clean or "vue" in fw_clean:
            tmpl_key = "vite_spa"
        elif "fastapi" in fw_clean:
            tmpl_key = "fastapi"
        elif "django" in fw_clean:
            tmpl_key = "django"
        elif "flask" in fw_clean:
            tmpl_key = "flask"
        elif "laravel" in fw_clean or "php" in fw_clean:
            tmpl_key = "laravel"
        elif "go" in fw_clean:
            tmpl_key = "golang"
        elif "static" in fw_clean or "html" in fw_clean:
            tmpl_key = "static_html"
        else:
            tmpl_key = "node_backend"

    port = args.port or stack.get("recommended_port", 3000)
    df_content = generate_dockerfile(tmpl_key, port=port)
    di_content = generate_dockerignore()

    if args.preview:
        print("\n[Preview: Dockerfile]")
        print("------------------------------------------------------------------")
        print(df_content)
        print("------------------------------------------------------------------")
        print("\n[Preview: .dockerignore]")
        print("------------------------------------------------------------------")
        print(di_content)
        return

    df_path = os.path.join(target_dir, "Dockerfile")
    di_path = os.path.join(target_dir, ".dockerignore")

    wrote_df = False
    if not os.path.exists(df_path) or args.overwrite:
        with open(df_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(df_content)
        wrote_df = True
        print(f"\n[2] Dockerfile created at: {df_path}")
    else:
        print(f"\n[2] Dockerfile already exists (use --overwrite to replace)")

    wrote_di = False
    if not os.path.exists(di_path) or args.overwrite:
        with open(di_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(di_content)
        wrote_di = True
        print(f"[3] .dockerignore created at: {di_path}")
    else:
        print(f"[3] .dockerignore already exists (use --overwrite to replace)")

    print("\n[Summary] Setup complete! Project is now ready for professional PaaS & PSM deployment.")


if __name__ == "__main__":
    main()

