"""
Script Peluncur Mandiri Sistem SEGARA
Menjalankan server FastAPI dan antarmuka web dashboard terintegrasi.
"""
import os
import sys
import webbrowser
import uvicorn


def main():
    print("=" * 65)
    print(" 🪸  SEGARA - Sistem Early-warning Gangguan termal Atas terumbu kaRAng")
    print("=" * 65)
    print(" • Backend API:      http://127.0.0.1:8000/api")
    print(" • Dokumentasi API:  http://127.0.0.1:8000/docs")
    print(" • Web Dashboard:    http://127.0.0.1:8000/")
    print(" • Database:         SQLite (segara.db)")
    print(" • 5 Stasiun Laut:   Bunaken, Raja Ampat, Wakatobi, Karimunjawa, Komodo")
    print("=" * 65)
    print("Menjalankan server... Tekan CTRL+C untuk menghentikan.")
    print("=" * 65)

    # Buka peramban secara otomatis setelah server siap
    try:
        webbrowser.open("http://127.0.0.1:8000/")
    except Exception:
        pass

    # Jalankan Uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
