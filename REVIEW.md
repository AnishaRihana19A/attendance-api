# REVIEW.md

| # | Where | What was wrong | How I noticed it | Fix / Status |
|---:|---|---|---|---|
| 1 | `punch_in` | An unknown employee code caused a 500 error because the lookup returned `None`. | Tested punch-in with an invalid employee code and saw a `'NoneType' object is not subscriptable` error. | **Fixed:** Return HTTP 404 when the employee does not exist. |
| 2 | `list_employees` | The page offset used `page * page_size`, skipping the first page of employees. | Page 1 returned an empty `items` list even though `total` was 7. | **Fixed:** Use `(page - 1) * page_size`. |
| 3 | `list_employees` | The total count ignored the department filter. | Compared the filtered employee list with the total count. | **Fixed:** Count documents using the same filter `q`. |
| 4 | Employee responses | `created_at` was returned as a local-time string instead of UTC epoch milliseconds. | Inspected the API response and found a timestamp such as `2026-10-11T22:10:08.495000`. | **Found, not fixed.** |
| 5 | `compute_late_minutes` | The calculation used the wrong time zone, ignored seconds, and failed for overnight shifts. | Checked boundary cases, including a punch at 09:40:01 and an overnight shift. | **Found, not fixed.** |
| 6 | `compute_work_hours` | Python's `round()` did not provide the required half-up rounding behavior. | Tested 3618 seconds and observed 1.0 instead of 1.01. | **Found, not fixed.** |
| 7 | `compute_overtime` | The calculation missed the 30-minute minimum, mishandled naive datetimes, and used the wrong end day for overnight shifts. | Checked overtime boundaries, datetime handling, and overnight shifts in `test_helpers.py`. | **Found, not fixed.** |
| 8 | `punch_in` | A find-then-insert approach could allow simultaneous requests to create duplicate attendance records. | Identified the race condition while reviewing the starter code. | **Fixed:** Added a unique attendance index and handled `DuplicateKeyError`. |
| 9 | `punch_in` | The endpoint accepted arbitrary status text instead of only the three valid values. | Reviewed the input validation in the starter code. | **Found, not fixed.** |
| 10 | API responses | Responses could expose an internal `id`, and timestamps did not use epoch milliseconds. | Inspected the response structure and timestamp serialization. | **Found, not fixed.** |
| 11 | `list_attendance` | The endpoint loaded all records into memory, sorted them in Python, had no `page_size` limit, and did not validate the date range. | Identified these issues while reviewing the starter code. | **Found, not fixed.** |
| 12 | `create_employee` | A find-then-insert approach could create duplicate employees under concurrent requests, and input validation was insufficient. | Reviewed the insertion flow and validation logic in the starter code. | **Found, not fixed.** |
| 13 | `/health` | The endpoint returned `ok` even when MongoDB was unavailable. | Identified the missing database connectivity check during code review. | **Found, not fixed.** |
| 14 | Database startup | The starter code had no indexes and no connection timeout configured. | Inspected the database initialization and connection settings. | **Found, not fixed.** |

## Looked at and decided it was not a defect

| # | Where | What I checked | Why it is correct |
|---:|---|---|---|
| 1 | `list_attendance` | Checked the page slicing expression `(page - 1) * page_size`. | The offset calculation correctly starts at zero for page 1. The problem was loading and sorting all records in memory, not the offset formula. |
| 2 | `insert_one` and `doc.pop("_id", None)` | Checked how MongoDB assigns document IDs during insertion. | MongoDB adds `_id` to the document, and removing it from the response dictionary prevents exposing the internal identifier. |