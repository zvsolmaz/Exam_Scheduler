# excel_import.py
from __future__ import annotations
import math, re
from typing import Optional, Tuple, Dict, Any, List, Iterable
import pandas as pd
from PyQt6.QtWidgets import QMessageBox
from db import get_connection

# ----------------- Genel yardımcılar -----------------
ALLOWED_CLASSES = {1, 2, 3, 4, 5, 6, 7}

def _norm(x) -> str:
    if isinstance(x, str):
        return x.strip()
    if x is None:
        return ""
    if isinstance(x, float) and math.isnan(x):
        return ""
    return str(x).strip()

def _to_class_or_none(v) -> Optional[int]:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        m = re.search(r"\d+", s)
        if not m:
            return None
        n = int(m.group(0))
        return n if n in ALLOWED_CLASSES else None
    except Exception:
        return None

def _first_digit_year_from_code(code: str) -> Optional[int]:
    if not code:
        return None
    m = re.search(r"(\d)", str(code))
    if not m:
        return None
    y = int(m.group(1))
    return y if y in ALLOWED_CLASSES else None

# ----------------- Ders Listesi Parser -----------------
def parse_courses_xlsx(xlsx_path: str) -> pd.DataFrame:
    """
    Excel biçimi:
      - 1. sütunda '1. Sınıf', '2. Sınıf' ... başlıklar
      - Altında: DERS KODU | DERSİN ADI | DERSİ VEREN ÖĞR. ELEMANI
      - 'SEÇMELİ DERS'/'SEÇİMLİK DERS' satırı görüldükten SONRA gelenler seçmeli
    """
    xl = pd.read_excel(xlsx_path, sheet_name=None)
    sheet = next(iter(xl.values())).copy()

    rows = []
    current_class: Optional[int] = None
    elective_mode = False

    nrows, ncols = sheet.shape
    for i in range(nrows):
        a = _norm(sheet.iloc[i, 0])
        b = _norm(sheet.iloc[i, 1]) if ncols > 1 else ""
        c = _norm(sheet.iloc[i, 2]) if ncols > 2 else ""

        # Yeni sınıf başlığı
        m = re.match(r"^\s*(\d+)\.\s*S[ıi]n[ıi]f\s*$", a, flags=re.I)
        if m:
            current_class = _to_class_or_none(m.group(1))
            elective_mode = False
            continue

        # Seçmeli/seçimlik anahtarları
        if any(k in a.upper() for k in ("SEÇMEL", "SECIML", "SECİML", "SECMEL", "SEÇİML")):
            elective_mode = True
            continue

        # Tablo başlığı
        if a.upper().startswith("DERS KODU"):
            continue

        if not a and not b and not c:
            continue

        code, name, instr = a, b, c
        if not code or not name:
            continue

        is_elective_by_name = any(k in name.upper() for k in ("SEÇMEL", "SECIML", "SECİML", "SECMEL"))
        rows.append({
            "Code": code,
            "Name": name,
            "InstructorName": instr,
            "ClassYear": current_class,  # burada boş kalabilir, aşağıda dolduracağız
            "IsMandatoryText": "Seçmeli" if (elective_mode or is_elective_by_name) else "Zorunlu",
        })

    df = pd.DataFrame(rows, columns=["Code","Name","InstructorName","ClassYear","IsMandatoryText"])
    if df.empty:
        return df

    # Aynı (Code,ClassYear) kırp
    df = df.drop_duplicates(subset=["Code","ClassYear"], keep="first").reset_index(drop=True)

    # ClassYear boşsa Code'dan türet (BLM105 -> 1, FEF215 -> 2 ...)
    df["ClassYear"] = df.apply(
        lambda r: (r["ClassYear"] if pd.notna(r["ClassYear"]) and r["ClassYear"] in ALLOWED_CLASSES
                   else (_first_digit_year_from_code(r["Code"]) or 1)),
        axis=1
    ).astype(int)

    # Zorunluluk normalize
    def _norm_mand(x: str) -> str:
        s = (x or "").strip().lower()
        if s.startswith("zorunlu"): return "Zorunlu"
        if s.startswith("seç") or s.startswith("sec"): return "Seçmeli"
        return "Zorunlu"  # default
    df["IsMandatoryText"] = df["IsMandatoryText"].apply(_norm_mand)

    return df

