-- Inisialisasi Ekstensi TimescaleDB untuk SEGARA
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Schema tabel terdefinisi melalui deklaratif SQLAlchemy saat container API dijalankan.
-- Script ini memastikan ekstensi analitik deret waktu PostgreSQL siap digunakan.
