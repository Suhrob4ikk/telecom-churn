-- Схема синтетических данных мобильного оператора (Oracle)
-- Порядок удаления учитывает внешние ключи.

BEGIN
  FOR t IN (SELECT table_name FROM user_tables
            WHERE table_name IN ('CAMPAIGN_CONTACTS','CAMPAIGNS','SALES','MONTHLY_USAGE',
                                 'SUBSCRIBERS','SALONS','TARIFFS','MART_SUBSCRIBER_MONTH')) LOOP
    EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS PURGE';
  END LOOP;
END;
/

CREATE TABLE tariffs (
  tariff_id        NUMBER(3)     PRIMARY KEY,
  tariff_name      VARCHAR2(50 CHAR)  NOT NULL,
  monthly_fee_tjs  NUMBER(8,2)   NOT NULL,
  data_gb          NUMBER(5)     NOT NULL,
  minutes          NUMBER(6)     NOT NULL
);

CREATE TABLE salons (
  salon_id  NUMBER(5)    PRIMARY KEY,
  city      VARCHAR2(50 CHAR) NOT NULL,
  district  VARCHAR2(50 CHAR) NOT NULL
);

CREATE TABLE subscribers (
  subscriber_id    NUMBER(10)  PRIMARY KEY,
  activation_date  DATE        NOT NULL,
  salon_id         NUMBER(5)   NOT NULL REFERENCES salons,
  tariff_id        NUMBER(3)   NOT NULL REFERENCES tariffs,
  gender           CHAR(1)     CHECK (gender IN ('M','F')),
  birth_year       NUMBER(4),
  churn_date       DATE,
  CONSTRAINT chk_churn_after_act CHECK (churn_date IS NULL OR churn_date >= activation_date)
);

CREATE TABLE monthly_usage (
  subscriber_id  NUMBER(10)  NOT NULL REFERENCES subscribers,
  month_start    DATE        NOT NULL,
  voice_min      NUMBER(8)   NOT NULL,
  sms_cnt        NUMBER(8)   NOT NULL,
  data_mb        NUMBER(10)  NOT NULL,
  topup_tjs      NUMBER(10,2) NOT NULL,
  active_days    NUMBER(2)   NOT NULL,
  CONSTRAINT pk_usage PRIMARY KEY (subscriber_id, month_start)
);

CREATE TABLE sales (
  sale_id        NUMBER(10)   PRIMARY KEY,
  salon_id       NUMBER(5)    NOT NULL REFERENCES salons,
  sale_date      DATE         NOT NULL,
  product_type   VARCHAR2(30 CHAR) NOT NULL,
  amount_tjs     NUMBER(10,2) NOT NULL,
  subscriber_id  NUMBER(10)   REFERENCES subscribers
);

CREATE TABLE campaigns (
  campaign_id    NUMBER(5)     PRIMARY KEY,
  campaign_name  VARCHAR2(100 CHAR) NOT NULL,
  start_date     DATE          NOT NULL,
  end_date       DATE          NOT NULL,
  channel        VARCHAR2(30 CHAR)
);

CREATE TABLE campaign_contacts (
  campaign_id    NUMBER(5)    NOT NULL REFERENCES campaigns,
  subscriber_id  NUMBER(10)   NOT NULL REFERENCES subscribers,
  contact_date   DATE         NOT NULL,
  group_type     VARCHAR2(10 CHAR) NOT NULL CHECK (group_type IN ('TARGET','CONTROL')),
  CONSTRAINT pk_contacts PRIMARY KEY (campaign_id, subscriber_id)
);

CREATE INDEX ix_usage_month ON monthly_usage (month_start);
CREATE INDEX ix_sales_salon_date ON sales (salon_id, sale_date);
