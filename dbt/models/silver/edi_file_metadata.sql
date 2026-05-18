{{ config(
    materialized='incremental',
    unique_key=['ingested_at', 'metadata_filename', 'file_path'],
    incremental_strategy='merge',
    cluster_by=['malformed', 'to_date(ingested_at)']
) }}

select
  r.loaded_at as ingested_at,
  r.filename as metadata_filename,
  r.record:generated_at_utc::timestamp_tz as generated_at_utc,
  f.value:file_path::string as file_path,
  f.value:malformed::boolean as malformed,
  f.value:transaction_counts:"835"::number as transaction_count_835,
  f.value:transaction_counts:"837"::number as transaction_count_837,
  f.value:creation_datetime::timestamp_tz as creation_datetime,
  f.value:error_count::number as error_count,
  f.value:errors::array as errors
from {{ source('bronze', 'raw_edi_metadata') }} as r,
lateral flatten(input => r.record:files) as f
{% if is_incremental() %}
where r.loaded_at > coalesce((select max(ingested_at) from {{ this }}), '1900-01-01'::timestamp_ltz)
{% endif %}
