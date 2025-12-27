# seat_plan_repo.py
# SQL Server şema: Exams, Courses, ExamRooms, Classrooms, Students, StudentCourses
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Set
from datetime import datetime

from db import get_connection

# ───────────── Veri Modelleri ─────────────
@dataclass(frozen=True)
class Student:
    no: str
    name: str
    class_year: Optional[int] = None

@dataclass
class RoomLayout:
    classroom_id: int
    classroom_name: str
    rows: int
    cols: int
    bench_size: int  # Classrooms.DeskGroupSize (2/3/4)

@dataclass
class SeatPos:
    row: int  # 0-index
    col: int  # 0-index

@dataclass
class Placement:
    student: Student
    classroom_id: int
    classroom_name: str
    pos: SeatPos

@dataclass
class PlanResult:
    exam_id: int                       # ExamID; slot planında -1
    placements: List[Placement]
    warnings: List[str]
    errors: List[str]
    empty_slots: Dict[int, List[SeatPos]]  # classroom_id -> boş slotlar

# ─────────────────────────────────────────────────────────────
# 1) LISTELEME — ExamID bazlı
# ─────────────────────────────────────────────────────────────

def list_exams(department_id: Optional[int] = None) -> List[Tuple[int, str]]:
    """
    ExamID bazlı liste.
    Dönüş: [(ExamID, "CODE – NAME | dd.MM HH:mm | Oda1, Oda2"), ...]
    Oda adları DISTINCT birleştirilir; tek satır.
    """
    conn = get_connection(); cur = conn.cursor()
    if department_id is None:
        cur.execute(r"""
            SELECT
              e.ExamID,
              CONCAT(
                c.Code, N' – ', c.Name, N' | ',
                FORMAT(e.StartDT, 'dd.MM HH:mm'), N' | ',
                ISNULL(
                  STUFF((
                    SELECT N', ' + cl.Name
                    FROM dbo.ExamRooms er2
                    JOIN dbo.Classrooms cl ON cl.ClassroomID = er2.ClassroomID
                    WHERE er2.ExamID = e.ExamID
                    GROUP BY cl.Name                       -- tekilleştir
                    FOR XML PATH(''), TYPE
                  ).value('.','nvarchar(max)'), 1, 2, ''),
                  N'—'
                )
              ) AS Info
            FROM dbo.Exams e
            JOIN dbo.Courses c ON c.CourseID = e.CourseID
            ORDER BY e.StartDT ASC, e.ExamID ASC;
        """)
    else:
        cur.execute(r"""
            SELECT
              e.ExamID,
              CONCAT(
                c.Code, N' – ', c.Name, N' | ',
                FORMAT(e.StartDT, 'dd.MM HH:mm'), N' | ',
                ISNULL(
                  STUFF((
                    SELECT N', ' + cl.Name
                    FROM dbo.ExamRooms er2
                    JOIN dbo.Classrooms cl ON cl.ClassroomID = er2.ClassroomID
                    WHERE er2.ExamID = e.ExamID
                    GROUP BY cl.Name                       -- tekilleştir
                    FOR XML PATH(''), TYPE
                  ).value('.','nvarchar(max)'), 1, 2, ''),
                  N'—'
                )
              ) AS Info
            FROM dbo.Exams e
            JOIN dbo.Courses c ON c.CourseID = e.CourseID
            WHERE c.DepartmentID = ?
            ORDER BY e.StartDT ASC, e.ExamID ASC;
        """, (int(department_id),))
    rows = cur.fetchall()
    conn.close()
    return [(int(r[0]), str(r[1])) for r in rows]

