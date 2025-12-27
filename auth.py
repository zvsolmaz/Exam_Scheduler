# auth.py
from __future__ import annotations
import os
import logging
from typing import Tuple, Optional, Dict, Any

import pyodbc
from passlib.hash import bcrypt
from dotenv import load_dotenv

load_dotenv()

# Passlib'in detay loglarını sustur (konsolda "trapped ... __about__" görünmesin)
logging.getLogger("passlib").setLevel(logging.WARNING)


# ──────────────────────────────────────────────────────────────────────────────
# DB Bağlantı
# ──────────────────────────────────────────────────────────────────────────────

def get_connection() -> pyodbc.Connection:
    """
    .env içindeki MSSQL_CONN bağlantı dizesini kullanarak pyodbc bağlantısı döner.
    Örnek:
      MSSQL_CONN="Driver={ODBC Driver 17 for SQL Server};Server=.;Database=ExamSchedulerDB;Trusted_Connection=yes;"
    """
    conn_str = os.getenv("MSSQL_CONN")
    if not conn_str:
        raise RuntimeError("MSSQL_CONN .env içinde tanımlı değil.")
    return pyodbc.connect(conn_str)


# ──────────────────────────────────────────────────────────────────────────────
# Kimlik Doğrulama
# ──────────────────────────────────────────────────────────────────────────────

