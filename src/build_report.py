"""Выполняет запросы из sql/03_analysis.sql в Oracle и собирает Excel-отчёт с графиками.

Запуск:  python src/build_report.py   -> reports/telecom_report.xlsx
"""
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from db import ROOT, connect, named_queries, query_df

SHEETS = {
    "q1_sales_by_salon_month": "Продажи по салонам",
    "q2_tariff_usage": "Тарифы",
    "q3_campaign_effect": "Акции удержания",
    "q4_cohort_retention": "Когорты",
    "q5_churn_by_salon": "Отток по салонам",
    "q6_churn_signal": "Сигнал оттока",
}
HEAD = PatternFill("solid", fgColor="00B956")


def write_df(ws, df, start_row=1):
    for j, c in enumerate(df.columns, 1):
        cell = ws.cell(start_row, j, c)
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), HEAD
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(j)].width = max(12, min(32, len(str(c)) + 4))
    for i, row in enumerate(df.itertuples(index=False), start_row + 1):
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, None if v != v else v)  # NaN -> пусто
            if hasattr(v, "strftime"):
                c.number_format = "mmm yyyy"
    ws.freeze_panes = ws.cell(start_row + 1, 1)


def main():
    out = ROOT / "reports" / "telecom_report.xlsx"
    qs = named_queries(ROOT / "sql" / "03_analysis.sql")
    results = {}
    with connect() as conn:
        for key in SHEETS:
            results[key] = query_df(conn, qs[key])

    wb = Workbook()
    wb.remove(wb.active)
    for key, title in SHEETS.items():
        ws = wb.create_sheet(title)
        write_df(ws, results[key])
        results[key].to_csv(ROOT / "reports" / f"{key}.csv", index=False)

    # Сводная выручка сети по месяцам (лист + линейный график)
    q1 = results["q1_sales_by_salon_month"]
    pivot = q1.pivot_table(index="month", columns="salon", values="revenue_tjs", aggfunc="sum").fillna(0)
    pivot["Итого по сети"] = pivot.sum(axis=1)
    ws = wb.create_sheet("Сводная выручка", 0)
    write_df(ws, pivot.reset_index().rename(columns={"month": "Месяц"}))
    n = len(pivot) + 1
    total_col = pivot.shape[1] + 1
    ch = LineChart()
    ch.title, ch.y_axis.title, ch.height, ch.width = "Выручка сети по месяцам, сомони", "сомони", 8, 18
    ch.add_data(Reference(ws, min_col=total_col, min_row=1, max_row=n), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=n))
    ws.add_chart(ch, f"B{n + 3}")

    def bar(sheet, cat_col, val_col, title, anchor):
        ws = wb[sheet]
        rows = ws.max_row
        b = BarChart()
        b.title, b.height, b.width, b.legend = title, 7, 16, None
        b.add_data(Reference(ws, min_col=val_col, min_row=1, max_row=rows), titles_from_data=True)
        b.set_categories(Reference(ws, min_col=cat_col, min_row=2, max_row=rows))
        ws.add_chart(b, anchor)

    bar("Отток по салонам", 1, 4, "Отток за 6 месяцев по салону подключения, %", "H2")
    bar("Тарифы", 1, 4, "ARPU по тарифам, сомони", "J2")
    bar("Акции удержания", 2, 5, "Отток за 3 мес. после контакта, %", "H2")
    out.parent.mkdir(exist_ok=True)
    wb.save(out)
    print("Сохранено:", out)
    for key in ["q2_tariff_usage", "q3_campaign_effect", "q4_cohort_retention", "q5_churn_by_salon", "q6_churn_signal"]:
        print(f"\n== {key}\n{results[key].to_string(index=False)}")


if __name__ == "__main__":
    main()
