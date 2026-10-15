# DECISIONS.md

### 1. Indexes
I created two types of indexes to improve employee and attendance operations. The unique employee code index prevents duplicate employees, while the attendance index ensures one record per employee per day and supports attendance queries. I rejected a standalone `status` index because it has only five possible values.

### 2. Punch-in Race Condition
If two punch-in requests arrive for the same employee on the same day, the unique attendance index allows only one to succeed. MongoDB raises a `DuplicateKeyError` for the other request, which the code converts into an HTTP 409 response. The unique index avoids the need for a separate check-before-insert operation.

### 3. Leaderboard Ties
I have not implemented the leaderboard yet. If I add it, I would use MongoDB’s `$setWindowFields` stage with a `rank` operator so employees with the same score receive the same rank and all tied employees are included.

### 4. Headcount
I have not implemented the headcount calculation yet. I would start with employees in the specified department and then join their attendance logs. This ensures employees without any attendance records are still included in the total headcount.

### 5. Handling 100x More Data
If the dataset grows significantly, deep pagination using `skip` may become slower because the database must pass over many records. I would switch to cursor-based pagination to retrieve subsequent records more efficiently.