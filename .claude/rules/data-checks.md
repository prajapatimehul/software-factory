---
paths:
  - "**/*.sql"
  - "**/models/**"
  - "**/migrations/**"
---
# Data checks — a query that agrees with you has proved nothing yet
- Write the expected value in the task file before running the query.
- An empty or zero result needs a control query that must return rows on the same table and filter.
- Check one more member than the one that broke: the next column, the next tenant, the next day.
- A count goes into the task file with the query that produced it. No count is typed from memory.
- A wrong figure is fixed where it is computed. The card, chart or column that shows it stays.
- A migration is run on development first, and the task file holds both outputs before production is touched.
