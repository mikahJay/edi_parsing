{{ config(materialized='table') }}

select
  to_date(ingested_at) as metric_date,
  malformed,
  sum(coalesce(error_count, 0)) as error_count,
  count(*) as file_count,
  current_timestamp() as updated_at
from {{ ref('edi_file_metadata') }}
group by 1, 2
