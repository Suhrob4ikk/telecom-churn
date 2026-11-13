"""Собирает и выполняет ноутбуки проекта (чтобы в репозитории были сохранённые результаты).

Запуск:  python src/build_notebooks.py
"""
from pathlib import Path

import nbformat as nbf
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks"


def md(s):
    return nbf.v4.new_markdown_cell(s.strip())


def code(s):
    return nbf.v4.new_code_cell(s.strip())


SETUP = """
import sys, warnings
sys.path.insert(0, '../src')
warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, matplotlib.pyplot as plt
plt.rcParams.update({'figure.figsize': (9, 4), 'axes.spines.top': False, 'axes.spines.right': False})
GREEN, PURPLE, GREY = '#00B956', '#731982', '#9AA0A6'
"""

analysis = [
    md("""
# 1. Аналитика оператора: продажи, тарифы, акции, отток

**Данные синтетические** — сгенерированы скриптом `src/generate_synthetic.py`, чтобы повторить
структуру данных мобильного оператора (абоненты, тарифы, салоны, потребление, продажи, акции).
Все расчёты делаются **SQL-запросами в Oracle** (`sql/03_analysis.sql`), здесь — визуализация и выводы.

Бизнес-вопросы:
1. Как меняются продажи в салонах?
2. Как абоненты используют услуги на разных тарифах?
3. Работают ли акции удержания — и как это доказать?
4. Где и почему абоненты уходят? Можно ли заметить уход заранее?
"""),
    code(SETUP + """
from db import connect, named_queries, query_df
qs = named_queries(__import__('pathlib').Path('../sql/03_analysis.sql'))
conn = connect()
r = {k: query_df(conn, v) for k, v in qs.items()}
list(r)
"""),
    md("## 1. Динамика продаж в салонах"),
    code("""
q1 = r['q1_sales_by_salon_month']
q1['month'] = pd.to_datetime(q1['month'])
net = q1.groupby('month')['revenue_tjs'].sum() / 1e3
ax = net.plot(color=GREEN, marker='o', lw=2)
ax.set(title='Выручка сети салонов по месяцам, тыс. сомони', xlabel='', ylabel='тыс. сомони')
for m in net.index[net.index.month.isin([3, 12])]:
    ax.axvline(m, color=PURPLE, ls=':', alpha=.6)
plt.show()
top = q1.groupby('salon')['revenue_tjs'].sum().sort_values(ascending=False) / 1e3
top.round(0).to_frame('выручка, тыс. сомони')
"""),
    md("""
**Вывод.** Пики продаж приходятся на **декабрь и март** (Новый год и Навруз, пунктир) — к ним стоит
готовить запасы смартфонов и персонал. Основная выручка — у четырёх салонов Душанбе.
"""),
    md("## 2. Использование услуг по тарифам"),
    code("""
q2 = r['q2_tariff_usage'].set_index('tariff_name')
q2[['monthly_fee_tjs', 'arpu_tjs', 'avg_data_gb', 'data_package_used_pct', 'subscribers']]
"""),
    md("""
**Вывод.** На всех тарифах ARPU примерно на **30% выше абонентской платы**: абоненты докупают услуги сверх пакета.
При этом пакет интернета используется лишь на ~65%. Значит, люди платят сверху не за нехватку
трафика, а за другие услуги, и апсейл стоит строить на дополнительных сервисах, а не на объёме ГБ.
"""),
    md("## 3. Эффективность акций удержания"),
    code("""
from scipy import stats
q3 = r['q3_campaign_effect']
rows = []
for name, g in q3.groupby('campaign_name', sort=False):
    t = g[g.group_type == 'TARGET'].iloc[0]; c = g[g.group_type == 'CONTROL'].iloc[0]
    table = [[t.churned_3m, t.contacted - t.churned_3m], [c.churned_3m, c.contacted - c.churned_3m]]
    _, p, _, _ = stats.chi2_contingency(table)
    rows.append({'акция': name, 'отток TARGET, %': t.churn_3m_pct, 'отток CONTROL, %': c.churn_3m_pct,
                 'эффект, п.п.': round(t.churn_3m_pct - c.churn_3m_pct, 1), 'p-value': f'{p:.1e}'})
pd.DataFrame(rows)
"""),
    md("""
**Вывод.** Обе акции снижают отток за 3 месяца примерно на **9–12 п.п.** относительно контрольной группы,
различие статистически значимо (χ², p ≪ 0,01). Контрольная группа выбрана случайно, поэтому
разницу можно считать именно эффектом акции, а не особенностью выбранных абонентов.
"""),
    md("## 4. Где уходят абоненты и можно ли это заметить заранее"),
    code("""
q5 = r['q5_churn_by_salon'].sort_values('churn_6m_pct')
colors = [PURPLE if v > 1.3 else GREY for v in q5.vs_network_avg]
ax = q5.plot.barh(x='salon', y='churn_6m_pct', color=colors, legend=False)
ax.axvline(q5.churn_6m_pct.mean(), color=GREEN, ls='--', label='среднее по сети')
ax.set(title='Отток в первые 6 месяцев по салону подключения, %', ylabel='', xlabel='%'); ax.legend()
plt.show()
"""),
    code("""
q4 = r['q4_cohort_retention'].set_index('cohort')
q4
"""),
    code("""
q6 = r['q6_churn_signal'].set_index('segment')
q6
"""),
    md("""
**Выводы.**
* Два салона в **Худжанде** «приводят» абонентов, которые уходят в 1,4–1,5 раза чаще среднего по сети.
  Это повод проверить качество подключения там (навязанный тариф? неверные ожидания клиента?).
* Когорты стабильны: через 6 месяцев остаётся ~75% подключившихся, через год ~61%.
* **Ранний сигнал:** за месяц до ухода трафик и пополнения падают в среднем на ~25%, активных дней
  меньше на 6. Это можно ловить автоматически — см. ноутбук 2 с моделью.

**Рекомендации:** (1) аудит подключений в салонах Худжанда; (2) масштабировать акции удержания —
эффект доказан на контрольной группе; (3) ежемесячно отбирать абонентов с падением потребления
для превентивного предложения.
"""),
]

