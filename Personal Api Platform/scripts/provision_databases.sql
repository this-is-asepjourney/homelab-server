-- =============================================================================
-- Personal API Platform (PAP) — Database Provisioning Reference Script
-- Run only after inspecting existing PostgreSQL ('psm') and MySQL ('stock_umkm').
-- Never commit real passwords to source control.
-- =============================================================================

-- 1. PostgreSQL (100.106.63.90:5432) — Create dedicated role and pap_core database
-- CREATE ROLE pap_user LOGIN PASSWORD 'REPLACE_WITH_NEW_STRONG_SECRET';
-- CREATE DATABASE pap_core OWNER pap_user;

-- 2. MySQL (100.106.63.90:3306) — Create least-privilege reader for Stock UMKM
-- CREATE USER 'pap_stock_reader'@'<PAP_SOURCE_HOST>' IDENTIFIED BY 'REPLACE_WITH_NEW_STRONG_SECRET';
-- GRANT SELECT ON stock_umkm.* TO 'pap_stock_reader'@'<PAP_SOURCE_HOST>';
-- FLUSH PRIVILEGES;

