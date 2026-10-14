"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), tz_aware=True)
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))

@asynccontextmanager
async def lifespan(app):
   db.employees.create_index("emp_code", unique=True)
   db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
   yield

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def to_dt(ms: int) -> datetime:
    # milliseconds from the client -> a datetime, cut to whole seconds (rule R1)
    return datetime.fromtimestamp(ms // 1000, tz=timezone.utc)


def to_ms(dt):
    # a datetime from the database -> milliseconds for the client
    if dt is None:
        return None
    return (dt.astimezone(timezone.utc) - EPOCH) // timedelta(milliseconds=1)


def attendance_date(punch_in: datetime, shift_start: str, shift_end: str) -> str:
    # R1: which calendar day (in IST) does this punch-in belong to?
    local = punch_in.astimezone(IST)
    day = local.date()
    if shift_end <= shift_start and local.strftime("%H:%M") < shift_end:
        day = day - timedelta(days=1)   # overnight shift: belongs to the day before
    return day.isoformat()


def compute_late_minutes(punch_in: datetime, shift_start: str, date_str: str) -> int:
    # R2: late only if MORE than 10:00 after shift start
    h, m = map(int, shift_start.split(":"))
    start = datetime.fromisoformat(date_str).replace(hour=h, minute=m, tzinfo=IST)
    seconds = int((punch_in - start).total_seconds())
    return seconds // 60 if seconds > 600 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    # R4: seconds / 3600, rounded to 2 decimals, half-up
    seconds = int((punch_out - punch_in).total_seconds())
    hours = Decimal(seconds) / Decimal(3600)
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_overtime(punch_out: datetime, shift_start: str, shift_end: str, date_str: str) -> int:
    # R3: whole minutes after shift end, counted only if at least 30
    h, m = map(int, shift_end.split(":"))
    end = datetime.fromisoformat(date_str).replace(hour=h, minute=m, tzinfo=IST)
    if shift_end <= shift_start:
        end += timedelta(days=1)        # overnight shift ends the next day
    minutes = int((punch_out - end).total_seconds()) // 60
    return minutes if minutes >= 30 else 0

def hist_out(h: dict) -> dict:
   h = dict(h)
   if isinstance(h.get("at"), datetime):
       h["at"] = to_ms(h["at"])
   return h

def record_out(doc: dict) -> dict:
   # What the client sees: times in milliseconds, no _id (contract)
   return {
       "emp_code": doc["emp_code"],
       "date": doc["date"],
       "status": doc["status"],
       "punch_in": to_ms(doc.get("punch_in")),
       "punch_out": to_ms(doc.get("punch_out")),
       "work_hours": doc.get("work_hours"),
       "late_minutes": doc.get("late_minutes", 0),
       "overtime_minutes": doc.get("overtime_minutes", 0),
       "half_day": doc.get("half_day", False),
       "history": [hist_out(h) for h in doc.get("history", [])],
   }


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str


class PunchInIn(BaseModel):
   emp_code: str
   punched_at: Optional[StrictInt] = Field(None, ge=100000000000, le=4102444800000)
   status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"


class PunchOutIn(BaseModel):
   emp_code: str
   punched_at: Optional[StrictInt] = Field(None, ge=100000000000, le=4102444800000)

class RegularizeIn(BaseModel):
   model_config = ConfigDict(extra="forbid")   # derived fields cannot be sent
   status: Optional[Literal["PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"]] = None
   punch_in: Optional[StrictInt] = Field(None, ge=100000000000, le=4102444800000)
   punch_out: Optional[StrictInt] = Field(None, ge=100000000000, le=4102444800000)
   reason: str = Field(min_length=5, max_length=200)
   regularized_by: str = Field(min_length=1, max_length=50)


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now()
    db.employees.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.get("/employees")
def list_employees(department: Optional[str] = None, page: int = 1, page_size: int = 20):
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size #fix1
    total = db.employees.count_documents(q) #fix2
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
   emp = db.employees.find_one({"emp_code": body.emp_code})
   if emp is None:
       raise HTTPException(404, "employee not found")
   if body.punched_at is not None:
       ts = to_dt(body.punched_at)
   else:
       ts = datetime.now(timezone.utc).replace(microsecond=0)
   d = attendance_date(ts, emp["shift_start"], emp["shift_end"])
   doc = {
       "emp_code": body.emp_code,
       "date": d,
       "status": body.status,
       "punch_in": ts,
       "punch_out": None,
       "work_hours": None,
       "late_minutes": compute_late_minutes(ts, emp["shift_start"], d),
       "overtime_minutes": 0,
       "half_day": False,
       "history": [],
   }
   try:
       db.attendance_logs.insert_one(doc)
   except DuplicateKeyError:
       raise HTTPException(409, "already punched in for this date")
   return record_out(doc)

@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
   emp = db.employees.find_one({"emp_code": body.emp_code})
   if emp is None:
       raise HTTPException(404, "employee not found")
   if body.punched_at is not None:
       out = to_dt(body.punched_at)
   else:
       out = datetime.now(timezone.utc).replace(microsecond=0)

   # the most recent record whose punch_in is at or before this punch-out
   rec = db.attendance_logs.find_one(
       {"emp_code": body.emp_code, "punch_in": {"$lte": out}},
       sort=[("punch_in", -1)],
   )
   if rec is None:
       raise HTTPException(404, "no punch-in found")
   if rec.get("punch_out") is not None:
       raise HTTPException(409, "already punched out")
   if out <= rec["punch_in"] or out > rec["punch_in"] + timedelta(hours=24):
       raise HTTPException(422, "punched_at must be after punch_in and within 24 hours")

   work_hours = compute_work_hours(rec["punch_in"], out)
   update = {
       "punch_out": out,
       "work_hours": work_hours,
       "overtime_minutes": compute_overtime(out, emp["shift_start"], emp["shift_end"], rec["date"]),
       "half_day": work_hours < 4.5,
   }
   # only succeeds if punch_out is STILL empty: this is what makes it race-safe
   res = db.attendance_logs.update_one(
       {"_id": rec["_id"], "punch_out": None}, {"$set": update}
   )
   if res.matched_count == 0:
       raise HTTPException(409, "already punched out")
   rec.update(update)
   return record_out(rec)

@app.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code: str, date: str, body: RegularizeIn):
    # PART 1: find the record
    try:
        ok = datetime.strptime(date, "%Y-%m-%d").date().isoformat() == date
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(422, "date must be YYYY-MM-DD")
    emp = db.employees.find_one({"emp_code": emp_code})
    if emp is None:
        raise HTTPException(404, "employee not found")
    rec = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if rec is None:
        raise HTTPException(404, "no record for that date")

    # PART 2: work out the new status and times, and validate them
    old_status = rec["status"]
    old_in, old_out = rec.get("punch_in"), rec.get("punch_out")
    new_status = body.status or old_status
    if new_status in ("ABSENT", "LEAVE"):
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(422, "ABSENT/LEAVE cannot have punch times")
        new_in, new_out = None, None
    else:
        new_in = to_dt(body.punch_in) if body.punch_in is not None else old_in
        new_out = to_dt(body.punch_out) if body.punch_out is not None else old_out
        if new_in is None:
            raise HTTPException(422, "a presence status needs a punch_in")
        if attendance_date(new_in, emp["shift_start"], emp["shift_end"]) != date:
            raise HTTPException(422, "punch_in must be on the record's attendance date")
        if new_out is not None and (new_out <= new_in or new_out > new_in + timedelta(hours=24)):
            raise HTTPException(422, "punch_out must be after punch_in and within 24 hours")

    # PART 3: recompute the derived fields (R2 to R5)
    if new_in is None:
        new = {"late_minutes": 0, "work_hours": None, "overtime_minutes": 0, "half_day": False}
    else:
        new = {"late_minutes": compute_late_minutes(new_in, emp["shift_start"], date)}
        if new_out is None:
            new.update({"work_hours": None, "overtime_minutes": 0, "half_day": False})
        else:
            wh = compute_work_hours(new_in, new_out)
            new.update({
                "work_hours": wh,
                "overtime_minutes": compute_overtime(new_out, emp["shift_start"], emp["shift_end"], date),
                "half_day": wh < 4.5,
            })
    new.update({"status": new_status, "punch_in": new_in, "punch_out": new_out})

    # PART 4: what actually changed? (only those fields go into history)
    old = {
        "status": old_status, "punch_in": old_in, "punch_out": old_out,
        "work_hours": rec.get("work_hours"), "late_minutes": rec.get("late_minutes", 0),
        "overtime_minutes": rec.get("overtime_minutes", 0), "half_day": rec.get("half_day", False),
    }

    def shown(field, value):
        return to_ms(value) if field in ("punch_in", "punch_out") else value

    changes = {f: {"from": shown(f, old[f]), "to": shown(f, new[f])} for f in new if old[f] != new[f]}
    if all(f not in changes for f in ("status", "punch_in", "punch_out")):
        raise HTTPException(422, "this request changes nothing")

    # PART 5: save, but only if nobody else changed the record in the meantime
    history = rec.get("history", [])
    entry = {
        "at": datetime.now(timezone.utc).replace(microsecond=0),
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }
    res = db.attendance_logs.update_one(
        {"_id": rec["_id"], "punch_out": old_out, f"history.{len(history)}": {"$exists": False}},
        {"$set": new, "$push": {"history": entry}},
    )
    if res.matched_count == 0:
        raise HTTPException(409, "record was changed by someone else, please retry")
    rec.update(new)
    rec["history"] = history + [entry]
    return record_out(rec)

@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status
    docs = list(db.attendance_logs.find(q))
    docs.sort(key=lambda d: d["date"], reverse=True)
    total = len(docs)
    page_docs = docs[(page - 1) * page_size : page * page_size]
    for d in page_docs:
        d["id"] = str(d.pop("_id"))
    return {"items": page_docs, "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