# ─────────────────────────────────────────────────────────────
# 2) LISTELEME — SLOT bazlı (CourseID + StartDT) + bölüm filtresi
# ─────────────────────────────────────────────────────────────
def list_exam_slots(department_id: Optional[int] = None) -> List[Tuple[int, datetime, str]]:
    """
    SLOT bazlı liste (CourseID + StartDT tekilleştirilmiş).
    Dönüş: [(CourseID, StartDT, "CODE – NAME | dd.MM HH:mm | Oda1, Oda2"), ...]
    Oda adları DISTINCT birleştirilir; tek satır.
    """
    conn = get_connection(); cur = conn.cursor()

    if department_id is None:
        cur.execute(r"""
            WITH ExamBase AS (
              SELECT e.CourseID, e.StartDT
              FROM dbo.Exams e
              GROUP BY e.CourseID, e.StartDT      -- slot tekilleşir
            )
            SELECT
              eb.CourseID,
              eb.StartDT,
              CONCAT(
                c.Code, N' – ', c.Name, N' | ',
                FORMAT(eb.StartDT, 'dd.MM HH:mm'), N' | ',
                ISNULL(
                  STUFF((
                    SELECT N', ' + cl.Name
                    FROM dbo.Exams e2
                    JOIN dbo.ExamRooms er2 ON er2.ExamID = e2.ExamID
                    JOIN dbo.Classrooms cl ON cl.ClassroomID = er2.ClassroomID
                    WHERE e2.CourseID = eb.CourseID AND e2.StartDT = eb.StartDT
                    GROUP BY cl.Name                     -- tekilleştir
                    FOR XML PATH(''), TYPE
                  ).value('.','nvarchar(max)'), 1, 2, ''),
                  N'—'
                )
              ) AS Info
            FROM ExamBase eb
            JOIN dbo.Courses c ON c.CourseID = eb.CourseID
            ORDER BY eb.StartDT ASC, eb.CourseID ASC;
        """)
    else:
        cur.execute(r"""
            WITH ExamBase AS (
              SELECT e.CourseID, e.StartDT
              FROM dbo.Exams e
              GROUP BY e.CourseID, e.StartDT
            )
            SELECT
              eb.CourseID,
              eb.StartDT,
              CONCAT(
                c.Code, N' – ', c.Name, N' | ',
                FORMAT(eb.StartDT, 'dd.MM HH:mm'), N' | ',
                ISNULL(
                  STUFF((
                    SELECT N', ' + cl.Name
                    FROM dbo.Exams e2
                    JOIN dbo.ExamRooms er2 ON er2.ExamID = e2.ExamID
                    JOIN dbo.Classrooms cl ON cl.ClassroomID = er2.ClassroomID
                    WHERE e2.CourseID = eb.CourseID AND e2.StartDT = eb.StartDT
                    GROUP BY cl.Name                     -- tekilleştir
                    FOR XML PATH(''), TYPE
                  ).value('.','nvarchar(max)'), 1, 2, ''),
                  N'—'
                )
              ) AS Info
            FROM ExamBase eb
            JOIN dbo.Courses c ON c.CourseID = eb.CourseID
            WHERE c.DepartmentID = ?
            ORDER BY eb.StartDT ASC, eb.CourseID ASC;
        """, (int(department_id),))

    rows = cur.fetchall()
    conn.close()
    # pyodbc: StartDT datetime, Info nvarchar
    return [(int(r[0]), r[1], str(r[2])) for r in rows]

# ─────────────────────────────────────────────────────────────
# 3) PLAN OLUŞTUR — ExamID bazlı
# ─────────────────────────────────────────────────────────────
def build_plan_for_exam(
    exam_id: int,
    forbidden_pairs: Optional[Set[Tuple[str, str]]] = None,   # (StudentNo, StudentNo)
    prefer_front_student_nos: Optional[List[str]] = None
) -> PlanResult:
    """
    1) StudentCourses → öğrencileri, ExamRooms/Classrooms → salon düzenini çeker
    2) Kurallara göre yerleştirir
    3) PlanResult döndürür
    """
    students, rooms, _meta = _fetch_exam_context(exam_id)
    if not rooms:
        return PlanResult(exam_id, [], [], ["Bu sınav için derslik atanmamış."], {})
    if not students:
        return PlanResult(exam_id, [], [], ["Bu sınavı alan öğrenci bulunamadı."], {})

    result = _build_seating_plan(
        students=students,
        rooms=rooms,
        forbidden_pairs={(min(a, b), max(a, b)) for (a, b) in (forbidden_pairs or set())},
        prefer_front=prefer_front_student_nos or []
    )
    result.exam_id = exam_id  # type: ignore
    return result

