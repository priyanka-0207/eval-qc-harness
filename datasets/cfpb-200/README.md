# cfpb-200

Real consumer complaint narratives from the CFPB complaint database, pulled from my Databricks lakehouse (`workspace.src.silver_cfpb_complaints`). It holds up to 400 complaints per product family from the latest 12 months. `run.py` uses the oldest 75% by date as the retrieval corpus and samples 200 test cases from the newest dates.

CFPB has since dropped narratives from its public API and bulk CSV, so this export is the only copy in the repo.

Export query (Databricks SQL), saved as `cfpb_real.csv` in this folder:

```sql
WITH recent AS (
  SELECT * FROM workspace.src.silver_cfpb_complaints
  WHERE has_narrative AND product_family <> 'other'
    AND date_received >= (SELECT add_months(max(date_received), -12) FROM workspace.src.silver_cfpb_complaints)
), ranked AS (
  SELECT *, row_number() OVER (PARTITION BY product_family ORDER BY rand(7)) AS rn FROM recent
)
SELECT complaint_id, date_received, product_family AS product, sub_product, issue, sub_issue,
       company, state, tags, narrative
FROM ranked WHERE rn <= 400
```

`tags` (Older American, Servicemember) and `issue` / `sub_issue` (fraud, identity theft) set the expected escalation, so the guardrail can be tested.
