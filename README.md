# Employee Attendance & Analytics API

A FastAPI + MongoDB service for punch-in/out, manual corrections with an audit trail, and attendance analytics.

## Run locally

1. Install Python 3.11+ and have MongoDB 6.0+ available (Atlas free tier or local Docker).
2. Create and activate a virtual environment, then install dependencies:

python -m venv .venv
.venv\Scripts\activate (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt

3. Create a `.env` file in the project root (it is not committed):

MONGO_URI=<your MongoDB connection string>
MONGO_DB=<database name>

4. Start the server (indexes are created automatically at startup):

uvicorn app.main:app --port 8000

5. Open http://127.0.0.1:8000/docs to try the endpoints.

## Status

| Endpoint | Status |
|---|---|
| GET /health (pings MongoDB, 503 if down) | Done |
| POST /employees, GET /employees | Done |
| POST /attendance/punch-in | Done |
| POST /attendance/punch-out | Done |
| PATCH /attendance/{emp_code}/{date} (with history) | Done |
| GET /attendance | Done |
| GET /analytics/employees/{emp_code}/monthly | Not done |
| GET /analytics/departments/summary | Not done |
| GET /analytics/leaderboard/late | Not done |
| GET /analytics/departments/{department}/trend | Not done |
| GET /admin/explain/{endpoint} | Not done |

## Design notes

- Times are stored as UTC datetimes, exposed to clients as epoch milliseconds, and attendance dates are calculated in IST.
- Business rules R1 to R5 (date assignment, late minutes, overtime, work hours, half day) live in small helper functions in `app/main.py`.
- Duplicate punch-ins and duplicate employees are prevented by unique indexes, not by check-then-insert.
- Punch-out and PATCH use conditional updates so two simultaneous requests cannot both succeed.
- `REVIEW.md` lists the defects I found in the starter code and how I fixed them.

## Known gaps

- The four analytics endpoints and the explain endpoint are not implemented.
- I checked the time helpers with a local script that is not in this repository.
- (Add anything else that is unfinished or you are unsure about.)

## Notes

I used an AI assistant to learn concepts and to check my work; I typed and tested the code and can explain it.