# ─────────────────────────────────────────────────────────────
# 4) PLAN OLUŞTUR — SLOT bazlı (CourseID + StartDT)
# ─────────────────────────────────────────────────────────────
def build_plan_for_slot(
    course_id: int,
    start_dt: datetime,
    forbidden_pairs: Optional[Set[Tuple[str, str]]] = None,
    prefer_front_student_nos: Optional[List[str]] = None
) -> PlanResult:
    """
    Aynı CourseID + StartDT’ye sahip TÜM ExamID’lerin salonlarını birleştirir ve tek plan üretir.
    """
    students, rooms = _fetch_slot_context(course_id, start_dt)
    if not rooms:
        return PlanResult(-1, [], [], ["Bu ders-slot için derslik atanmamış."], {})
    if not students:
        return PlanResult(-1, [], [], ["Bu dersi alan öğrenci bulunamadı."], {})

    res = _build_seating_plan(
        students=students,
        rooms=rooms,
        forbidden_pairs={(min(a, b), max(a, b)) for (a, b) in (forbidden_pairs or set())},
        prefer_front=prefer_front_student_nos or []
    )
    return res

# ─────────────────────────────────────────────────────────────
# 5) PLAN KAYDET / OKU
# ─────────────────────────────────────────────────────────────
def save_plan(exam_id: int, placements: List[Placement]) -> None:
    """
    SeatPlans tablosuna yazar. Şema:
      SeatPlans(ExamID INT, StudentNo NVARCHAR(32), ClassroomID INT,
                RowIndex INT, ColIndex INT, CreatedAt DATETIME2 DEFAULT SYSUTCDATETIME())
    """
    conn = get_connection(); cur = conn.cursor()

    cur.execute("""
    IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'SeatPlans')
    BEGIN
        CREATE TABLE SeatPlans(
            ExamID      INT          NOT NULL,
            StudentNo   NVARCHAR(32) NOT NULL,
            ClassroomID INT          NOT NULL,
            RowIndex    INT          NOT NULL,
            ColIndex    INT          NOT NULL,
            CreatedAt   DATETIME2    NOT NULL DEFAULT SYSUTCDATETIME()
        );
        CREATE INDEX IX_SeatPlans_ExamID ON SeatPlans(ExamID);
    END
    """)

    cur.execute("DELETE FROM SeatPlans WHERE ExamID = ?", exam_id)
    for p in placements:
        cur.execute("""
            INSERT INTO SeatPlans(ExamID, StudentNo, ClassroomID, RowIndex, ColIndex)
            VALUES(?, ?, ?, ?, ?)
        """, exam_id, p.student.no, p.classroom_id, p.pos.row, p.pos.col)

    conn.commit()
    conn.close()

