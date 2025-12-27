from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Set, Tuple, Optional
from datetime import date, time, datetime, timedelta
from collections import defaultdict
from db import get_connection

# ───────────────────── İstisnalar ─────────────────────
class SchedulingError(Exception):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}

class DateRangeError(SchedulingError): ...
class ClassroomNotFoundError(SchedulingError): ...
class CapacityError(SchedulingError): ...
class StudentOverlapError(SchedulingError): ...

# ───────────────────── Veri Modeli ────────────────────
@dataclass
class Constraints:
    department_id: int
    date_start: date
    date_end: date
    exclude_weekdays: Set[int]            # Monday=0 .. Sunday=6
    default_duration_min: int
    buffer_min: int
    global_no_overlap: bool               # True: aynı anda yalnız 1 sınav
    chosen_courses: List[Dict[str, Any]]  # {CourseID, CourseCode, CourseName, ClassYear}
    exam_type: str = "Vize"
    per_course_durations: Optional[Dict[int, int]] = None   # {CourseID: minutes}

    # Zaman çizelgesi
    day_start_hour: int = 9
    day_end_hour: int   = 20
    slot_step_min: int  = 15

    # Gün dağıtımı
    rotate_days_per_year: bool = True     # round-robin başlatma

# ───────────────────── Yardımcılar ────────────────────
def _iter_days(cs: Constraints) -> List[date]:
    d = cs.date_start
    days: List[date] = []
    while d <= cs.date_end:
        if d.weekday() not in cs.exclude_weekdays:
            days.append(d)
        d += timedelta(days=1)
    return days

def _count_students_by_course(dept_id: int, course_ids: List[int]) -> Dict[int, int]:
    if not course_ids:
        return {}
    conn = get_connection(); cur = conn.cursor()
    q = f"""
        SELECT CourseID, COUNT(DISTINCT StudentNo) AS cnt
        FROM dbo.StudentCourses
        WHERE DepartmentID=? AND CourseID IN ({",".join("?"*len(course_ids))})
        GROUP BY CourseID
    """
    cur.execute(q, (dept_id, *course_ids))
    out = {int(r[0]): int(r[1]) for r in cur.fetchall()}
    conn.close()
    return out

def _course_students_map(dept_id: int, course_ids: List[int]) -> Dict[int, Set[int]]:
    if not course_ids:
        return {}
    conn = get_connection(); cur = conn.cursor()
    q = f"""
        SELECT CourseID, StudentNo
        FROM dbo.StudentCourses
        WHERE DepartmentID=? AND CourseID IN ({",".join("?"*len(course_ids))})
    """
    cur.execute(q, (dept_id, *course_ids))
    mp: Dict[int, Set[int]] = defaultdict(set)
    for cid, s in cur.fetchall():
        mp[int(cid)].add(int(s))
    conn.close()
    return mp

def _duration_for_course(cs: Constraints, course_id: int) -> timedelta:
    if cs.per_course_durations and course_id in cs.per_course_durations:
        return timedelta(minutes=int(cs.per_course_durations[course_id]))
    return timedelta(minutes=int(cs.default_duration_min))

def _build_candidate_times(start_hour: int = 9, end_hour: int = 20, step_min: int = 15) -> List[time]:
    """
    start_hour–end_hour (SON BAŞLANGIÇ) arasında her 'step_min' dakikada bir
    aday başlangıç saati üretir. Örn: 09:00, 09:15, ..., 20:00
    """
    times: List[time] = []
    cur = datetime.combine(date.today(), time(start_hour, 0))
    limit = datetime.combine(date.today(), time(end_hour,   0))
    step = timedelta(minutes=step_min)
    while cur <= limit:
        times.append(cur.time().replace(second=0, microsecond=0))
        cur += step
    return times

