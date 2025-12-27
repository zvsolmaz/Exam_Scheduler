# import_guard_ui.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Optional
import pandas as pd

# ---- Hata modeli -------------------------------------------------------------
@dataclass
class ImportErrorItem:
    sheet: str
    row: int           # Excel satır numarası (1'den başlar; başlık satırı 1 kabul)
    column: str        # Kaynak başlık (Excel’de görünen)
    message: str

# ---- Yardımcılar -------------------------------------------------------------
def _norm(s: str) -> str:
    if s is None: return ""
    s = str(s)
    return (s.strip().lower()
            .replace("ı","i").replace("ş","s").replace("ç","c")
            .replace("ğ","g").replace("ö","o").replace("ü","u")
            .replace(" ", "").replace("-", "").replace(".", ""))

def _excel_row(idx0: int, header_row: int = 1) -> int:
    # pandas index 0 -> Excel’de 2. satır (başlık = 1. satır)
    return idx0 + 1 + header_row

def _build_mapper(df: pd.DataFrame, wanted: Dict[str, set]) -> Dict[str, str]:
    src = { _norm(c): c for c in df.columns }
    mapping = {}
    for key, aliases in wanted.items():
        found = next((src[a] for a in aliases if a in src), None)
        if found: mapping[key] = found
    return mapping

# ---- Başlık alias'ları (sıra bağımsız) --------------------------------------
COURSE_COLUMNS = {
    "course_code": {"derskodu","derskod","kod","coursecode"},
    "course_name": {"dersadi","dersinadi","ders","coursename","name"},
    "lecturer"   : {"hocasi","dersiverenhoca","ogretimelemani","ogrtel","lecturer","instructor"},
    "class"      : {"sinif","class","grade"},
    "type"       : {"tur","dersinturu","zorunlu","secimli","secimlik","type"},
}
STUDENT_COLUMNS = {
    "student_no": {"ogrencino","ogrno","no","numara","studentno","studentnumber"},
    "full_name" : {"adsoyad","adi-soyadi","adi_soyadi","ogrenci","fullname","name"},
    "class"     : {"sinif","class","grade"},
    "course_code": {"derskodu","kod","coursecode"},
}

# ---- Doğrulayıcılar ----------------------------------------------------------
def validate_courses_xlsx(path: str) -> List[ImportErrorItem]:
    """Sadece hataları döner. Hata yoksa []."""
    errors: List[ImportErrorItem] = []
    try:
        book = pd.read_excel(path, sheet_name=None, dtype=str)
    except Exception as e:
        return [ImportErrorItem("—", 0, "Dosya", f"Excel okunamadı: {e}")]

    for sheet, df in book.items():
        if df is None or df.empty:
            continue
        df = df.dropna(how="all")
        df.columns = [str(c).strip() for c in df.columns]
        mapping = _build_mapper(df, COURSE_COLUMNS)

        missing = [k for k in ("course_code","course_name","lecturer") if k not in mapping]
        if missing:
            msg = "Gerekli başlık(lar) yok: " + ", ".join(missing)
            errors.append(ImportErrorItem(sheet, 1, "Başlıklar", msg))
            continue

        for i, rec in df.iterrows():
            rown = _excel_row(i)
            code = str(rec.get(mapping["course_code"], "") or "").strip()
            name = str(rec.get(mapping["course_name"], "") or "").strip()
            lec  = str(rec.get(mapping["lecturer"], "") or "").strip()

            if not code:
                errors.append(ImportErrorItem(sheet, rown, mapping["course_code"], "Ders kodu boş"))
            if not name:
                errors.append(ImportErrorItem(sheet, rown, mapping["course_name"], "Ders adı boş"))
            if not lec:
                errors.append(ImportErrorItem(sheet, rown, mapping["lecturer"], "Öğr. elemanı boş"))
    return errors


