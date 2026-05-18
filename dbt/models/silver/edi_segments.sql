{{ config(
    materialized='incremental',
    unique_key=['raw_filename', 'raw_file_row_number'],
    incremental_strategy='merge',
    cluster_by=['transaction_set', 'segment_id', 'to_date(ingested_at)']
) }}

select
  loaded_at as ingested_at,
  filename as raw_filename,
  file_row_number as raw_file_row_number,
  record:source_file::string as source_file,
  record:segment_index::number as segment_index,
  record:segment_id::string as segment_id,
  record:transaction_set::string as transaction_set,
  record:transaction_control_number::string as transaction_control_number,
  record:interchange_control_number::string as interchange_control_number,
  record:functional_group_control_number::string as functional_group_control_number,
  record:segment_elements::array as segment_elements
from {{ source('bronze', 'raw_edi_segments') }}
{% if is_incremental() %}
where loaded_at > coalesce((select max(ingested_at) from {{ this }}), '1900-01-01'::timestamp_ltz)
{% endif %}
