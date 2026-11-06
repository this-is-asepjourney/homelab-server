# Homelab Deployment Guide

## Prerequisites (Phase 0)

1. Verify Ubuntu Server 24.04.5 LTS LAN address (`192.168.25.101`) and route to database host `100.106.63.90`.
2. Provision `pap_user` and `pap_core` on PostgreSQL (`100.106.63.90:5432`) and `pap_stock_reader` on MySQL (`100.106.63.90:3306`) using `scripts/provision_databases.sql`.
3. Copy `.env.example` to `.env` and populate private credentials.

## Running Migrations & Seeding

```bash
alembic upgrade head
python scripts/seed_pap.py
```

## Starting the Container

```bash
docker compose config
docker compose build
docker compose up -d
docker ps
curl http://192.168.25.101:8000/health
```