def fetch_saved_plan(exam_id: int) -> List[Placement]:
    """
    Kaydedilmiş planı Students ve Classrooms ile birlikte döndürür.
    """
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT sp.StudentNo, ISNULL(s.FullName, sp.StudentNo) AS FullName,
               sp.ClassroomID, cl.Name, sp.RowIndex, sp.ColIndex
        FROM SeatPlans sp
        LEFT JOIN Students   s  ON s.StudentNo    = sp.StudentNo
        LEFT JOIN Classrooms cl ON cl.ClassroomID = sp.ClassroomID
        WHERE sp.ExamID = ?
        ORDER BY cl.Name, sp.RowIndex, sp.ColIndex, sp.StudentNo
    """, exam_id)
    rows = cur.fetchall()
    conn.close()

    out: List[Placement] = []
    for r in rows:
        st = Student(no=str(r[0]), name=r[1])
        out.append(Placement(
            student=st,
            classroom_id=int(r[2]),
            classroom_name=r[3] or "",
            pos=SeatPos(int(r[4]), int(r[5]))
        ))
    return out

# ─────────────────────────────────────────────────────────────
# 6) DB Yardımcıları
# ─────────────────────────────────────────────────────────────
def _fetch_exam_context(exam_id: int) -> Tuple[List[Student], List[RoomLayout], dict]:
    """
    - Exams(ExamID, CourseID, ExamType, StartDT, DurationMin, Notes)
    - StudentCourses(StudentNo, CourseID, DepartmentID)
    - Students(StudentNo, FullName, ClassYear)
    - ExamRooms(ExamID, ClassroomID)
    - Classrooms(ClassroomID, Name, Rows, Cols, DeskGroupSize)
    """
    conn = get_connection(); cur = conn.cursor()

    # Exam meta
    cur.execute("""
        SELECT e.CourseID, e.ExamType, e.StartDT, e.DurationMin, e.Notes
        FROM Exams e
        WHERE e.ExamID = ?
    """, exam_id)
    em = cur.fetchone()
    meta: Dict[str, object] = {}
    if em:
        meta = {
            "CourseID": int(em[0]),
            "ExamType": em[1],
            "StartDT": em[2],
            "DurationMin": int(em[3]) if em[3] is not None else None,
            "Notes": em[4],
        }
    course_id = meta.get("CourseID")

    # Öğrenciler (CourseID → StudentCourses → Students)
    cur.execute("""
        SELECT DISTINCT s.StudentNo, s.FullName, s.ClassYear
        FROM StudentCourses sc
        JOIN Students s ON s.StudentNo = sc.StudentNo
        WHERE sc.CourseID = ?
        ORDER BY s.StudentNo
    """, course_id)
    students = [Student(no=str(r[0]), name=r[1], class_year=(int(r[2]) if r[2] is not None else None))
                for r in cur.fetchall()]

    # Sınıflar (sadece bu ExamID)
    cur.execute("""
        SELECT cl.ClassroomID, cl.Name, cl.Rows, cl.Cols, cl.DeskGroupSize
        FROM ExamRooms er
        JOIN Classrooms cl ON cl.ClassroomID = er.ClassroomID
        WHERE er.ExamID = ?
        ORDER BY cl.Name
    """, exam_id)
    rooms = [RoomLayout(
        classroom_id=int(r[0]), classroom_name=r[1],
        rows=int(r[2]), cols=int(r[3]), bench_size=int(r[4])
    ) for r in cur.fetchall()]

    conn.close()
    return students, rooms, meta

def _fetch_slot_context(course_id: int, start_dt: datetime) -> Tuple[List[Student], List[RoomLayout]]:
    """
    Slot = CourseID + StartDT.
    Öğrenciler CourseID'den, salonlar aynı slottaki TÜM ExamID'lerin birleşiminden alınır.
    """
    conn = get_connection(); cur = conn.cursor()

    # Öğrenciler
    cur.execute("""
        SELECT DISTINCT s.StudentNo, s.FullName, s.ClassYear
        FROM StudentCourses sc
        JOIN Students s ON s.StudentNo = sc.StudentNo
        WHERE sc.CourseID = ?
        ORDER BY s.StudentNo
    """, course_id)
    students = [Student(no=str(r[0]), name=r[1], class_year=(int(r[2]) if r[2] is not None else None))
                for r in cur.fetchall()]

    # Salonlar (aynı CourseID+StartDT'ye sahip tüm ExamID'lerden)
    cur.execute("""
        SELECT DISTINCT cl.ClassroomID, cl.Name, cl.Rows, cl.Cols, cl.DeskGroupSize
        FROM Exams e
        JOIN ExamRooms er ON er.ExamID = e.ExamID
        JOIN Classrooms cl ON cl.ClassroomID = er.ClassroomID
        WHERE e.CourseID = ? AND e.StartDT = ?
        ORDER BY cl.Name
    """, course_id, start_dt)
    rooms = [RoomLayout(
        classroom_id=int(r[0]), classroom_name=r[1],
        rows=int(r[2]), cols=int(r[3]), bench_size=int(r[4])
    ) for r in cur.fetchall()]

    conn.close()
    return students, rooms

# ─────────────────────────────────────────────────────────────
# 7) Yerleştirme Çekirdeği  — Bench deseni BOYUNA (rows) uygulanır
# ─────────────────────────────────────────────────────────────
def _mask_for_bench(bench_size: int) -> List[int]:
    """
    4'lü: [1,0,0,1]  → dolu, boş, boş, dolu
    3'lü: [1,0,1]
    2'li: [0,1]      → sağ koltuk dolu
    """
    if bench_size == 4: return [1,0,0,1]
    if bench_size == 3: return [1,0,1]
    if bench_size == 2: return [1,0]
    return [1]

def _iter_slots(layout: RoomLayout):
    """
    Bench maskesine göre öğrenci oturabilir slotları üretir (ön sıra önce).
    ***DİKKAT***: Desen BOYUNA uygulanır → mask[r % mlen].
    """
    mask = _mask_for_bench(layout.bench_size)
    mlen = len(mask)
    for r in range(layout.rows):
        if mask[r % mlen] != 1:
            continue
        for c in range(layout.cols):
            yield SeatPos(r, c)

def _adjacency_groups(layout: RoomLayout) -> List[List[SeatPos]]:
    """
    Aynı bench bloğundaki fiziksel yan-yana pozisyon grupları.
    Desen boyuna uygulandığı için, gruplar **sütun başına**, her mlen satırlık bloktan oluşur.
    Örn. bench=3 ise (satır 0..2), (3..5), (6..8) blokları; her blokta aynı sütundaki
    koltuklar yan-yana (aynı bench) kabul edilir.
    """
    groups: List[List[SeatPos]] = []
    m = _mask_for_bench(layout.bench_size)
    mlen = len(m)

    for c in range(layout.cols):
        for gstart in range(0, layout.rows, mlen):
            g: List[SeatPos] = []
            for i in range(mlen):
                r = gstart + i
                if r >= layout.rows:
                    break
                g.append(SeatPos(r, c))
            if g:
                groups.append(g)
    return groups

def _build_seating_plan(
    students: List[Student],
    rooms: List[RoomLayout],
    forbidden_pairs: Set[Tuple[str, str]],   # StudentNo çifti
    prefer_front: List[str]                  # StudentNo listesi
) -> PlanResult:
    warnings: List[str] = []
    errors: List[str] = []
    placements: List[Placement] = []
    empty_slots: Dict[int, List[SeatPos]] = {}

    # Kullanılabilir slotları hazırla
    room_slots: Dict[int, List[SeatPos]] = {}
    room_by_id: Dict[int, RoomLayout] = {r.classroom_id: r for r in rooms}
    for room in rooms:
        slots = list(_iter_slots(room))
        room_slots[room.classroom_id] = slots.copy()
        empty_slots[room.classroom_id] = slots.copy()

    capacity = sum(len(v) for v in room_slots.values())
    if len(students) > capacity:
        errors.append(f"Toplam kapasite yetersiz! Öğrenci: {len(students)}, kapasite: {capacity}.")
        return PlanResult(-1, placements, warnings, errors, empty_slots)

    # Ön sıra (row=0) ve diğer slotlar
    front_q: List[Tuple[int, SeatPos]] = []
    rest_q:  List[Tuple[int, SeatPos]] = []
    for room in rooms:
        front_q.extend([(room.classroom_id, s) for s in room_slots[room.classroom_id] if s.row == 0])
        rest_q.extend([(room.classroom_id, s) for s in room_slots[room.classroom_id] if s.row != 0])

    placed_nos: Set[str] = set()
    all_nos = {s.no for s in students}

    def take_slot(front_pref: bool) -> Optional[Tuple[int, SeatPos]]:
        if front_pref and front_q:
            return front_q.pop(0)
        if front_q:
            return front_q.pop(0)
        if rest_q:
            return rest_q.pop(0)
        return None

    # 1) Ön sıra isteyenler
    for sno in prefer_front:
        if sno not in all_nos:
            continue
        slot = take_slot(True)
        if not slot:
            warnings.append("Belirtilen öğrenci ön sıraya yerleştirilemedi (kapasite dolu)!")
            break
        room_id, pos = slot
        st = next(s for s in students if s.no == sno)
        placements.append(Placement(st, room_id, room_by_id[room_id].classroom_name, pos))
        placed_nos.add(st.no)
        empty_slots[room_id].remove(pos)

    # 2) Kalan herkes
    for st in students:
        if st.no in placed_nos:
            continue
        slot = take_slot(False)
        if not slot:
            errors.append("Yerleştirme beklenmedik şekilde durdu (slot kalmadı).")
            break
        room_id, pos = slot
        placements.append(Placement(st, room_id, room_by_id[room_id].classroom_name, pos))
        empty_slots[room_id].remove(pos)

    if errors:
        return PlanResult(-1, placements, warnings, errors, empty_slots)

    # 3) Yan yana olmama kontrolü (aynı bench bloğunda)
    by_room: Dict[int, Dict[Tuple[int, int], str]] = {}
    for p in placements:
        by_room.setdefault(p.classroom_id, {})[(p.pos.row, p.pos.col)] = p.student.no

    forbidden_norm = {(min(a, b), max(a, b)) for (a, b) in forbidden_pairs}

    for room in rooms:
        groups = _adjacency_groups(room)
        pos2no = by_room.get(room.classroom_id, {})
        for g in groups:
            seated = [pos2no.get((s.row, s.col)) for s in g]
            seated = [x for x in seated if x is not None]
            if len(seated) < 2:
                continue
            for i in range(len(seated)):
                for j in range(i+1, len(seated)):
                    a, b = seated[i], seated[j]
                    if (min(a, b), max(a, b)) in forbidden_norm:
                        warnings.append("Bu iki öğrenci yan yana oturmayacak şekilde plan oluşturulamadı!")
                        break

    return PlanResult(-1, placements, warnings, errors, empty_slots)
