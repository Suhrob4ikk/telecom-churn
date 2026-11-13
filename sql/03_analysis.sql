-- Аналитические запросы. Каждый блок отвечает на один бизнес-вопрос.
-- Результаты выгружаются в Excel-отчёт скриптом src/build_report.py.

-- name: q1_sales_by_salon_month
-- Динамика продаж в салонах: выручка по месяцам и прирост к прошлому месяцу.
SELECT
  sl.city || ', ' || sl.district                    AS salon,
  TRUNC(s.sale_date, 'MM')                          AS month,
  COUNT(*)                                          AS sales_cnt,
  SUM(s.amount_tjs)                                 AS revenue_tjs,
  ROUND(100 * (SUM(s.amount_tjs)
        / NULLIF(LAG(SUM(s.amount_tjs)) OVER (PARTITION BY sl.salon_id
                                              ORDER BY TRUNC(s.sale_date, 'MM')), 0) - 1), 1) AS mom_growth_pct
FROM sales s
JOIN salons sl ON sl.salon_id = s.salon_id
GROUP BY sl.salon_id, sl.city, sl.district, TRUNC(s.sale_date, 'MM')
ORDER BY salon, month;

-- name: q2_tariff_usage
-- Использование услуг по тарифам: ARPU, трафик, доля использования пакета.
SELECT
  t.tariff_name,
  t.monthly_fee_tjs,
  COUNT(DISTINCT mu.subscriber_id)                         AS subscribers,
  ROUND(AVG(mu.topup_tjs), 1)                              AS arpu_tjs,
  ROUND(AVG(mu.data_mb) / 1024, 2)                         AS avg_data_gb,
  ROUND(100 * AVG(mu.data_mb) / 1024 / t.data_gb, 1)       AS data_package_used_pct,
  ROUND(AVG(mu.voice_min))                                 AS avg_voice_min
FROM monthly_usage mu
JOIN subscribers s ON s.subscriber_id = mu.subscriber_id
JOIN tariffs     t ON t.tariff_id     = s.tariff_id
WHERE mu.month_start >= DATE '2026-01-01'
GROUP BY t.tariff_name, t.monthly_fee_tjs, t.data_gb
ORDER BY arpu_tjs DESC;

-- name: q3_campaign_effect
-- Эффективность акций удержания: доля ушедших за 3 месяца после контакта,
-- целевая группа против контрольной (случайное разбиение 50/50).
SELECT
  c.campaign_name,
  cc.group_type,
  COUNT(*)                                                             AS contacted,
  SUM(CASE WHEN s.churn_date < ADD_MONTHS(cc.contact_date, 3) THEN 1 ELSE 0 END) AS churned_3m,
  ROUND(100 * AVG(CASE WHEN s.churn_date < ADD_MONTHS(cc.contact_date, 3) THEN 1 ELSE 0 END), 1) AS churn_3m_pct
FROM campaign_contacts cc
JOIN campaigns   c ON c.campaign_id   = cc.campaign_id
JOIN subscribers s ON s.subscriber_id = cc.subscriber_id
GROUP BY c.campaign_id, c.campaign_name, cc.group_type
ORDER BY c.campaign_id, cc.group_type DESC;

-- name: q4_cohort_retention
-- Когорты по кварталу подключения: какая доля абонентов активна через 3, 6, 12 месяцев.
SELECT
  TO_CHAR(s.activation_date, 'YYYY') || '-Q' || TO_CHAR(s.activation_date, 'Q') AS cohort,
  COUNT(*)                                                                    AS activated,
  ROUND(100 * AVG(CASE WHEN s.churn_date IS NULL OR s.churn_date >= ADD_MONTHS(s.activation_date, 3)  THEN 1 ELSE 0 END), 1) AS alive_3m_pct,
  ROUND(100 * AVG(CASE WHEN s.churn_date IS NULL OR s.churn_date >= ADD_MONTHS(s.activation_date, 6)  THEN 1 ELSE 0 END), 1) AS alive_6m_pct,
  CASE WHEN MAX(s.activation_date) <= DATE '2025-09-30'
       THEN ROUND(100 * AVG(CASE WHEN s.churn_date IS NULL OR s.churn_date >= ADD_MONTHS(s.activation_date, 12) THEN 1 ELSE 0 END), 1)
  END                                                                         AS alive_12m_pct
FROM subscribers s
WHERE s.activation_date <= DATE '2026-03-31'
GROUP BY TO_CHAR(s.activation_date, 'YYYY') || '-Q' || TO_CHAR(s.activation_date, 'Q')
ORDER BY cohort;

-- name: q5_churn_by_salon
-- Отток по салону подключения в сравнении со средним по сети:
-- какие салоны «приводят» абонентов, которые быстро уходят.
SELECT
  salon,
  subscribers,
  churned_6m,
  churn_6m_pct,
  ROUND(churn_6m_pct / AVG(churn_6m_pct) OVER (), 2) AS vs_network_avg
FROM (
  SELECT
    sl.city || ', ' || sl.district AS salon,
    COUNT(*)                       AS subscribers,
    SUM(CASE WHEN s.churn_date < ADD_MONTHS(s.activation_date, 6) THEN 1 ELSE 0 END) AS churned_6m,
    ROUND(100 * AVG(CASE WHEN s.churn_date < ADD_MONTHS(s.activation_date, 6) THEN 1 ELSE 0 END), 1) AS churn_6m_pct
  FROM subscribers s
  JOIN salons sl ON sl.salon_id = s.salon_id
  WHERE s.activation_date <= DATE '2026-03-31'   -- у всех есть 6 месяцев наблюдения
  GROUP BY sl.city, sl.district
)
ORDER BY churn_6m_pct DESC;

-- name: q6_churn_signal
-- Ранний сигнал: как меняется потребление за месяц до ухода
-- (по витрине; сравнение уходящих и остающихся).
SELECT
  CASE churn_next_month WHEN 1 THEN 'Уйдёт в след. месяце' ELSE 'Останется' END AS segment,
  COUNT(*)                                   AS rows_cnt,
  ROUND(AVG(data_trend), 2)                  AS avg_data_trend,
  ROUND(AVG(topup_trend), 2)                 AS avg_topup_trend,
  ROUND(AVG(active_days), 1)                 AS avg_active_days
FROM mart_subscriber_month
WHERE data_trend IS NOT NULL
GROUP BY churn_next_month;
