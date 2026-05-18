{{ config(
    materialized='incremental',
    unique_key=['raw_filename', 'raw_file_row_number', 'element_position'],
    incremental_strategy='merge'
) }}

select
  s.ingested_at,
  s.raw_filename,
  s.raw_file_row_number,
  s.source_file,
  s.segment_index,
  s.segment_id,
  f.index::number as element_position,
  f.value::string as element_value
from {{ ref('edi_segments') }} as s,
lateral flatten(input => s.segment_elements) as f
{% if is_incremental() %}
where s.ingested_at > coalesce((select max(ingested_at) from {{ this }}), '1900-01-01'::timestamp_ltz)
{% endif %}
