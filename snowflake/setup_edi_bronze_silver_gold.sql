-- Snowflake setup for Bronze/Silver/Gold modeling of parser outputs:
-- - parsed_records.jsonl (JSONL segment records)
-- - metadata.json (batch metadata JSON)
--
-- Update placeholders before running:
--   <DATABASE_NAME>, <SCHEMA_NAME>, <WAREHOUSE_NAME>, <STAGE_URL>, <STORAGE_INTEGRATION_NAME>

USE ROLE SYSADMIN;

CREATE DATABASE IF NOT EXISTS <DATABASE_NAME>;
CREATE SCHEMA IF NOT EXISTS <DATABASE_NAME>.<SCHEMA_NAME>;
USE DATABASE <DATABASE_NAME>;
USE SCHEMA <SCHEMA_NAME>;

-- Optional (for external cloud storage stage):
-- CREATE STORAGE INTEGRATION IF NOT EXISTS <STORAGE_INTEGRATION_NAME>
--   TYPE = EXTERNAL_STAGE
--   STORAGE_PROVIDER = S3
--   ENABLED = TRUE
--   STORAGE_AWS_ROLE_ARN = '<AWS_ROLE_ARN>'
--   STORAGE_ALLOWED_LOCATIONS = ('<STAGE_URL>');

CREATE FILE FORMAT IF NOT EXISTS ff_edi_json
  TYPE = JSON
  STRIP_OUTER_ARRAY = FALSE;

CREATE STAGE IF NOT EXISTS stg_edi_segments
  URL = '<STAGE_URL>/segments'
  FILE_FORMAT = ff_edi_json;

CREATE STAGE IF NOT EXISTS stg_edi_metadata
  URL = '<STAGE_URL>/metadata'
  FILE_FORMAT = ff_edi_json;