ml = [
    md("""
# 2. Прогноз оттока абонентов: бейзлайн против градиентного бустинга

**Данные:** публичный датасет IBM Telco Customer Churn (7 043 абонента, 21 признак).
**Задача:** предсказать, кто уйдёт, и решить, кому из абонентов выгодно сделать предложение об удержании.

План: подготовка данных → бейзлайн (логистическая регрессия) → LightGBM → честная проверка на
отложенной выборке → интерпретация → экономика удержания.
"""),
    code(SETUP + """
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score, roc_curve
import lightgbm as lgb

df = pd.read_csv('../data/raw/Telco-Customer-Churn.csv')
df.shape
"""),
    md("## Подготовка и первый взгляд"),
    code("""
# TotalCharges читается как текст: у 11 новых абонентов (tenure = 0) там пробел
print('пустых TotalCharges:', (df.TotalCharges.str.strip() == '').sum())
df['TotalCharges'] = pd.to_numeric(df.TotalCharges, errors='coerce').fillna(0)
df['churn'] = (df.Churn == 'Yes').astype(int)
print(f"доля ушедших: {df.churn.mean():.1%}")
df.groupby('Contract').churn.agg(['mean', 'size']).rename(columns={'mean': 'доля оттока', 'size': 'абонентов'})
"""),
    code("""
fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
df.groupby(pd.cut(df.tenure, [-1, 6, 12, 24, 48, 72])).churn.mean().plot.bar(ax=ax[0], color=GREEN, rot=0)
ax[0].set(title='Отток по сроку жизни абонента, мес.', xlabel='', ylabel='доля оттока')
df.groupby('PaymentMethod').churn.mean().sort_values().plot.barh(ax=ax[1], color=PURPLE)
ax[1].set(title='Отток по способу оплаты', ylabel='')
plt.tight_layout(); plt.show()
"""),
    md("""
Уходят в основном **новые** абоненты на **помесячном контракте**, платящие электронным чеком.
Добавлю пару признаков, которые отражают это явно, и разобью данные: 80% — обучение, 20% — отложенный тест,
который модель не видит до самого конца.
"""),
    code("""
df['avg_charge'] = df.TotalCharges / df.tenure.replace(0, 1)
df['n_services'] = (df[['OnlineSecurity', 'OnlineBackup', 'DeviceProtection', 'TechSupport',
                        'StreamingTV', 'StreamingMovies']] == 'Yes').sum(axis=1)
num = ['tenure', 'MonthlyCharges', 'TotalCharges', 'avg_charge', 'n_services', 'SeniorCitizen']
cat = [c for c in df.columns if df[c].dtype == object and c not in ('customerID', 'Churn')]
X, y = df[num + cat], df.churn
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
cv = StratifiedKFold(5, shuffle=True, random_state=42)
len(X_tr), len(X_te)
"""),
    md("## Бейзлайн: логистическая регрессия"),
    code("""
pre = ColumnTransformer([('num', StandardScaler(), num), ('cat', OneHotEncoder(handle_unknown='ignore'), cat)])
logreg = make_pipeline(pre, LogisticRegression(max_iter=2000, C=0.5))
cv_lr = cross_val_score(logreg, X_tr, y_tr, cv=cv, scoring='roc_auc')
print(f'LogReg  CV ROC-AUC: {cv_lr.mean():.3f} ± {cv_lr.std():.3f}')
"""),
    md("## LightGBM"),
    code("""
X_tr_l, X_te_l = X_tr.copy(), X_te.copy()
for c in cat:
    X_tr_l[c] = X_tr_l[c].astype('category')
    X_te_l[c] = pd.Categorical(X_te_l[c], categories=X_tr_l[c].cat.categories)
# Неглубокие деревья и сильная регуляризация: данных всего ~5,6 тыс. строк
gbm = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.02, num_leaves=8, min_child_samples=40,
                         subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5,
                         verbose=-1, random_state=42)
cv_gb = cross_val_score(gbm, X_tr_l, y_tr, cv=cv, scoring='roc_auc')
print(f'LightGBM CV ROC-AUC: {cv_gb.mean():.3f} ± {cv_gb.std():.3f}')
"""),
    md("## Проверка на отложенной выборке"),
    code("""
logreg.fit(X_tr, y_tr); gbm.fit(X_tr_l, y_tr)
p_lr, p_gb = logreg.predict_proba(X_te)[:, 1], gbm.predict_proba(X_te_l)[:, 1]

def lift_at(y, p, q=0.2):
    k = int(len(y) * q); top = np.argsort(-p)[:k]
    return np.asarray(y)[top].mean() / np.mean(y)

res = pd.DataFrame({
    'ROC-AUC': [roc_auc_score(y_te, p) for p in (p_lr, p_gb)],
    'PR-AUC': [average_precision_score(y_te, p) for p in (p_lr, p_gb)],
    'Lift@20%': [lift_at(y_te, p) for p in (p_lr, p_gb)],
}, index=['Логистическая регрессия', 'LightGBM']).round(3)
res
"""),
    code("""
for p, name, col in [(p_lr, 'LogReg', GREY), (p_gb, 'LightGBM', GREEN)]:
    fpr, tpr, _ = roc_curve(y_te, p); plt.plot(fpr, tpr, label=f'{name}  AUC={roc_auc_score(y_te, p):.3f}', color=col, lw=2)
plt.plot([0, 1], [0, 1], ls=':', color='k', alpha=.4)
plt.gca().set(title='ROC-кривые на отложенной выборке', xlabel='FPR', ylabel='TPR', aspect='equal'); plt.legend(); plt.show()
"""),
    md("""
**Вывод.** LightGBM лучше бейзлайна, но **ненамного**: +0,01 ROC-AUC на кросс-валидации и +0,015
на отложенной выборке, PR-AUC 0,65 против 0,62. Зависимости здесь в основном простые и монотонные
(срок жизни, тип контракта, цена), и линейная модель ловит большую их часть. Выбор между моделями —
это компромисс: бустинг даёт немного больше точности, логистическая регрессия проще объясняется
бизнесу. Ниже для экономики использую LightGBM.
"""),
    md("## Что влияет на отток"),
    code("""
imp = pd.Series(gbm.booster_.feature_importance('gain'), index=X_tr_l.columns)
(imp / imp.sum()).sort_values().tail(10).plot.barh(color=GREEN)
plt.title('LightGBM: вклад признаков (gain)'); plt.show()
"""),
    md("## Экономика: кому делать предложение об удержании"),
    md("""
Допущения (их стоит согласовать с бизнесом):
* предложение стоит оператору **скидку в размере одного месячного платежа**;
* оно удерживает **30%** тех, кто действительно собирался уйти;
* удержанный абонент приносит ещё **12 месяцев** платы.

Сортируем абонентов по ожидаемой выгоде (вероятность × ценность) и ищем, скольким выгодно звонить.
"""),
    code("""
mc = X_te.MonthlyCharges.to_numpy(); yt = y_te.to_numpy()
def profit_curve(p, save_rate=0.30, months=12):
    order = np.argsort(-(p * mc))
    gain = yt[order] * save_rate * mc[order] * months - mc[order]
    return np.cumsum(gain)
curves = {'LightGBM': profit_curve(p_gb), 'LogReg': profit_curve(p_lr),
          'Случайно': profit_curve(np.random.default_rng(0).random(len(yt)))}
share = np.arange(1, len(yt) + 1) / len(yt)
for (n, c), col in zip(curves.items(), [GREEN, GREY, PURPLE]):
    plt.plot(share * 100, c / 1e3, label=n, color=col, lw=2)
plt.axhline(0, color='k', lw=.5)
plt.gca().set(title='Прибыль от кампании удержания, тыс. $', xlabel='% абонентов, которым сделали предложение', ylabel='тыс. $')
plt.legend(); plt.show()
best = curves['LightGBM'].argmax()
print(f'Оптимум: предложение {share[best]:.0%} абонентов с наибольшим риском × платежом, '
      f'прибыль {curves["LightGBM"][best]:,.0f} $ на {len(yt)} абонентов тестовой выборки')
for n, c in curves.items():
    print(f'{n:9s} максимум {c.max():>9,.0f} $   при охвате 38%: {c[best]:>9,.0f} $   всем: {c[-1]:>9,.0f} $')
"""),
    md("""
**Итог.** Если сделать предложение 38% абонентов, отобранных моделью, кампания приносит **~35 тыс. $**.
Это в **4,6 раза** больше, чем предложение всем подряд (~7,7 тыс. $), и при этом скидок раздаётся меньше.
Предложение выгодно делать не всем, а только верхней части списка по ожидаемой потере. Как и в моём
проекте на хакатоне, сортировать стоит по **деньгам** (риск × платёж), а не по одной вероятности.

**Ограничения:** датасет статичный (один срез без истории по месяцам), поэтому настоящую проверку по
времени здесь сделать нельзя. Как выглядела бы витрина с историей, показано в `sql/02_mart.sql`.
"""),
]


def build(cells, name):
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(NB)}})
    nbf.write(nb, NB / name)
    print("OK", name)


if __name__ == "__main__":
    build(analysis, "01_operator_analytics.ipynb")
    build(ml, "02_churn_model.ipynb")
