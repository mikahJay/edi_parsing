{{ config(materialized='table') }}

select
  to_date(ingested_at) as metric_date,
  source_file,
  transaction_set,
  segment_id,
  count(*) as segment_count,
  current_timestamp() as updated_at
from {{ ref('edi_segments') }}
group by 1, 2, 3, 4
