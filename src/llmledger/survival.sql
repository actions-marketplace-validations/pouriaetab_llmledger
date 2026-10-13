-- One row per model: how many days it was followed and how that ended.
-- The same table as survival.subject_table in Python, built independently
-- in SQL. The pipeline stops before publishing if the two disagree.
-- :definition is main, headline, no_first_week or real_only.
WITH ev AS (
  SELECT n, model, kind, field, old, new,
         CAST(strftime('%s', at) AS INTEGER) AS secs,
         substr(at, 1, 10) AS day,
         json_type(old) IN ('integer', 'real')
           AND json_type(new) IN ('integer', 'real') AS numeric
  FROM events
),

-- Time zero: the first time a model was added. Models already in the
-- first version (kind 'start') are left out.
starts AS (
  SELECT model, n, secs AS start
  FROM (SELECT model, n, secs,
               ROW_NUMBER() OVER (PARTITION BY model ORDER BY n) AS k
        FROM ev WHERE kind = 'added')
  WHERE k = 1
    AND model NOT IN (SELECT model FROM ev WHERE kind = 'start')
),

-- Bulk clean up: a removal on a day with 50 or more removals.
removals AS (
  SELECT n, COUNT(*) OVER (PARTITION BY day) AS same_day
  FROM ev WHERE kind = 'removed'
),

-- Price changes from one number to another, with the change before and
-- after on the same field of the same model.
priced AS (
  SELECT n, model, field, secs,
         CAST(old AS REAL) AS a, CAST(new AS REAL) AS b,
         LAG(CAST(old AS REAL)) OVER w AS prev_a,
         LAG(CAST(new AS REAL)) OVER w AS prev_b,
         LAG(secs) OVER w AS prev_secs,
         LEAD(CAST(old AS REAL)) OVER w AS next_a,
         LEAD(CAST(new AS REAL)) OVER w AS next_b,
         LEAD(secs) OVER w AS next_secs
  FROM ev WHERE kind = 'price' AND numeric
  WINDOW w AS (PARTITION BY model, field ORDER BY n)
),

-- Unit fix: 100 times larger or smaller. Reverted: undone within 30
-- days, or the change that undid one. The first change on a field has
-- no change before it, so prev_a is NULL there, and NULL = b is neither
-- true nor false. COALESCE turns that unknown into false.
corrections AS (
  SELECT n,
         COALESCE(
           (a <> 0 AND b <> 0 AND (b / a >= 100 OR b / a <= 1.0 / 100))
           OR (prev_a = b AND prev_b = a AND secs - prev_secs <= 30 * 86400)
           OR (next_b = a AND next_a = b AND next_secs - secs <= 30 * 86400),
           0) AS fixed
  FROM priced
),

exits AS (
  SELECT ev.model, ev.secs,
    CASE
      WHEN ev.kind = 'removed' THEN
        CASE WHEN :definition = 'real_only' AND r.same_day >= 50
             THEN 'cleanup' ELSE 'removed' END
      WHEN ev.kind = 'deprecation' AND ev.old = 'null' AND ev.new <> 'null'
        THEN 'retirement'
      WHEN ev.kind = 'price' AND ev.numeric
        AND NOT (:definition = 'headline' AND ev.field NOT IN
                 ('input_cost_per_token', 'output_cost_per_token'))
        AND NOT (:definition = 'no_first_week'
                 AND ev.secs - s.start <= 7 * 86400)
        AND NOT (:definition = 'real_only' AND c.fixed)
        THEN 'price'
    END AS cause
  FROM ev
  JOIN starts s ON s.model = ev.model AND ev.n > s.n
  LEFT JOIN removals r ON r.n = ev.n
  LEFT JOIN corrections c ON c.n = ev.n
),

-- The first exit wins. On the same day: removal, then retirement, then price.
first_exit AS (
  SELECT model, secs, cause
  FROM (SELECT model, secs, cause,
               ROW_NUMBER() OVER (
                 PARTITION BY model
                 ORDER BY secs, CASE cause WHEN 'retirement' THEN 1
                                           WHEN 'price' THEN 2 ELSE 0 END
               ) AS k
        FROM exits WHERE cause IS NOT NULL)
  WHERE k = 1
)

SELECT s.model,
       (COALESCE(f.secs, (SELECT MAX(secs) FROM ev)) - s.start) / 86400.0
         AS days,
       CASE WHEN f.cause IS NULL OR f.cause = 'cleanup' THEN 'censored'
            ELSE f.cause END AS kind
FROM starts s
LEFT JOIN first_exit f ON f.model = s.model
ORDER BY s.model;
