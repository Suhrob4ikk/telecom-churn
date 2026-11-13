"""Создаёт схему в Oracle, загружает синтетические CSV и строит витрину.

Запуск:  python src/load_oracle.py
"""
import time

import numpy as np
import pandas as pd

from db import ROOT, connect, query_df, run_file

DATA = ROOT / "data" / "synthetic"
ORDER = ["tariffs", "salons", "subscribers", "monthly_usage", "sales", "campaigns", "campaign_contacts"]
DATES = {"subscribers": ["activation_date", "churn_date"], "monthly_usage": ["month_start"],
         "sales": ["sale_date"], "campaigns": ["start_date", "end_date"], "campaign_contacts": ["contact_date"]}


def load_table(conn, name):
    df = pd.read_csv(DATA / f"{name}.csv", parse_dates=DATES.get(name, []))
    df = df.astype(object).where(df.notna(), None)
    rows = [tuple(v.to_pydatetime() if isinstance(v, pd.Timestamp) else (v.item() if isinstance(v, np.generic) else v) for v in r)
            for r in df.itertuples(index=False)]
    cols = ", ".join(df.columns)
    binds = ", ".join(f":{i + 1}" for i in range(len(df.columns)))
    with conn.cursor() as cur:
        for i in range(0, len(rows), 20_000):
            cur.executemany(f"INSERT INTO {name} ({cols}) VALUES ({binds})", rows[i:i + 20_000])
    conn.commit()
    return len(rows)


def main():
    t0 = time.time()
    with connect() as conn:
        run_file(conn, ROOT / "sql" / "01_schema.sql")
        for name in ORDER:
            print(f"{name:18s} загружено {load_table(conn, name):>8,d}")
        run_file(conn, ROOT / "sql" / "02_mart.sql")
        n = query_df(conn, "SELECT COUNT(*) n, ROUND(100*AVG(churn_next_month),2) churn_pct FROM mart_subscriber_month")
        print(f"Витрина mart_subscriber_month: {int(n.n[0]):,d} строк, отток в след. месяце {n.churn_pct[0]}%")
    print(f"Готово за {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
