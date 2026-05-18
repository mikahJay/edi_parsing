{{ config(materialized='table') }}

with dedup as (
  select distinct
    ingested_at,
    source_file,
    interchange_control_number,
    transaction_set,
    transaction_control_number
  from {{ ref('edi_segments') }}
  where transaction_set in ('835', '837')
    and transaction_control_number is not null
)
select
  to_date(ingested_at) as metric_date,
  source_file,
  interchange_control_number,
  transaction_set,
  count(*) as transaction_count,
  current_timestamp() as updated_at
from dedup
group by 1, 2, 3, 4
