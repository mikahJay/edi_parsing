{{ config(materialized='view', secure=true) }}

select
  metric_date,
  transaction_set,
  sum(transaction_count) as transaction_count
from {{ ref('fact_transaction_counts') }}
group by 1, 2
