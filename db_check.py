# dp_check.py
import os
import pyodbc
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# .env dosyasını yükle
# -----------------------------------------------------------------------------
load_dotenv()

# -----------------------------------------------------------------------------
# Bağlantı dizesini oku
# -----------------------------------------------------------------------------
conn_str = os.getenv("MSSQL_CONN")

if not conn_str:
    print("❌ HATA: MSSQL_CONN değeri bulunamadı. Lütfen proje kökünde bir '.env' dosyası oluşturun.")
    print("Örnek:")
    print("MSSQL_CONN=Driver={ODBC Driver 17 for SQL Server};Server=localhost;Database=ExamSchedulerDB;Trusted_Connection=Yes;Encrypt=yes;TrustServerCertificate=yes;")
    raise SystemExit(1)

print("🔌 Bağlantı dizesi yüklendi.\n")

# -----------------------------------------------------------------------------
# SQL Server bağlantı testi
# -----------------------------------------------------------------------------
try:
    with pyodbc.connect(conn_str) as conn:
        cur = conn.cursor()
        cur.execute("SELECT DB_NAME();")
        db_name = cur.fetchone()[0]
        print(f"✅ Başarılı bağlantı! Veritabanı: {db_name}")
except pyodbc.Error as e:
    print("❌ Veritabanı bağlantı hatası!")
    print("Hata mesajı:", e)
except Exception as e:
    print("❌ Beklenmeyen hata:", e)
