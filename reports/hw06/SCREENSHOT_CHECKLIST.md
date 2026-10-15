# HW6 Screenshot Checklist

Before every terminal screenshot, run:

```bash
echo "Student: Xuanhua Li"
```

The assignment warns that points may be deducted when the student's name is not visible.

## Part 1

1. Swagger or Postman: successful POST with HTTP 201 and the created document.
2. Successful GET-all, GET-one, PUT, and DELETE operations. Combine operations only when status codes and response bodies remain readable.
3. Three validation failures: missing `listingTitle`, invalid enum, and invalid date, showing HTTP 422 and error details.
4. MongoDB Compass: database `s2974_doc`, collection `listings`, and at least one sample document with `createdAt` and `updatedAt` visible.

## Part 2

1. `http://127.0.0.1:8274/hw6-chat` after at least 10 messages, with assistant replies and the metric line visible.
2. Browser/Postman JSON for `GET /api/memory/{user_id}`.
3. Browser/Postman JSON for `GET /api/aggregate/{user_id}`.
4. MongoDB Compass showing documents in `messages`, `summaries`, and `episodes`. Include collection names in the left panel.

## Part 3

1. Terminal after `python code/hw6_memory_experiment.py` completes, showing all four settings and the student's name.
2. The completed table from `reports/hw06/METRICS.md` should be pasted as a report table; it does not need to be a screenshot.

## Part 4

1. Chat page or Postman result for `/compact`, showing the before-and-after line counts.
2. Terminal result of `python code/test_hw6_offline.py`, showing `6/6 PASS` and the student's name.
3. The final terminal result of `python code/verify_hw6.py`, showing every check and the final pass count.

Do not screenshot secrets, `.env`, passwords, database credentials, or the full embedding arrays.