def validate_students_xlsx(
    path: str,
    student_no_type: str = "int",
    check_course_codes: bool = False,
    course_code_exists: Optional[Callable[[str], bool]] = None
) -> List[ImportErrorItem]:
    """
    Sadece hataları döner. Hata yoksa [].
    - student_no_type: 'int' (DB'n INT olduğu için default bu)
    - check_course_codes: True ise, her course_code için course_code_exists() ile kontrol eder.
    """
    errors: List[ImportErrorItem] = []
    try:
        book = pd.read_excel(path, sheet_name=None, dtype=str)
    except Exception as e:
        return [ImportErrorItem("—", 0, "Dosya", f"Excel okunamadı: {e}")]

    for sheet, df in book.items():
        if df is None or df.empty:
            continue
        df = df.dropna(how="all")
        df.columns = [str(c).strip() for c in df.columns]
        mapping = _build_mapper(df, STUDENT_COLUMNS)

        miss = [k for k in ("student_no","full_name","course_code") if k not in mapping]
        if miss:
            msg = "Gerekli başlık(lar) yok: " + ", ".join(miss)
            errors.append(ImportErrorItem(sheet, 1, "Başlıklar", msg))
            continue

        for i, rec in df.iterrows():
            rown = _excel_row(i)
            no_raw = rec.get(mapping["student_no"], "")
            name   = rec.get(mapping["full_name"], "")
            ccode  = rec.get(mapping["course_code"], "")

            no_txt = "" if pd.isna(no_raw) else str(no_raw).strip()
            fullname = "" if pd.isna(name) else str(name).strip()
            course_code = "" if pd.isna(ccode) else str(ccode).strip()

            if not no_txt:
                errors.append(ImportErrorItem(sheet, rown, mapping["student_no"], "Öğrenci no boş"))
            else:
                if student_no_type == "int":
                    try:
                        int(str(no_txt).split(".")[0])
                    except Exception:
                        errors.append(ImportErrorItem(sheet, rown, mapping["student_no"], "Öğrenci no INT olmalı"))

            if not fullname:
                errors.append(ImportErrorItem(sheet, rown, mapping["full_name"], "Ad-soyad boş"))

            if not course_code:
                errors.append(ImportErrorItem(sheet, rown, mapping["course_code"], "Ders kodu boş"))
            elif check_course_codes and course_code_exists:
                try:
                    ok = bool(course_code_exists(course_code))
                except Exception as e:
                    ok = True  # kontrol başarısızsa importu bloklamayalım
                if not ok:
                    errors.append(ImportErrorItem(sheet, rown, mapping["course_code"], "Sistemde böyle bir ders kodu yok"))
    return errors

# ---- PyQt6: Hata diyaloğu ---------------------------------------------------
def show_import_errors(parent, errors: List[ImportErrorItem]):
    """
    Basit tablo diyaloğu. Hata yoksa 'Hiç hata yok' diyerek kapanır.
    """
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QLabel
    from PyQt6.QtCore import Qt

    dlg = QDialog(parent)
    dlg.setWindowTitle("Excel Hata Raporu")
    layout = QVBoxLayout(dlg)

    if not errors:
        lbl = QLabel("Hiç hata yok.")
        layout.addWidget(lbl)
        btn = QPushButton("Kapat"); btn.clicked.connect(dlg.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        dlg.exec()
        return

    info = QLabel("Lütfen listelenen satırları Excel’de düzeltip dosyayı yeniden yükleyin.")
    layout.addWidget(info)

    table = QTableWidget(len(errors), 4)
    table.setHorizontalHeaderLabels(["Sayfa", "Satır", "Sütun", "Mesaj"])
    for i, e in enumerate(errors):
        table.setItem(i, 0, QTableWidgetItem(getattr(e, "sheet", "")))
        table.setItem(i, 1, QTableWidgetItem(str(getattr(e, "row", ""))))
        table.setItem(i, 2, QTableWidgetItem(getattr(e, "column", "")))
        table.setItem(i, 3, QTableWidgetItem(getattr(e, "message", "")))
    table.resizeColumnsToContents()
    layout.addWidget(table)

    btn = QPushButton("Kapat")
    btn.clicked.connect(dlg.accept)
    layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    dlg.resize(760, 440)
    dlg.exec()

# ---- Kolay entegrasyon yardımcıları (opsiyonel) -----------------------------
def validate_then_import_courses(
    parent_widget,
    xlsx_path: str,
    importer: Callable[[str, int], Any],
    department_id: int
):
    """
    1) validate_courses_xlsx -> hata varsa göster ve dur
    2) yoksa: mevcut importer'ını çağır (excel_import.py'daki fonksiyonun)
    """
    errs = validate_courses_xlsx(xlsx_path)
    if errs:
        show_import_errors(parent_widget, errs)
        return False
    importer(xlsx_path, department_id)
    return True


def validate_then_import_students(
    parent_widget,
    xlsx_path: str,
    importer: Callable[[str, int], Any],
    department_id: int,
    course_code_exists: Optional[Callable[[str], bool]] = None
):
    """
    1) validate_students_xlsx -> hata varsa göster ve dur
    2) yoksa: mevcut importer'ını çağır (excel_import.py'daki fonksiyonun)
    - course_code_exists(course_code) verilir ise 'kod var mı' kontrolü yapılır.
    """
    errs = validate_students_xlsx(
        xlsx_path,
        student_no_type="int",
        check_course_codes=bool(course_code_exists),
        course_code_exists=course_code_exists
    )
    if errs:
        show_import_errors(parent_widget, errs)
        return False
    importer(xlsx_path, department_id)
    return True