# ----------------- Öğrenci Listesi Parser -----------------
def parse_student_enrollments_xlsx(xlsx_path: str) -> pd.DataFrame:
    """
    Beklenen sayfa adı: 'Kayıtlar'
    Kolonlar: Öğrenci No | Ad Soyad | Sınıf | Ders
    Çıktı: StudentNo, FullName, ClassYear, CourseCode
    """
    df = pd.read_excel(xlsx_path, sheet_name="Kayıtlar")
    keymap = {c.strip().lower(): c for c in df.columns}
    need = ["öğrenci no", "ad soyad", "sınıf", "ders"]
    for k in need:
        if k not in keymap:
            raise ValueError(f"Excel'de beklenen kolon yok: {k}")

    out = pd.DataFrame({
        "StudentNo": df[keymap["öğrenci no"]].astype(str).str.strip(),
        "FullName":  df[keymap["ad soyad"]].astype(str).str.strip(),
        "ClassYear": df[keymap["sınıf"]].apply(_to_class_or_none),
        "CourseCode": df[keymap["ders"]].astype(str).str.strip(),
    })
    out = out[(out["StudentNo"]!="") & (out["CourseCode"]!="")]
    # Sınıf boşsa course kodundan yine türetebiliriz; ama burada genelde gerekmez.
    return out

# ----------------- DB Yardımcıları -----------------
def _resolve_instructor_id_by_name(cur, instr_name: str) -> Optional[int]:
    """Instructors.Name ile birebir eşleşme; bulunamazsa None döner."""
    if not instr_name:
        return None
    cur.execute("""
        SELECT TOP 1 InstructorID
        FROM dbo.Instructors
        WHERE LOWER(LTRIM(RTRIM(Name))) = LOWER(LTRIM(RTRIM(?)))
    """, (instr_name,))
    r = cur.fetchone()
    try:
        return int(r.InstructorID) if r else None
    except Exception:
        return int(r[0]) if r else None

# ----------------- DB Yazıcılar (Tam Senkron) -----------------
def _in_clause_placeholders(seq: Iterable[Any]) -> str:
    return ", ".join("?" for _ in seq)