# ── Gün hedefleri (sınıf başına) — 8 ders / 5 gün → 2-2-2-1-1 gibi ──
def _build_year_day_targets(num_courses_for_year: int, days: List[date]) -> Dict[date, int]:
    """
    Genel hedef: günlere dengeli yay, bir gün max 2 (2'yi aşmaz).
    Strateji:
      1) Mümkünse tüm günlere 1'er ver
      2) Kalanı günlere +1 (max 2)
      3) Hâlâ artarsa yine 2'yi aşmadan döngü
    """
    D = len(days)
    base = [0]*D
    remain = int(num_courses_for_year)

    # 1'ler
    i = 0
    while remain > 0 and i < D:
        base[i] = 1
        remain -= 1
        i += 1

    # +1 vererek 2'ye tamamla
    i = 0
    while remain > 0 and i < D:
        if base[i] < 2:
            base[i] += 1
            remain -= 1
        i += 1

    # Aşırı durum: 2 sınırı korunarak döngü
    while remain > 0:
        for i in range(D):
            if base[i] < 2:
                add = min(2 - base[i], remain)
                base[i] += add
                remain -= add
                if remain == 0:
                    break

    return {day: base[idx] for idx, day in enumerate(days)}

def _ordered_days_by_target(
    days: List[date],
    class_year: int,
    day_year_load: Dict[date, Dict[int, int]],
    targets: Dict[date, int],
    offset: int
) -> List[date]:
    """
    Günleri sırala:
      1) (load - target) sapması küçük olan önde (negatif → hedefin altında)
      2) daha erken gün önde
    Sonra round-robin ofset uygula (bias kırmak için).
    """
    ordered = sorted(
        days,
        key=lambda d: ((day_year_load[d].get(class_year, 0) - targets.get(d, 0)), d)
    )
    if offset and len(ordered) > 1:
        k = offset % len(ordered)
        ordered = ordered[k:] + ordered[:k]
    return ordered

def _choose_slot_with_year_balance(
    days: List[date],
    slots: List[Tuple[date, time]],
    class_year: int,
    day_year_load: Dict[date, Dict[int, int]],
    global_no_overlap: bool,
    slot_students: Dict[Tuple[date, time], Set[int]],
    students: Set[int],
    buffer_td: timedelta,
    last_end_by_student: Dict[int, datetime],
    duration: timedelta,
    targets_for_year: Dict[date, int],
    offset: int
) -> Optional[Tuple[date, time]]:
    """
    1) Önce hedef ≤ günlerde slot ara.
    2) Bulamazsak, hedefi aşsa da en az sapmalı güne yerleştir (kitlenmeyi önlemek için).
    """
    # 1) Hedefi aşmadan dene
    for d in _ordered_days_by_target(days, class_year, day_year_load, targets_for_year, offset):
        if day_year_load[d].get(class_year, 0) >= targets_for_year.get(d, 0):
            continue
        for t in [s for (sd, s) in slots if sd == d]:
            sk = (d, t)
            if global_no_overlap and slot_students[sk]:
                continue
            start_dt = datetime.combine(d, t)
            # öğrenci çakışma/buffer
            conflict = False
            for st in students:
                last = last_end_by_student.get(st)
                if last and (start_dt - last) < buffer_td:
                    conflict = True; break
                if slot_students[sk] and st in slot_students[sk]:
                    conflict = True; break
            if not conflict:
                return (d, t)

    # 2) Hedefi aşarak en az sapmalı güne yerleştir
    for d in _ordered_days_by_target(days, class_year, day_year_load, targets_for_year, offset):
        for t in [s for (sd, s) in slots if sd == d]:
            sk = (d, t)
            if global_no_overlap and slot_students[sk]:
                continue
            start_dt = datetime.combine(d, t)
            conflict = False
            for st in students:
                last = last_end_by_student.get(st)
                if last and (start_dt - last) < buffer_td:
                    conflict = True; break
                if slot_students[sk] and st in slot_students[sk]:
                    conflict = True; break
            if not conflict:
                return (d, t)
    return None

