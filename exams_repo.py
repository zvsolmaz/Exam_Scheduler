# exams_repo.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from db import get_connection

INSERT_SQL = """
INSERT INTO dbo.Exams (CourseID, ExamType, StartDT, DurationMin, Notes)
VALUES (?, ?, ?, ?, ?)
"""

# Yalnızca İLGİLİ BÖLÜM + SINAV TÜRÜ + TARİH ARALIĞI için sil
DELETE_SCOPED_SQL = """
DELETE E
FROM dbo.Exams AS E
INNER JOIN dbo.Courses AS C ON C.CourseID = E.CourseID
WHERE C.DepartmentID = ?
  AND E.ExamType = ?
  AND E.StartDT >= ?
  AND E.StartDT <  ?
"""

def overwrite_and_insert_scoped(
    department_id: int,
    exam_type: str,
    date_start: date,
    date_end: date,
    rows: List[Dict[str, Any]],
) -> int:
    """
    Yalnızca VERİLEN bölüm + sınav türü + tarih aralığındaki kayıtları siler
    ve aynı kapsamda yeni kayıtları yazar. Diğer bölümlerin verilerine dokunmaz.
    """
    if not rows:
        return 0

    # End'i dahil etmek için bir gün sonrasına < koşulu
    end_exclusive = date_end + timedelta(days=1)

    conn = get_connection()
    cur = conn.cursor()

    # Kapsamlı temizleme (sadece bu bölüm / tür / aralık)
    cur.execute(DELETE_SCOPED_SQL, (int(department_id), exam_type, date_start, end_exclusive))

    # Insert
    inserted = 0
    payload: List[Tuple] = []
    for r in rows:
        start_dt = datetime.combine(r["Date"], r["Start"])
        payload.append((
            int(r["CourseID"]),
            r.get("ExamType", exam_type),
            start_dt,
            int(r.get("DurationMin") or 0),
            f"{r['ClassroomName']}",
        ))
    cur.executemany(INSERT_SQL, payload)
    inserted = len(payload)

    conn.commit()
    conn.close()
    return inserted
