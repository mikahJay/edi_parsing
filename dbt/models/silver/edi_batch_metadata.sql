{{ config(
    materialized='incremental',
    unique_key=['ingested_at', 'metadata_filename'],
    incremental_strategy='merge'
) }}

select
  loaded_at as ingested_at,
  filename as metadata_filename,
  record:generated_at_utc::timestamp_tz as generated_at_utc,
  record:total_edi_files::number as total_edi_files,
  record:successfully_parsed_files::number as successfully_parsed_files,
  record:malformed_edi_files::number as malformed_edi_files,
  record:transaction_set_counts:"835"::number as transaction_set_count_835,
  record:transaction_set_counts:"837"::number as transaction_set_count_837,
  record:creation_date_range:earliest::timestamp_tz as creation_earliest,
  record:creation_date_range:latest::timestamp_tz as creation_latest
from {{ source('bronze', 'raw_edi_metadata') }}
{% if is_incremental() %}
where loaded_at > coalesce((select max(ingested_at) from {{ this }}), '1900-01-01'::timestamp_ltz)
{% endif %}
