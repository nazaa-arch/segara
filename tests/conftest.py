"""
Konfigurasi pytest: seluruh tes memakai database SQLite sementara.

Harus diset SEBELUM modul aplikasi diimpor, karena router memanggil init_db()
saat impor. Tanpa ini, tes API menulis data simulasi ke segara.db milik pengguna.
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="segara-test-")
os.environ["SEGARA_DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP_DIR, "test.db").replace("\\", "/")
# Jangan pernah mengirim notifikasi Telegram nyata dari tes
os.environ.pop("SEGARA_TELEGRAM_TOKEN", None)
os.environ.pop("SEGARA_TELEGRAM_CHAT_ID", None)
