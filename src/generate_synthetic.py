"""Генератор СИНТЕТИЧЕСКИХ данных мобильного оператора.

Все данные выдуманы. Цель — получить реалистичную многотабличную структуру
(абоненты, тарифы, салоны, ежемесячное потребление, продажи, маркетинговые
акции), на которой можно отработать SQL-аналитику в Oracle: JOIN, группировки,
подзапросы, оконные функции, когорты, оценку акции через контрольную группу.

Запуск:  python src/generate_synthetic.py   -> CSV в data/synthetic/
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_SUBS = 20_000
START, END = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-09-30")
OUT = Path(__file__).resolve().parents[1] / "data" / "synthetic"

rng = np.random.default_rng(SEED)


def tariffs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tariff_id": [1, 2, 3, 4, 5],
            "tariff_name": ["Старт", "Смарт", "Безлимит", "Семейный", "Молодёжный"],
            "monthly_fee_tjs": [35, 65, 120, 90, 45],
            "data_gb": [3, 12, 100, 30, 20],
            "minutes": [100, 400, 2000, 800, 300],
            # «врождённая» склонность к оттоку: дешёвые тарифы уходят чаще
            "_hazard": [0.055, 0.030, 0.015, 0.012, 0.040],
            "_share": [0.30, 0.28, 0.12, 0.12, 0.18],
        }
    )


def salons() -> pd.DataFrame:
    rows = [
        ("Душанбе", "Сино"), ("Душанбе", "Шохмансур"), ("Душанбе", "Фирдавси"),
        ("Душанбе", "Исмоили Сомони"), ("Худжанд", "Центр"), ("Худжанд", "Панчшанбе"),
        ("Бохтар", "Центр"), ("Куляб", "Центр"), ("Истаравшан", "Центр"),
        ("Турсунзаде", "Центр"), ("Вахдат", "Центр"), ("Хорог", "Центр"),
    ]
    df = pd.DataFrame(rows, columns=["city", "district"])
    df.insert(0, "salon_id", range(101, 101 + len(df)))
    # качество обслуживания в салоне влияет на отток подключённых там абонентов
    df["_quality"] = rng.normal(0, 1, len(df)).round(2)
    df.loc[df.salon_id == 106, "_quality"] = -2.2  # «проблемный» салон
    return df


def subscribers(tar: pd.DataFrame, sal: pd.DataFrame) -> pd.DataFrame:
    days = (END - START).days - 60
    # подключения растут к концу периода
    act_offsets = (rng.beta(1.3, 1.0, N_SUBS) * days).astype(int)
    df = pd.DataFrame(
        {
            "subscriber_id": np.arange(1_000_001, 1_000_001 + N_SUBS),
            "activation_date": START + pd.to_timedelta(act_offsets, unit="D"),
            "salon_id": rng.choice(sal.salon_id, N_SUBS, p=_salon_weights(sal)),
            "tariff_id": rng.choice(tar.tariff_id, N_SUBS, p=tar._share),
            "gender": rng.choice(["M", "F"], N_SUBS, p=[0.56, 0.44]),
            "birth_year": rng.integers(1960, 2008, N_SUBS),
        }
    )
    # молодёжный тариф — молодым
    young = df.tariff_id == 5
    df.loc[young, "birth_year"] = rng.integers(1999, 2008, young.sum())
    return df


def _salon_weights(sal):
    w = np.where(sal.city == "Душанбе", 3.0, 1.0)
    w = np.where(sal.city == "Худжанд", 2.0, w)
    return w / w.sum()


def simulate(subs, tar, sal):
    """Помесячная симуляция: потребление, пополнения, отток.

    Перед оттоком абонент 'затухает' — потребление падает за 1–3 месяца.
    Это и есть сигнал, который должен ловить анализ.
    """
    months = pd.period_range(START, END, freq="M")
    hz = subs.tariff_id.map(tar.set_index("tariff_id")._hazard).to_numpy()
    q = subs.salon_id.map(sal.set_index("salon_id")._quality).to_numpy()
    age = 2026 - subs.birth_year.to_numpy()
    base_hazard = hz * np.exp(-0.25 * q) * np.where(age < 25, 1.25, 1.0)
    fee = subs.tariff_id.map(tar.set_index("tariff_id").monthly_fee_tjs).to_numpy()
    gb = subs.tariff_id.map(tar.set_index("tariff_id").data_gb).to_numpy()
    mins = subs.tariff_id.map(tar.set_index("tariff_id").minutes).to_numpy()

    act_m = subs.activation_date.dt.to_period("M").to_numpy()
    intensity = rng.lognormal(0, 0.35, len(subs))  # индивидуальная «активность»
    churn_month = np.full(len(subs), None, dtype=object)
    fade = np.zeros(len(subs))  # 0..1, насколько абонент «затух»
    decided = np.full(len(subs), -1)  # через сколько месяцев уйдёт

    # маркетинговая акция удержания: сентябрь 2025 и март 2026
    camp = {pd.Period("2025-09", "M"): 1, pd.Period("2026-03", "M"): 2}
    contacts, usage = [], []

    for m in months:
        alive = (act_m <= m) & (churn_month == None)  # noqa: E711
        idx = np.where(alive)[0]
        if len(idx) == 0:
            continue
        tenure = np.array([(m - a).n for a in act_m[idx]])
        h = base_hazard[idx] * np.where(tenure < 3, 1.6, 1.0) * np.where(tenure > 12, 0.7, 1.0)

        # акция: случайно 50/50 target/control среди тех, кто уже «затухает»
        if m in camp:
            cand = idx[(fade[idx] > 0) | (rng.random(len(idx)) < 0.15)]
            cand = rng.choice(cand, min(len(cand), 1500), replace=False)
            grp = rng.random(len(cand)) < 0.5
            for s, g in zip(cand, grp):
                contacts.append((camp[m], subs.subscriber_id.iat[s], m.to_timestamp() + pd.Timedelta(days=int(rng.integers(0, 10))), "TARGET" if g else "CONTROL"))
                if g and rng.random() < 0.35:  # акция спасает ~35% из целевой группы
                    fade[s] = 0
                    decided[s] = -1
                    base_hazard[s] *= 0.6

        # новые решения уйти
        new = (decided[idx] < 0) & (rng.random(len(idx)) < h)
        decided[idx[new]] = rng.integers(1, 4, new.sum())
        dec = idx[decided[idx] > 0]
        fade[dec] = np.minimum(1, fade[dec] + 1 / decided[dec].clip(1) * 0.8)
        decided[dec] -= 1
        gone = dec[decided[dec] == 0]
        churn_month[gone] = m
        decided[gone] = -1

        live = np.setdiff1d(idx, gone)
        k = intensity[live] * (1 - 0.75 * fade[live]) * rng.lognormal(0, 0.2, len(live))
        seasonal = 1.15 if m.month in (3, 12) else 1.0  # Навруз, Новый год
        usage.append(
            pd.DataFrame(
                {
                    "subscriber_id": subs.subscriber_id.to_numpy()[live],
                    "month_start": m.to_timestamp(),
                    "voice_min": (mins[live] * 0.55 * k * seasonal).round().astype(int),
                    "sms_cnt": rng.poisson(12 * k).astype(int),
                    "data_mb": (gb[live] * 1024 * 0.6 * k * seasonal).round().astype(int),
                    "topup_tjs": np.maximum(0, fee[live] * (0.9 + 0.4 * k) * (1 - 0.5 * fade[live]) + rng.normal(0, 5, len(live))).round(2),
                    "active_days": np.clip((30 * (1 - 0.6 * fade[live]) * rng.uniform(0.8, 1.0, len(live))).round(), 1, 31).astype(int),
                }
            )
        )

    subs = subs.copy()
    churn_dates = [
        (cm.to_timestamp(how="end").normalize() - pd.Timedelta(days=int(rng.integers(0, 20)))) if cm is not None else pd.NaT
        for cm in churn_month
    ]
    # уход не может быть раньше подключения (ловится CHECK-ограничением в Oracle)
    subs["churn_date"] = pd.Series(churn_dates, index=subs.index).where(
        lambda d: d.isna() | (d >= subs.activation_date), subs.activation_date
    ).where(pd.Series(churn_dates, index=subs.index).notna())
    usage = pd.concat(usage, ignore_index=True)
    contacts = pd.DataFrame(contacts, columns=["campaign_id", "subscriber_id", "contact_date", "group_type"])
    return subs, usage, contacts


def sales(subs, sal):
    """Продажи в салонах: SIM при подключении + устройства/аксессуары/смены тарифа."""
    sim = pd.DataFrame(
        {"salon_id": subs.salon_id, "sale_date": subs.activation_date, "product_type": "SIM", "amount_tjs": 10.0, "subscriber_id": subs.subscriber_id}
    )
    n = 26_000
    days = (END - START).days
    d = START + pd.to_timedelta(rng.integers(0, days, n), unit="D")
    prod = rng.choice(["Смартфон", "Аксессуар", "Роутер", "Смена тарифа"], n, p=[0.22, 0.45, 0.08, 0.25])
    base = {"Смартфон": 1800, "Аксессуар": 90, "Роутер": 450, "Смена тарифа": 0}
    amt = np.array([base[p] * rng.lognormal(0, 0.35) for p in prod]).round(2)
    # декабрь и март — пики продаж
    boost = np.isin(d.month, [3, 12])
    amt[boost] *= 1.2
    other = pd.DataFrame(
        {
            "salon_id": rng.choice(sal.salon_id, n, p=_salon_weights(sal)),
            "sale_date": d,
            "product_type": prod,
            "amount_tjs": amt.round(2),
            "subscriber_id": rng.choice(subs.subscriber_id, n),
        }
    )
    df = pd.concat([sim, other], ignore_index=True).sort_values("sale_date").reset_index(drop=True)
    df.insert(0, "sale_id", np.arange(1, len(df) + 1))
    return df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tar, sal = tariffs(), salons()
    subs = subscribers(tar, sal)
    subs, usage, contacts = simulate(subs, tar, sal)
    sl = sales(subs, sal)
    camps = pd.DataFrame(
        {
            "campaign_id": [1, 2],
            "campaign_name": ["Осенний бонус +5 ГБ", "Навруз: скидка 30% на 3 месяца"],
            "start_date": pd.to_datetime(["2025-09-01", "2026-03-01"]),
            "end_date": pd.to_datetime(["2025-09-30", "2026-03-31"]),
            "channel": ["SMS", "Звонок оператора"],
        }
    )
    tables = {
        "tariffs": tar.drop(columns=["_hazard", "_share"]),
        "salons": sal.drop(columns=["_quality"]),
        "subscribers": subs,
        "monthly_usage": usage,
        "sales": sl,
        "campaigns": camps,
        "campaign_contacts": contacts,
    }
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False, date_format="%Y-%m-%d")
        print(f"{name:18s} {len(df):>8,d} строк")
    print(f"Отток за период: {subs.churn_date.notna().mean():.1%}")


if __name__ == "__main__":
    main()