def _collect_student_conflict_examples(
    all_slots: List[Tuple[date, time]],
    duration: timedelta,
    students: Set[int],
    slot_students: Dict[Tuple[date, time], Set[int]],
    last_end_by_student: Dict[int, datetime],
    buffer_td: timedelta,
    slot_courses: Dict[Tuple[date, time], Set[str]],
    last_course_by_student: Dict[int, str],
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Çakışma olduğunda örnek birkaç öğrenciyi açıklar."""
    examples: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for st in students:
        if len(examples) >= limit:
            break
        same_time_courses: Set[str] = set()
        buffer_block = False
        for d, t in all_slots:
            sk = (d, t)
            if st in slot_students.get(sk, set()):
                same_time_courses.update(slot_courses.get(sk, set()))
            last = last_end_by_student.get(st)
            if last:
                start_dt = datetime.combine(d, t)
                if (start_dt - last) < buffer_td:
                    buffer_block = True
        if same_time_courses and st not in seen:
            examples.append({"student": st, "type": "same-time",
                             "conflict_with": sorted(list(same_time_courses))[:5]})
            seen.add(st)
        elif buffer_block and st not in seen:
            examples.append({"student": st, "type": "buffer",
                             "conflict_with": [last_course_by_student.get(st, "")]})
            seen.add(st)
    return examples

# ───────────────── Derslik Yerleştirici ─────────────────
class _RoomAllocator:
    """
    Amaç 1 (birincil): Kullanılan salon SAYISINI minimize etmek (her sınav için).
    Amaç 1'de aynı sayıda salonla çözüm varsa, boş koltuk (waste) en az olanı seç.
    Amaç 2 (ikincil): Program genelinde aynı salonları tekrar kullanmaya eğilim (reuse).
    Amaç 3 (eşitlik bozucu): Toplam kullanım dakikası az olana öncelik (yük dengeleme).
    """
    def __init__(self, rooms_sorted: List[Dict[str, Any]]):
        # beklenen alanlar: ClassroomID, Code, Name, Capacity
        self.rooms = rooms_sorted[:]
        self.used_minutes = defaultdict(int)  # room_id -> toplam kullanım dakikası
        self.used_once: Set[int] = set()      # programda en az 1 kez kullanılan salonlar

    # Reuse önceliği için anahtar: (yeni mi, kullanılan dakika, -kapasite)
    def _key_for_reuse_desc(self, r: Dict[str, Any]) -> Tuple[int, int, int]:
        rid = int(r["ClassroomID"])
        new_used = 0 if rid in self.used_once else 1           # 0: tercih et (zaten kullanılıyor)
        return (new_used, self.used_minutes[rid], -int(r["Capacity"]))  # büyük kapasite öne

    def _sorted_for_reuse_desc(self) -> List[Dict[str, Any]]:
        # büyükten küçüğe, reuse & düşük yük öne
        return sorted(self.rooms, key=self._key_for_reuse_desc)

    def _sorted_by_capacity_desc(self) -> List[Dict[str, Any]]:
        return sorted(self.rooms, key=lambda r: int(r["Capacity"]), reverse=True)

    def _sorted_by_capacity_asc(self) -> List[Dict[str, Any]]:
        return sorted(self.rooms, key=lambda r: int(r["Capacity"]))

    def _score_tuple(self, bundle: List[Dict[str, Any]], need: int) -> Tuple[int, int, int, int]:
        """
        Karşılaştırma için skor: (kardinalite, waste, new_used_total, used_minutes_total)
        Daha küçük daha iyidir.
        """
        caps = [int(r["Capacity"]) for r in bundle]
        total = sum(caps)
        waste = max(0, total - need)
        new_used_total = sum(0 if int(r["ClassroomID"]) in self.used_once else 1 for r in bundle)
        used_minutes_total = sum(self.used_minutes[int(r["ClassroomID"])] for r in bundle)
        return (len(bundle), waste, new_used_total, used_minutes_total)

    def _commit(self, bundle: List[Dict[str, Any]], duration_min: int) -> List[Dict[str, Any]]:
        for r in bundle:
            rid = int(r["ClassroomID"])
            self.used_minutes[rid] += duration_min
            self.used_once.add(rid)
        return bundle

    def _best_single(self, need: int) -> Optional[List[Dict[str, Any]]]:
        # En küçük kapasiteyle ihtiyacı tek başına karşılayan salon
        asc = self._sorted_by_capacity_asc()
        candidates = [r for r in asc if int(r["Capacity"]) >= need]
        if not candidates:
            return None
        # eşitlik: reuse ve düşük yük
        candidates.sort(key=lambda r: (0 if int(r["ClassroomID"]) in self.used_once else 1,
                                       self.used_minutes[int(r["ClassroomID"])],
                                       int(r["Capacity"])))  # küçük kapasite öne
        return [candidates[0]]

    def _best_pair(self, need: int) -> Optional[List[Dict[str, Any]]]:
        # Two-pointer: toplam >= need ve toplam en küçük
        asc = self._sorted_by_capacity_asc()
        n = len(asc)
        i, j = 0, n - 1
        best_sum = None
        best_pair = None
        while i < j:
            s = int(asc[i]["Capacity"]) + int(asc[j]["Capacity"])
            if s >= need:
                # aday
                if best_sum is None or s < best_sum:
                    best_sum = s
                    best_pair = (asc[i], asc[j])
                # daha küçük toplam bulmak için j'yi azalt
                j -= 1
            else:
                i += 1
        if best_pair is None:
            return None
        # reuse / yük eşitlik bozucu
        a, b = best_pair
        pair = [a, b]
        # tek alternatif olmadığı için burada ekstra sıralamaya gerek yok
        return pair

    def _best_triple(self, need: int) -> Optional[List[Dict[str, Any]]]:
        # O(n^3): derslik sayısı genelde küçük olduğundan kabul edilebilir
        asc = self._sorted_by_capacity_asc()
        n = len(asc)
        best_sum = None
        best = None
        for x in range(n):
            for y in range(x+1, n):
                for z in range(y+1, n):
                    s = int(asc[x]["Capacity"]) + int(asc[y]["Capacity"]) + int(asc[z]["Capacity"])
                    if s >= need:
                        if best_sum is None or s < best_sum:
                            best_sum = s
                            best = [asc[x], asc[y], asc[z]]
        return best

    def allocate(self, need: int, duration_min: int) -> List[Dict[str, Any]]:
        """
        0) Tek salon: ihtiyacı karşılayan EN KÜÇÜK kapasite (boşluğu minimize eder).
        1) Çift salon: toplam kapasite en küçük (two-pointer, waste minimize).
        2) Üç salon: toplam kapasite en küçük (waste minimize).
        3) Hâlâ yoksa: salon sayısını minimize etmek için büyükten küçüğe greedy.
        Tüm adaylar eşitse: reuse & düşük yük öne.
        """
        candidates: List[List[Dict[str, Any]]] = []

        s1 = self._best_single(need)
        if s1:
            candidates.append(s1)

        s2 = self._best_pair(need)
        if s2:
            candidates.append(s2)

        s3 = self._best_triple(need)
        if s3:
            candidates.append(s3)

        if candidates:
            # En iyi skoru seç
            candidates.sort(key=lambda bundle: self._score_tuple(bundle, need))
            return self._commit(candidates[0], duration_min)

        # 4) Greedy: en az salon sayısı için büyükten küçüğe doldur
        plan: List[Dict[str, Any]] = []
        remain = int(need)
        for r in self._sorted_by_capacity_desc():
            if remain <= 0:
                break
            cap = int(r["Capacity"])
            if cap <= 0:
                continue
            plan.append(r)
            remain -= cap
            if remain <= 0:
                break
        if remain > 0:
            return []  # kapasite yetmiyor

        # Eşitlik bozucu: reuse & düşük yük öne
        plan.sort(key=lambda r: (0 if int(r["ClassroomID"]) in self.used_once else 1,
                                 self.used_minutes[int(r["ClassroomID"])],
                                 -int(r["Capacity"])))
        return self._commit(plan, duration_min)

# ───────────────── Ana Fonksiyon ──────────────────────
def generate_schedule(cs: Constraints, classrooms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 1) Uygun günler
    days = _iter_days(cs)
    if not days:
        raise DateRangeError("Seçilen tarih aralığı sınavları barındırmıyor!",
                             {"date_start": cs.date_start, "date_end": cs.date_end})

    # 2) Derslik kontrolü
    if not classrooms:
        raise ClassroomNotFoundError("Derslik bulunamadı!", {})

    # 3) Öğrenci sayıları ve mapping
    course_ids = [int(c["CourseID"]) for c in cs.chosen_courses]
    student_counts = _count_students_by_course(cs.department_id, course_ids)
    students_by_course = _course_students_map(cs.department_id, course_ids)

    # 4) Kapasite ön kontrol (kritik)
    total_capacity = sum(int(r["Capacity"]) for r in classrooms)
    for c in cs.chosen_courses:
        cid = int(c["CourseID"]); need = max(1, student_counts.get(cid, 0))
        if need > total_capacity:
            raise CapacityError(
                f"Sınıf kapasitesi yetersiz! (Ders: {c['CourseCode']}, ihtiyaç: {need}, toplam kapasite: {total_capacity})",
                {"course_code": c["CourseCode"], "need": need, "total_capacity": total_capacity}
            )

    # 5) Sıralama (en kalabalık dersler önce)
    courses_sorted = sorted(cs.chosen_courses,
                            key=lambda c: student_counts.get(int(c["CourseID"]), 0),
                            reverse=True)
    rooms_sorted = sorted(classrooms, key=lambda r: int(r["Capacity"]), reverse=True)

    # 6) Slot listesi (kayan zaman çizelgesi)
    daily_times = _build_candidate_times(cs.day_start_hour, cs.day_end_hour, cs.slot_step_min)
    slots: List[Tuple[date, time]] = [(d, t) for d in days for t in daily_times]

    # 7) Takip yapıları
    slot_students: Dict[Tuple[date, time], Set[int]] = defaultdict(set)
    slot_courses:  Dict[Tuple[date, time], Set[str]] = defaultdict(set)
    last_end_by_student: Dict[int, datetime] = {}
    last_course_by_student: Dict[int, str] = {}
    day_year_load: Dict[date, Dict[int, int]] = defaultdict(lambda: defaultdict(int))

    # 8) Salon yerleştirici
    allocator = _RoomAllocator(rooms_sorted)

    # 9) Round-robin ofsetleri
    year_day_offsets: Dict[int, int] = defaultdict(int)

    # 10) Yıl → Gün hedef kotası
    year_course_count: Dict[int, int] = defaultdict(int)
    for c in cs.chosen_courses:
        year_course_count[int(c.get("ClassYear", 0))] += 1

    targets_for_year: Dict[int, Dict[date, int]] = {}
    for y, n in year_course_count.items():
        targets_for_year[y] = _build_year_day_targets(n, days)

    # 11) Yerleştirme
    result: List[Dict[str, Any]] = []
    buffer_td = timedelta(minutes=int(cs.buffer_min))

    for course in courses_sorted:
        cid = int(course["CourseID"])
        year = int(course.get("ClassYear", 0))
        need = max(1, student_counts.get(cid, 0))
        students = students_by_course.get(cid, set())
        duration = _duration_for_course(cs, cid)

        chosen = _choose_slot_with_year_balance(
            days, slots, year, day_year_load, cs.global_no_overlap,
            slot_students, students, buffer_td, last_end_by_student, duration,
            targets_for_year=targets_for_year.get(year, {d: 1 for d in days}),
            offset=year_day_offsets[year] if cs.rotate_days_per_year else 0
        )
        if not chosen:
            # Neden analizi
            cause = None
            for d, t in slots:
                sk = (d, t)
                if cs.global_no_overlap and slot_students[sk]:
                    cause = "global"; break
            if cause != "global":
                start_end_list = [(datetime.combine(d, t), datetime.combine(d, t) + duration) for (d, t) in slots]
                student_block = False
                for (d, t), (start_dt, end_dt) in zip(slots, start_end_list):
                    sk = (d, t)
                    for st in students:
                        last = last_end_by_student.get(st)
                        if last and (start_dt - last) < buffer_td:
                            student_block = True; break
                        if slot_students[sk] and st in slot_students[sk]:
                            student_block = True; break
                    if student_block:
                        break
                cause = "student" if student_block else "none"

            if cause == "student":
                examples = _collect_student_conflict_examples(
                    all_slots=slots, duration=duration, students=students,
                    slot_students=slot_students, last_end_by_student=last_end_by_student,
                    buffer_td=buffer_td, slot_courses=slot_courses, last_course_by_student=last_course_by_student,
                    limit=10
                )
                raise StudentOverlapError(
                    f"Öğrencinin dersleri çakışıyor! (Ders: {course['CourseCode']})",
                    {"course_code": course["CourseCode"], "examples": examples}
                )
            elif cause == "global":
                raise ClassroomNotFoundError(
                    f"Derslik bulunamadı! (Global tek sınav kısıtı nedeniyle uygun boş slot yok — Ders: {course['CourseCode']})",
                    {"course_code": course["CourseCode"], "reason": "global_no_overlap_occupied"}
                )
            else:
                raise ClassroomNotFoundError(
                    f"Derslik bulunamadı! (Uygun slot bulunamadı — Ders: {course['CourseCode']})",
                    {"course_code": course["CourseCode"], "reason": "no_compatible_slot"}
                )

        d, t = chosen
        sk = (d, t)

        # Derslik ataması — ÖNCELİK: (1) en az salon sayısı (2) en az waste (3) reuse (4) düşük yük
        duration_min = int(duration.total_seconds() // 60)
        bundle = allocator.allocate(need, duration_min)
        if not bundle:
            raise ClassroomNotFoundError(
                f"Derslik bulunamadı! (Ders: {course['CourseCode']})",
                {"course_code": course["CourseCode"], "reason": "no_room_bundle"}
            )

        # Kayıt (birden çok salon olabilir)
        part = 1
        start_dt = datetime.combine(d, t)
        end_dt   = start_dt + duration
        slot_courses[sk].add(course["CourseCode"])
        for room in bundle:
            room_label = f"{room['Code']} - {room['Name']}" + (f" (Salon {part})" if part > 1 else "")
            result.append({
                "Date": d,
                "Start": t,
                "End": (datetime.combine(d, t) + duration).time(),
                "DurationMin": duration_min,
                "CourseID": cid,
                "CourseCode": course["CourseCode"],
                "CourseName": course["CourseName"],
                "ClassroomID": int(room["ClassroomID"]),
                "ClassroomName": room_label,
                "ExamType": cs.exam_type,
            })
            part += 1

        # Öğrenci & gün yükü izleme
        slot_students[sk].update(students)
        for st in students:
            last_end_by_student[st] = end_dt
            last_course_by_student[st] = course["CourseCode"]
        day_year_load[d][year] += 1

        # round-robin ilerlet
        if cs.rotate_days_per_year:
            year_day_offsets[year] += 1

    if not result:
        raise SchedulingError("Kısıtlara uygun sınav bulunamadı.", {})

    return result
