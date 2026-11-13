-- Витрина «абонент × месяц» для анализа оттока и ML.
-- Одна строка = активный абонент в месяце M.
-- Признаки считаются только по данным до конца месяца M (без заглядывания в будущее),
-- целевая переменная churn_next_month = абонент ушёл в месяце M+1.

CREATE TABLE mart_subscriber_month AS
WITH u AS (
  SELECT
    mu.subscriber_id,
    mu.month_start,
    mu.voice_min,
    mu.data_mb,
    mu.topup_tjs,
    mu.active_days,
    AVG(mu.data_mb)   OVER (PARTITION BY mu.subscriber_id ORDER BY mu.month_start
                            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS data_mb_prev3_avg,
    AVG(mu.topup_tjs) OVER (PARTITION BY mu.subscriber_id ORDER BY mu.month_start
                            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS topup_prev3_avg,
    LAG(mu.active_days) OVER (PARTITION BY mu.subscriber_id ORDER BY mu.month_start) AS active_days_prev
  FROM monthly_usage mu
)
SELECT
  u.subscriber_id,
  u.month_start,
  s.tariff_id,
  t.tariff_name,
  t.monthly_fee_tjs,
  s.salon_id,
  sl.city,
  s.gender,
  EXTRACT(YEAR FROM u.month_start) - s.birth_year                    AS age,
  MONTHS_BETWEEN(u.month_start, TRUNC(s.activation_date, 'MM'))      AS tenure_months,
  u.voice_min,
  u.data_mb,
  u.topup_tjs,
  u.active_days,
  ROUND(u.data_mb   / NULLIF(u.data_mb_prev3_avg, 0), 3)             AS data_trend,
  ROUND(u.topup_tjs / NULLIF(u.topup_prev3_avg, 0), 3)               AS topup_trend,
  u.active_days - u.active_days_prev                                  AS active_days_delta,
  CASE WHEN EXISTS (SELECT 1 FROM campaign_contacts cc
                    WHERE cc.subscriber_id = u.subscriber_id
                      AND cc.group_type = 'TARGET'
                      AND cc.contact_date < ADD_MONTHS(u.month_start, 1))
       THEN 1 ELSE 0 END                                              AS got_retention_offer,
  CASE WHEN TRUNC(s.churn_date, 'MM') = ADD_MONTHS(u.month_start, 1)
       THEN 1 ELSE 0 END                                              AS churn_next_month
FROM u
JOIN subscribers s ON s.subscriber_id = u.subscriber_id
JOIN tariffs     t ON t.tariff_id     = s.tariff_id
JOIN salons     sl ON sl.salon_id     = s.salon_id
-- последний месяц выгрузки не берём: для него ещё неизвестен исход M+1
WHERE u.month_start < (SELECT MAX(month_start) FROM monthly_usage);
