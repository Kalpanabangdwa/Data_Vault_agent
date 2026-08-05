WITH SRC AS (
    SELECT *
    FROM {{ source('CARD_PROCESSOR', 'card_status') }}
),
LOGIC AS (
    SELECT *
    FROM SRC
),
RENAME AS (
    SELECT
        status_id AS card_status_id,
        status_name AS status_name,
        updated_at AS status_updated_at
    FROM LOGIC
),
FILTER AS (
    SELECT *
    FROM RENAME
    WHERE 1 = 1
),
"JOIN" AS (
    SELECT *
    FROM FILTER
),
FINAL AS (
    SELECT
        card_status_id,
        status_name,
        status_updated_at
    FROM "JOIN"
)
SELECT *
FROM FINAL