-- --------------------------------------------------------------------------
-- Bronze (raw landing, immutable)
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_edi_segments (
  loaded_at TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  filename STRING NOT NULL,
  file_row_number NUMBER NOT NULL,
  record VARIANT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_edi_metadata (
  loaded_at TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  filename STRING NOT NULL,
  record VARIANT NOT NULL
);

-- Option A: Snowpipe auto-ingest (configure cloud notifications separately)
CREATE PIPE IF NOT EXISTS pipe_raw_edi_segments AS
COPY INTO raw_edi_segments (filename, file_row_number, record)
FROM (
  SELECT
    METADATA$FILENAME::STRING,
    METADATA$FILE_ROW_NUMBER::NUMBER,
    $1
  FROM @stg_edi_segments
)
FILE_FORMAT = (FORMAT_NAME = ff_edi_json);

CREATE PIPE IF NOT EXISTS pipe_raw_edi_metadata AS
COPY INTO raw_edi_metadata (filename, record)
FROM (
  SELECT
    METADATA$FILENAME::STRING,
    $1
  FROM @stg_edi_metadata
)
FILE_FORMAT = (FORMAT_NAME = ff_edi_json);

-- Option B: Scheduled COPY INTO (use instead of or in addition to Snowpipe)
-- COPY INTO raw_edi_segments (filename, file_row_number, record)
-- FROM (
--   SELECT METADATA$FILENAME::STRING, METADATA$FILE_ROW_NUMBER::NUMBER, $1
--   FROM @stg_edi_segments
-- )
-- FILE_FORMAT = (FORMAT_NAME = ff_edi_json);
--
-- COPY INTO raw_edi_metadata (filename, record)
-- FROM (
--   SELECT METADATA$FILENAME::STRING, $1
--   FROM @stg_edi_metadata
-- )
-- FILE_FORMAT = (FORMAT_NAME = ff_edi_json);

-- --------------------------------------------------------------------------
-- Silver (typed query-friendly)
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS edi_segments (
  ingested_at TIMESTAMP_LTZ NOT NULL,
  raw_filename STRING NOT NULL,
  raw_file_row_number NUMBER NOT NULL,
  source_file STRING,
  segment_index NUMBER,
  segment_id STRING,
  transaction_set STRING,
  transaction_control_number STRING,
  interchange_control_number STRING,
  functional_group_control_number STRING,
  segment_elements ARRAY
);

CREATE TABLE IF NOT EXISTS edi_segment_elements (
  ingested_at TIMESTAMP_LTZ NOT NULL,
  raw_filename STRING NOT NULL,
  raw_file_row_number NUMBER NOT NULL,
  source_file STRING,
  segment_index NUMBER,
  segment_id STRING,
  element_position NUMBER,
  element_value STRING
);

CREATE TABLE IF NOT EXISTS edi_batch_metadata (
  ingested_at TIMESTAMP_LTZ NOT NULL,
  metadata_filename STRING NOT NULL,
  generated_at_utc TIMESTAMP_TZ,
  total_edi_files NUMBER,
  successfully_parsed_files NUMBER,
  malformed_edi_files NUMBER,
  transaction_set_count_835 NUMBER,
  transaction_set_count_837 NUMBER,
  creation_earliest TIMESTAMP_TZ,
  creation_latest TIMESTAMP_TZ
);

CREATE TABLE IF NOT EXISTS edi_file_metadata (
  ingested_at TIMESTAMP_LTZ NOT NULL,
  metadata_filename STRING NOT NULL,
  generated_at_utc TIMESTAMP_TZ,
  file_path STRING,
  malformed BOOLEAN,
  transaction_count_835 NUMBER,
  transaction_count_837 NUMBER,
  creation_datetime TIMESTAMP_TZ,
  error_count NUMBER,
  errors ARRAY
);

ALTER TABLE edi_segments CLUSTER BY (transaction_set, segment_id, TO_DATE(ingested_at));
ALTER TABLE edi_file_metadata CLUSTER BY (malformed, TO_DATE(ingested_at));

CREATE OR REPLACE VIEW vw_edi_segments_secure SECURE AS
SELECT
  ingested_at,
  source_file,
  segment_index,
  segment_id,
  transaction_set,
  transaction_control_number,
  interchange_control_number,
  functional_group_control_number,
  segment_elements
FROM edi_segments;

-- --------------------------------------------------------------------------
-- Gold (aggregation-ready marts)
-- --------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dim_date (
  date_key DATE PRIMARY KEY,
  year NUMBER,
  quarter NUMBER,
  month NUMBER,
  day NUMBER
);

CREATE TABLE IF NOT EXISTS fact_edi_segment_counts (
  metric_date DATE NOT NULL,
  source_file STRING,
  transaction_set STRING,
  segment_id STRING,
  segment_count NUMBER NOT NULL,
  updated_at TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS fact_transaction_counts (
  metric_date DATE NOT NULL,
  source_file STRING,
  interchange_control_number STRING,
  transaction_set STRING,
  transaction_count NUMBER NOT NULL,
  updated_at TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS fact_error_counts (
  metric_date DATE NOT NULL,
  malformed BOOLEAN NOT NULL,
  error_count NUMBER NOT NULL,
  file_count NUMBER NOT NULL,
  updated_at TIMESTAMP_LTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE VIEW vw_edi_daily_transaction_counts SECURE AS
SELECT
  metric_date,
  transaction_set,
  SUM(transaction_count) AS transaction_count
FROM fact_transaction_counts
GROUP BY metric_date, transaction_set;

-- --------------------------------------------------------------------------
-- Streams + tasks for incremental transforms
-- --------------------------------------------------------------------------

CREATE STREAM IF NOT EXISTS str_raw_edi_segments
  ON TABLE raw_edi_segments
  APPEND_ONLY = TRUE;

CREATE STREAM IF NOT EXISTS str_raw_edi_metadata
  ON TABLE raw_edi_metadata
  APPEND_ONLY = TRUE;

CREATE STREAM IF NOT EXISTS str_edi_segments
  ON TABLE edi_segments
  APPEND_ONLY = TRUE;

CREATE STREAM IF NOT EXISTS str_edi_file_metadata
  ON TABLE edi_file_metadata
  APPEND_ONLY = TRUE;

CREATE TASK IF NOT EXISTS task_raw_to_silver_segments
  WAREHOUSE = <WAREHOUSE_NAME>
  SCHEDULE = 'USING CRON */5 * * * * UTC'
AS
INSERT INTO edi_segments (
  ingested_at,
  raw_filename,
  raw_file_row_number,
  source_file,
  segment_index,
  segment_id,
  transaction_set,
  transaction_control_number,
  interchange_control_number,
  functional_group_control_number,
  segment_elements
)
SELECT
  loaded_at,
  filename,
  file_row_number,
  record:source_file::STRING,
  record:segment_index::NUMBER,
  record:segment_id::STRING,
  record:transaction_set::STRING,
  record:transaction_control_number::STRING,
  record:interchange_control_number::STRING,
  record:functional_group_control_number::STRING,
  record:segment_elements::ARRAY
FROM str_raw_edi_segments;

CREATE TASK IF NOT EXISTS task_silver_segment_elements
  WAREHOUSE = <WAREHOUSE_NAME>
  AFTER task_raw_to_silver_segments
AS
INSERT INTO edi_segment_elements (
  ingested_at,
  raw_filename,
  raw_file_row_number,
  source_file,
  segment_index,
  segment_id,
  element_position,
  element_value
)
SELECT
  s.ingested_at,
  s.raw_filename,
  s.raw_file_row_number,
  s.source_file,
  s.segment_index,
  s.segment_id,
  f.index::NUMBER AS element_position,
  f.value::STRING AS element_value
FROM edi_segments AS s,
LATERAL FLATTEN(input => s.segment_elements) AS f
WHERE s.ingested_at >= DATEADD('minute', -10, CURRENT_TIMESTAMP());

CREATE TASK IF NOT EXISTS task_raw_to_silver_metadata
  WAREHOUSE = <WAREHOUSE_NAME>
  SCHEDULE = 'USING CRON */5 * * * * UTC'
AS
BEGIN
  INSERT INTO edi_batch_metadata (
    ingested_at,
    metadata_filename,
    generated_at_utc,
    total_edi_files,
    successfully_parsed_files,
    malformed_edi_files,
    transaction_set_count_835,
    transaction_set_count_837,
    creation_earliest,
    creation_latest
  )
  SELECT
    loaded_at,
    filename,
    record:generated_at_utc::TIMESTAMP_TZ,
    record:total_edi_files::NUMBER,
    record:successfully_parsed_files::NUMBER,
    record:malformed_edi_files::NUMBER,
    record:transaction_set_counts:"835"::NUMBER,
    record:transaction_set_counts:"837"::NUMBER,
    record:creation_date_range:earliest::TIMESTAMP_TZ,
    record:creation_date_range:latest::TIMESTAMP_TZ
  FROM str_raw_edi_metadata;

  INSERT INTO edi_file_metadata (
    ingested_at,
    metadata_filename,
    generated_at_utc,
    file_path,
    malformed,
    transaction_count_835,
    transaction_count_837,
    creation_datetime,
    error_count,
    errors
  )
  SELECT
    r.loaded_at,
    r.filename,
    r.record:generated_at_utc::TIMESTAMP_TZ,
    f.value:file_path::STRING,
    f.value:malformed::BOOLEAN,
    f.value:transaction_counts:"835"::NUMBER,
    f.value:transaction_counts:"837"::NUMBER,
    f.value:creation_datetime::TIMESTAMP_TZ,
    f.value:error_count::NUMBER,
    f.value:errors::ARRAY
  FROM str_raw_edi_metadata AS r,
  LATERAL FLATTEN(input => r.record:files) AS f;
END;

CREATE TASK IF NOT EXISTS task_silver_to_gold_segment_counts
  WAREHOUSE = <WAREHOUSE_NAME>
  AFTER task_raw_to_silver_segments
AS
MERGE INTO fact_edi_segment_counts t
USING (
  SELECT
    TO_DATE(ingested_at) AS metric_date,
    source_file,
    transaction_set,
    segment_id,
    COUNT(*) AS segment_count
  FROM str_edi_segments
  GROUP BY 1, 2, 3, 4
) s
ON t.metric_date = s.metric_date
AND NVL(t.source_file, '') = NVL(s.source_file, '')
AND NVL(t.transaction_set, '') = NVL(s.transaction_set, '')
AND NVL(t.segment_id, '') = NVL(s.segment_id, '')
WHEN MATCHED THEN UPDATE SET
  t.segment_count = t.segment_count + s.segment_count,
  t.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  metric_date,
  source_file,
  transaction_set,
  segment_id,
  segment_count
) VALUES (
  s.metric_date,
  s.source_file,
  s.transaction_set,
  s.segment_id,
  s.segment_count
);

CREATE TASK IF NOT EXISTS task_silver_to_gold_transaction_counts
  WAREHOUSE = <WAREHOUSE_NAME>
  AFTER task_raw_to_silver_segments
AS
MERGE INTO fact_transaction_counts t
USING (
  SELECT
    TO_DATE(ingested_at) AS metric_date,
    source_file,
    interchange_control_number,
    transaction_set,
    COUNT(*) AS transaction_count
  FROM (
    SELECT DISTINCT
      ingested_at,
      source_file,
      interchange_control_number,
      transaction_set,
      transaction_control_number
    FROM str_edi_segments
    WHERE transaction_set IN ('835', '837')
      AND transaction_control_number IS NOT NULL
  )
  GROUP BY 1, 2, 3, 4
) s
ON t.metric_date = s.metric_date
AND NVL(t.source_file, '') = NVL(s.source_file, '')
AND NVL(t.interchange_control_number, '') = NVL(s.interchange_control_number, '')
AND NVL(t.transaction_set, '') = NVL(s.transaction_set, '')
WHEN MATCHED THEN UPDATE SET
  t.transaction_count = t.transaction_count + s.transaction_count,
  t.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  metric_date,
  source_file,
  interchange_control_number,
  transaction_set,
  transaction_count
) VALUES (
  s.metric_date,
  s.source_file,
  s.interchange_control_number,
  s.transaction_set,
  s.transaction_count
);

CREATE TASK IF NOT EXISTS task_silver_to_gold_error_counts
  WAREHOUSE = <WAREHOUSE_NAME>
  AFTER task_raw_to_silver_metadata
AS
MERGE INTO fact_error_counts t
USING (
  SELECT
    TO_DATE(ingested_at) AS metric_date,
    malformed,
    SUM(COALESCE(error_count, 0)) AS error_count,
    COUNT(*) AS file_count
  FROM str_edi_file_metadata
  GROUP BY 1, 2
) s
ON t.metric_date = s.metric_date
AND t.malformed = s.malformed
WHEN MATCHED THEN UPDATE SET
  t.error_count = t.error_count + s.error_count,
  t.file_count = t.file_count + s.file_count,
  t.updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  metric_date,
  malformed,
  error_count,
  file_count
) VALUES (
  s.metric_date,
  s.malformed,
  s.error_count,
  s.file_count
);

-- Enable root tasks after review/customization:
-- ALTER TASK task_raw_to_silver_segments RESUME;
-- ALTER TASK task_raw_to_silver_metadata RESUME;