def import_courses(df: pd.DataFrame, department_id: Optional[int]) -> Tuple[int,int,int]:
    """
    TAM SENKRON:
      - Bu bölümde olup Excel'de OLMAYAN dersler (ve ilişkileri) silinir.
      - Excel'dekiler upsert edilir.
    Kolon uyarlaması:
      - InstructorID varsa çözülür, yoksa InstructorName yazılır.
      - IsMandatory/IsElective/IsMandatoryText'ten uygun olanı kullanır.
      - ClassYear her zaman (Excel veya Code) dolu yazılır.
    Döner: (insert_count, update_count, unresolved_instructor_count)
    """
    if df.empty:
        return (0,0,0)

    ins = upd = unresolved = 0
    with get_connection() as conn:
        cur = conn.cursor()

        # Courses kolonları
        cur.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='Courses'
        """)
        cols = {r[0] for r in cur.fetchall()}

        has_instr_id    = "InstructorID"     in cols
        has_instr_name  = "InstructorName"   in cols
        has_is_mand     = "IsMandatory"      in cols
        has_is_elect    = "IsElective"       in cols
        has_is_mand_txt = "IsMandatoryText"  in cols
        has_classyear   = "ClassYear"        in cols

        # 1) Silinecekler: bölümde olup Excel'de olmayan kodlar
        excel_codes = df["Code"].astype(str).str.strip().tolist()
        if excel_codes:
            ph = _in_clause_placeholders(excel_codes)
            cur.execute(f"""
                SELECT CourseID FROM dbo.Courses
                WHERE ISNULL(DepartmentID,-1)=ISNULL(?, -1) AND [Code] NOT IN ({ph})
            """, (department_id, *excel_codes))
        else:
            cur.execute("""
                SELECT CourseID FROM dbo.Courses
                WHERE ISNULL(DepartmentID,-1)=ISNULL(?, -1)
            """, (department_id,))
        to_delete = [int(x[0]) for x in cur.fetchall()]

        if to_delete:
            ids_ph = _in_clause_placeholders(to_delete)

            # SeatAssignments (varsa)
            cur.execute("SELECT 1 WHERE OBJECT_ID('dbo.SeatAssignments','U') IS NOT NULL")
            if cur.fetchone():
                cur.execute(f"""
                    DELETE SA FROM dbo.SeatAssignments AS SA
                    WHERE SA.ExamID IN (SELECT ExamID FROM dbo.Exams WHERE CourseID IN ({ids_ph}))
                """, (*to_delete,))

            # ExamRooms (varsa)
            cur.execute("SELECT 1 WHERE OBJECT_ID('dbo.ExamRooms','U') IS NOT NULL")
            if cur.fetchone():
                cur.execute(f"""
                    DELETE ER FROM dbo.ExamRooms AS ER
                    WHERE ER.ExamID IN (SELECT ExamID FROM dbo.Exams WHERE CourseID IN ({ids_ph}))
                """, (*to_delete,))

            # Exams
            cur.execute(f"DELETE FROM dbo.Exams WHERE CourseID IN ({ids_ph})", (*to_delete,))

            # StudentCourses (varsa)
            cur.execute("SELECT 1 WHERE OBJECT_ID('dbo.StudentCourses','U') IS NOT NULL")
            if cur.fetchone():
                cur.execute(f"DELETE FROM dbo.StudentCourses WHERE CourseID IN ({ids_ph})", (*to_delete,))

            # Courses
            cur.execute(f"DELETE FROM dbo.Courses WHERE CourseID IN ({ids_ph})", (*to_delete,))

        # 2) Upsert
        for _, r in df.iterrows():
            code = _norm(r["Code"])
            name = _norm(r["Name"])
            instr_name = _norm(r.get("InstructorName",""))
            cls = _to_class_or_none(r.get("ClassYear")) or _first_digit_year_from_code(code) or 1
            mand_text = _norm(r.get("IsMandatoryText") or "Zorunlu")
            mand_text = "Seçmeli" if mand_text.lower().startswith(("seç","sec")) else "Zorunlu"
            is_mand_val = 1 if mand_text == "Zorunlu" else 0

            instr_id = None
            if has_instr_id:
                instr_id = _resolve_instructor_id_by_name(cur, instr_name)
                if not instr_id and instr_name:
                    unresolved += 1

            # Var mı?
            cur.execute("""
                SELECT CourseID FROM dbo.Courses
                WHERE [Code]=? AND ISNULL(DepartmentID,-1)=ISNULL(?, -1)
            """, (code, department_id))
            row = cur.fetchone()

            if row:
                # UPDATE
                sets, params = [], []
                sets.append("Name=?"); params.append(name)
                if has_instr_id:
                    sets.append("InstructorID=?"); params.append(instr_id)
                elif has_instr_name:
                    sets.append("InstructorName=?"); params.append(instr_name or None)
                if has_classyear:
                    sets.append("ClassYear=?"); params.append(int(cls))
                if has_is_mand:
                    sets.append("IsMandatory=?"); params.append(is_mand_val)
                elif has_is_elect:
                    sets.append("IsElective=?"); params.append(int(not bool(is_mand_val)))
                elif has_is_mand_txt:
                    sets.append("IsMandatoryText=?"); params.append(mand_text)

                params.append(int(row[0]))
                cur.execute(f"UPDATE dbo.Courses SET {', '.join(sets)} WHERE CourseID=?", params)
                upd += 1
            else:
                # INSERT
                cols_ins = ["DepartmentID","Code","Name"]
                vals_ins = [department_id, code, name]
                if has_instr_id:
                    cols_ins.append("InstructorID");   vals_ins.append(instr_id)
                elif has_instr_name:
                    cols_ins.append("InstructorName"); vals_ins.append(instr_name or None)
                if has_classyear:
                    cols_ins.append("ClassYear");      vals_ins.append(int(cls))
                if has_is_mand:
                    cols_ins.append("IsMandatory");    vals_ins.append(is_mand_val)
                elif has_is_elect:
                    cols_ins.append("IsElective");     vals_ins.append(int(not bool(is_mand_val)))
                elif has_is_mand_txt:
                    cols_ins.append("IsMandatoryText"); vals_ins.append(mand_text)

                placeholders = _in_clause_placeholders(cols_ins)
                cur.execute(f"INSERT INTO dbo.Courses ({', '.join(cols_ins)}) VALUES ({placeholders})", vals_ins)
                ins += 1

        conn.commit()
    return (ins, upd, unresolved)

def import_student_enrollments(df: pd.DataFrame, department_id: Optional[int]) -> Tuple[int,int,int]:
    """
    Students upsert + StudentCourses insert-if-not-exists
    Döner: (student_upsert_count, sc_insert_count, missing_course_count)
    """
    if df.empty:
        return (0,0,0)

    stu_up = sc_ins = miss = 0
    with get_connection() as conn:
        cur = conn.cursor()
        for _, r in df.iterrows():
            sno  = _norm(r["StudentNo"])
            name = _norm(r["FullName"])
            cls  = _to_class_or_none(r.get("ClassYear"))
            ccode = _norm(r["CourseCode"])

            # CourseID: Code + DepartmentID
            cur.execute("""
                SELECT CourseID FROM dbo.Courses
                WHERE [Code]=? AND ISNULL(DepartmentID,-1)=ISNULL(?, -1)
            """, (ccode, department_id))
            cr = cur.fetchone()
            if not cr:
                miss += 1
                continue
            course_id = int(cr[0])

            # Students upsert
            cur.execute("SELECT 1 FROM dbo.Students WHERE StudentNo=?", (sno,))
            if cur.fetchone():
                cur.execute("""
                    UPDATE dbo.Students
                       SET FullName = CASE WHEN ?='' THEN FullName ELSE ? END,
                           ClassYear = ISNULL(?, ClassYear),
                           DepartmentID = ISNULL(?, DepartmentID)
                     WHERE StudentNo=?
                """, (name, name, cls, department_id, sno))
            else:
                cur.execute("""
                    INSERT INTO dbo.Students(StudentNo, DepartmentID, FullName, ClassYear)
                    VALUES(?,?,?,?)
                """, (sno, department_id, name or sno, cls))
                stu_up += 1

            # StudentCourses insert-if-not-exists
            cur.execute("""
                IF NOT EXISTS(SELECT 1 FROM dbo.StudentCourses WHERE StudentNo=? AND CourseID=?)
                    INSERT INTO dbo.StudentCourses(StudentNo, CourseID) VALUES(?,?)
            """, (sno, course_id, sno, course_id))
            sc_ins += 1

        conn.commit()
    return (stu_up, sc_ins, miss)

# ----------------- PyQt bağlayıcıları -----------------
def load_courses_from_excel(xlsx_path: str, department_id: Optional[int], parent=None) -> None:
    try:
        df = parse_courses_xlsx(xlsx_path)
        if df.empty:
            QMessageBox.information(parent, "Ders Yükleme", "Excel'de ders satırı bulunamadı."); return
        ins, upd, unresolved = import_courses(df, department_id)
        msg = f"Tamamlandı.\nYeni ders: {ins}\nGüncellenen: {upd}"
        if unresolved:
            msg += f"\nEşleşmeyen öğretim elemanı: {unresolved} (Instructors.Name ile eşleşmeyenler NULL/boş yazıldı)"
        QMessageBox.information(parent, "Ders Yükleme", msg)
    except Exception as e:
        QMessageBox.critical(parent, "Hata", f"Ders listesi yüklenemedi:\n{e}")

def load_student_list_from_excel(xlsx_path: str, department_id: Optional[int], parent=None) -> None:
    try:
        df = parse_student_enrollments_xlsx(xlsx_path)
        if df.empty:
            QMessageBox.information(parent, "Öğrenci Yükleme", "Excel'de öğrenci verisi bulunamadı."); return
        stu_up, sc_ins, miss = import_student_enrollments(df, department_id)
        msg = f"Tamamlandı.\nÖğrenci (ilk eklenen): {stu_up}\nKayıt (StudentCourses eklenen): {sc_ins}\nEşleşmeyen ders kodu: {miss}"
        if miss:
            msg += "\nNot: Eşleşmeyen dersler için önce 'Ders Listesi Yükle' çalıştırın."
        QMessageBox.information(parent, "Öğrenci Yükleme", msg)
    except Exception as e:
        QMessageBox.critical(parent, "Hata", f"Öğrenci listesi yüklenemedi:\n{e}")