def verify_user(email: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    E-posta + şifre doğrulaması (sağlamlaştırılmış):
      - E-posta trim + lower ile karşılaştırılır
      - Hash trim edilir (CHAR padding'e karşı)
      - bcrypt'in 72 bayt sınırı güvenli şekilde ele alınır
      - Hata durumunda anlaşılır sonuç döner

    Dönüş:
      (True, {user_dict}) | (False, None)

    user_dict alanları:
      user_id, email, role_id, department_id, photo (Users.PhotoPath ya da Instructors.PhotoUrl)
    """
    # DB bağlantısı
    try:
        conn = get_connection()
    except Exception as e:
        print(f"[AUTH] DB bağlantı hatası: {e}")
        return False, None

    try:
        cur = conn.cursor()

        # E-posta normalize
        email_norm = (email or "").strip().lower()
        if not email_norm:
            return False, None

        cur.execute(
            """
            SELECT UserID,
                   Email,
                   PasswordHash,
                   RoleID,
                   CAST(NULLIF(RTRIM(LTRIM(CAST(DepartmentID AS NVARCHAR(20)))), '') AS INT) AS DepartmentID,
                   CAST(NULLIF(RTRIM(LTRIM(PhotoPath)), '') AS NVARCHAR(255))         AS PhotoPath
            FROM dbo.Users
            WHERE LOWER(RTRIM(LTRIM(Email))) = ?
            """,
            (email_norm,),
        )
        row = cur.fetchone()
        if not row:
            return False, None

        # Hash'i temizle (boşluk/padding vs.)
        db_hash = (row.PasswordHash or "").strip()
        if not db_hash:
            return False, None

        # 72 bayt sınırı – güvenli şekilde kısalt
        try:
            pw_bytes = (password or "").encode("utf-8")
            if len(pw_bytes) > 72:
                pw_bytes = pw_bytes[:72]
                password = pw_bytes.decode("utf-8", "ignore")
        except Exception:
            password = (password or "")[:72]

        # Doğrulama
        try:
            ok = bcrypt.verify(password, db_hash)
        except Exception as e:
            print(f"[AUTH] bcrypt.verify hata: {e}")
            return False, None

        if not ok:
            return False, None

        # Foto için Users.PhotoPath varsa onu, yoksa Instructors.PhotoUrl'e bak
        user_photo = row.PhotoPath

        if not user_photo:
            try:
                cur.execute(
                    """
                    SELECT TOP 1 CAST(NULLIF(RTRIM(LTRIM(I.PhotoUrl)), '') AS NVARCHAR(255)) AS PhotoUrl
                    FROM dbo.Instructors I
                    WHERE LOWER(RTRIM(LTRIM(I.Email))) = ?
                    """,
                    (email_norm,),
                )
                r2 = cur.fetchone()
                if r2 and getattr(r2, "PhotoUrl", None):
                    user_photo = r2.PhotoUrl
            except Exception as e:
                # Foto opsiyonel olduğu için hatayı bastırıyoruz (loglamak istersen print bırak)
                print(f"[AUTH] Foto yedek sorgu hatası: {e}")

        user = {
            "user_id": row.UserID,
            "email": row.Email,
            "role_id": row.RoleID,
            "department_id": row.DepartmentID,
            "photo": user_photo,
        }
        return True, user

    finally:
        try:
            conn.close()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ──────────────────────────────────────────────────────────────────────────────

def get_department_name(department_id: Optional[int]) -> str:
    """DepartmentID'den bölüm adını döndürür; yoksa '' verir."""
    if not department_id:
        return ""
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT Name FROM dbo.Departments WHERE DepartmentID = ?",
                (int(department_id),),
            )
            r = cur.fetchone()
            return r.Name if r else ""
    except Exception as e:
        print(f"[AUTH] Bölüm adı alınamadı: {e}")
        return ""


def get_coordinator_profile(email: str) -> dict:
    """
    Users + Instructors + Departments üzerinden giriş yapan hocanın profilini döndürür.
    Dönüş:
      {
        "name": str,
        "email": str,
        "department_id": int|None,
        "department_name": str,
        "photo": str|None
      }

    Fotoğraf alanı önceliklendirmesi:
      1) Users.PhotoPath (eğer varsa)
      2) Instructors.PhotoUrl (eğer varsa)
    """
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return {"name": "", "email": "", "department_id": None, "department_name": "", "photo": None}

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1
                   ISNULL(I.Name, '')                                   AS Name,
                   U.Email                                              AS Email,
                   ISNULL(I.DepartmentID, U.DepartmentID)               AS DepartmentID,
                   ISNULL(D.Name, '')                                   AS DeptName,
                   /* Foto önceliği: Users.PhotoPath -> Instructors.PhotoUrl */
                   COALESCE(NULLIF(RTRIM(LTRIM(U.PhotoPath)), ''),
                            NULLIF(RTRIM(LTRIM(I.PhotoUrl)), ''))        AS PhotoFinal
            FROM dbo.Users U
            LEFT JOIN dbo.Instructors I
                   ON LOWER(LTRIM(RTRIM(I.Email))) = LOWER(LTRIM(RTRIM(U.Email)))
            LEFT JOIN dbo.Departments D
                   ON D.DepartmentID = ISNULL(I.DepartmentID, U.DepartmentID)
            WHERE LOWER(LTRIM(RTRIM(U.Email))) = ?
            """,
            (email_norm,),
        )
        r = cur.fetchone()

    if not r:
        return {
            "name": "",
            "email": email_norm,
            "department_id": None,
            "department_name": "",
            "photo": None,
        }

    return {
        "name": r.Name or "",
        "email": r.Email or email_norm,
        "department_id": r.DepartmentID,
        "department_name": r.DeptName or "",
        "photo": r.PhotoFinal,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Profil Fotoğrafı Güncelleme (Kullanışlı Yardımcı)
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_users_photo_column(conn: pyodbc.Connection) -> None:
    """
    Users tablosunda PhotoPath yoksa eklemeyi dener (NVARCHAR(255)).
    Zaten varsa sessizce devam eder.
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            IF COL_LENGTH('dbo.Users', 'PhotoPath') IS NULL
            BEGIN
                ALTER TABLE dbo.Users ADD PhotoPath NVARCHAR(255) NULL;
            END
        """)
        conn.commit()
    except Exception as e:
        # Aynı anda birden çok process bu kontrolü yaparsa benign hatalar olabilir; loglayıp devam.
        print(f"[AUTH] PhotoPath sütunu ekleme uyarı: {e}")


def set_user_photo(email: str, photo_path: str) -> bool:
    
    email_norm = (email or "").strip().lower()
    if not email_norm:
        print("[AUTH] set_user_photo: email boş.")
        return False

    # Dosya yolu var mı? (zorunlu değil ama faydalı uyarı)
    if not photo_path:
        print("[AUTH] set_user_photo: photo_path boş.")
        return False
    if not os.path.exists(photo_path):
        # Yine de veritabanına yazılabilir; sadece uyaralım.
        print(f"[AUTH] Uyarı: Dosya bulunamadı: {photo_path}")

    try:
        with get_connection() as conn:
            _ensure_users_photo_column(conn)
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE dbo.Users
                SET PhotoPath = ?
                WHERE LOWER(RTRIM(LTRIM(Email))) = ?
                """,
                (photo_path, email_norm),
            )
            if cur.rowcount == 0:
                print(f"[AUTH] set_user_photo: Kullanıcı bulunamadı: {email_norm}")
                return False
            conn.commit()
            return True
    except Exception as e:
        print(f"[AUTH] set_user_photo hata: {e}")
        return False
