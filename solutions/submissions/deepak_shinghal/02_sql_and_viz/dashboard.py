"""Create the annotated PDF dashboard required by Task 2.4."""

import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

# Use a writable cache folder on this managed machine; use a file-only backend.
os.environ.setdefault(
    "MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "presight-pillar2-matplotlib")
)
os.environ.setdefault(
    "XDG_CACHE_HOME", os.path.join(tempfile.gettempdir(), "presight-pillar2-cache")
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


def format_millions(value, position):
    return f"{value / 1e6:.0f}M"


def create_dashboard(connection, projects, results, output):
    # Dashboard needs ALL departments, not only those passing Q1's >90% filter.
    departments = pd.read_sql_query(
        """SELECT department, SUM(budget) AS budget,
       SUM(actual_cost) AS spend FROM dim_project GROUP BY department ORDER BY budget""",
        connection,
    )
    # Likewise vendor distribution uses all vendors BEFORE Q3's risk threshold.
    vendors = pd.read_sql_query(
        """SELECT v.vendor_id, v.vendor_name, SUM(f.amount) AS spend
       FROM fact_transactions f JOIN dim_vendor v USING(vendor_key)
       WHERE f.currency='AED' GROUP BY v.vendor_key ORDER BY spend DESC, v.vendor_id""",
        connection,
    )
    transaction_count = connection.execute(
        "SELECT COUNT(*) FROM fact_transactions"
    ).fetchone()[0]
    trend = results["Q5"].copy()
    trend["date"] = pd.to_datetime(trend["year_month"] + "-01")
    date_bounds = connection.execute(
        "SELECT MIN(d.full_date), MAX(d.full_date) FROM fact_transactions f JOIN dim_date d USING(date_key)"
    ).fetchone()
    source_range = date_bounds[0] + " to " + date_bounds[1]
    top_projects = projects.sort_values("budget_variance", ascending=False).head(10)
    budget = projects["budget"].sum()
    actual = projects["actual_cost"].sum()
    over_budget_pct = projects["is_over_budget"].mean() * 100

    departments.to_csv(output / "dashboard_department_data.csv", index=False)
    vendors.to_csv(output / "dashboard_vendor_data.csv", index=False)
    top_projects.to_csv(output / "dashboard_top_projects.csv", index=False)
    metrics = pd.DataFrame(
        [
            {
                "total_budget": budget,
                "total_actual_spend": actual,
                "over_budget_projects_pct": over_budget_pct,
                "total_transactions": transaction_count,
            }
        ]
    )
    metrics.to_csv(output / "dashboard_kpis.csv", index=False)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    figure = plt.figure(figsize=(17, 12), facecolor="#f4f6fa")
    grid = figure.add_gridspec(
        2, 2, left=0.065, right=0.96, bottom=0.105, top=0.71, hspace=0.80, wspace=0.29
    )
    date_label = datetime.now(ZoneInfo("Asia/Dubai")).strftime("%d %B %Y")
    figure.text(
        0.045,
        0.965,
        "PRESIGHT | Project Spend Performance",
        fontsize=23,
        weight="bold",
        color="#14243b",
    )
    figure.text(
        0.045,
        0.935,
        "Deepak Shinghal  •  " + date_label + "  •  Executive dashboard mockup",
        color="#526179",
    )
    figure.text(
        0.045,
        0.905,
        "Scope: all source projects and transactions. Amounts in AED; transactions "
        + source_range
        + ".",
        color="#526179",
    )

    # Static mockup controls: clear chosen values and explicit filter design.
    for x, label in [
        (0.045, "Region: All  ▾"),
        (0.27, "Project status: All  ▾"),
        (0.56, "Transaction year: All  ▾"),
    ]:
        figure.text(
            x,
            0.865,
            label,
            fontsize=11,
            bbox={
                "boxstyle": "round,pad=.6",
                "facecolor": "white",
                "edgecolor": "#d4dce8",
            },
        )
    figure.text(
        0.045,
        0.828,
        "Slicer design: region/status filter related projects and facts; year filters transaction charts/counts only.",
        fontsize=8,
        color="#526179",
    )

    cards = [
        (f"{budget / 1e6:,.1f}M", "Total allocated budget"),
        (f"{actual / 1e6:,.1f}M", "Total actual project spend"),
        (f"{over_budget_pct:.1f}%", "Projects over budget"),
        (f"{transaction_count:,}", "Total transactions"),
    ]
    for index, (value, label) in enumerate(cards):
        x = 0.055 + index * 0.235
        figure.text(x, 0.78, value, fontsize=24, weight="bold", color="#14243b")
        figure.text(x, 0.754, label, fontsize=9, color="#526179")

    bar = figure.add_subplot(grid[0, 0])
    bar.set_title(
        "Budget vs actual spend by department", loc="left", weight="bold", pad=12
    )
    positions = range(len(departments))
    budget_positions = []
    spend_positions = []
    for position in positions:
        budget_positions.append(position - 0.18)
        spend_positions.append(position + 0.18)
    bar.barh(
        budget_positions,
        departments["budget"],
        height=0.34,
        color="#9ac4e6",
        label="Budget",
    )
    bar.barh(
        spend_positions,
        departments["spend"],
        height=0.34,
        color="#246aaa",
        label="Actual",
    )
    bar.set_yticks(list(positions), departments["department"])
    bar.xaxis.set_major_formatter(FuncFormatter(format_millions))
    bar.set_xlabel("AED millions")
    bar.legend(loc="lower right", frameon=False)
    bar.text(
        0,
        -0.26,
        "Paired bars compare spending with allocation. Uses Q1 aggregation before its >90% filter.",
        transform=bar.transAxes,
        fontsize=8,
        color="#526179",
    )

    line = figure.add_subplot(grid[0, 1])
    line.set_title(
        "Monthly transaction spend by category", loc="left", weight="bold", pad=12
    )
    categories = trend["category"].drop_duplicates().tolist()
    colours = plt.get_cmap("tab20")
    for index, category in enumerate(categories):
        category_rows = trend[trend["category"] == category]
        line.plot(
            category_rows["date"],
            category_rows["monthly_spend"] / 1e6,
            label=category,
            linewidth=1.2,
            color=colours(index % 20),
        )
    line.set_ylabel("AED millions")
    line.grid(axis="y", alpha=0.18)
    line.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=3,
        fontsize=6.5,
        frameon=False,
    )
    line.tick_params(axis="x", labelsize=8)
    line.text(
        0,
        -0.57,
        "Lines reveal monthly trends; every category is shown. Source: Q5 monthly_spend.",
        transform=line.transAxes,
        fontsize=8,
        color="#526179",
    )

    table_axis = figure.add_subplot(grid[1, 0])
    table_axis.set_title(
        "Top 10 projects by budget variance", loc="left", weight="bold", pad=12
    )
    table_axis.axis("off")
    table_rows = []
    for row in top_projects.itertuples():
        table_rows.append(
            [
                row.project_id,
                row.project_name[:32],
                f"{row.budget / 1e6:.2f}",
                f"{row.actual_cost / 1e6:.2f}",
                f"{row.budget_variance / 1e6:+.2f}",
            ]
        )
    table = table_axis.table(
        cellText=table_rows,
        colLabels=["Project ID", "Project name", "Budget M", "Actual M", "Variance M"],
        colWidths=[0.14, 0.43, 0.14, 0.14, 0.15],
        loc="upper center",
        cellLoc="left",
        bbox=[0, 0.02, 1, 0.92],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(7.5)
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor("#e4e9f0")

        if row == 0:
            background = "#14243b"
        elif row % 2 == 0:
            background = "#edf2f8"
        else:
            background = "white"
        cell.set_facecolor(background)
        if row == 0:
            cell.get_text().set_color("white")
    table_axis.text(
        0,
        -0.11,
        "Table names the largest overspends (actual − budget), sorted descending. Values: AED millions.",
        transform=table_axis.transAxes,
        fontsize=8,
        color="#526179",
    )

    donut = figure.add_subplot(grid[1, 1])
    donut.set_title(
        "Vendor concentration | Top 5 + Other", loc="left", weight="bold", pad=12
    )
    top_vendors = vendors.head(5)
    values = top_vendors["spend"].tolist() + [vendors.iloc[5:]["spend"].sum()]
    labels = (top_vendors["vendor_id"] + " " + top_vendors["vendor_name"]).tolist() + [
        "Other"
    ]
    wedges, texts, percentages = donut.pie(
        values,
        startangle=90,
        autopct="%1.1f%%",
        colors=["#246aaa", "#388ebd", "#58b0c9", "#75c7cf", "#aadbd7", "#dce4ed"],
        wedgeprops={"width": 0.36, "edgecolor": "white"},
        pctdistance=0.81,
        textprops={"fontsize": 8},
    )
    donut.text(
        0,
        0,
        f"{vendors.spend.sum() / 1e9:.2f}B\nAED transactions",
        ha="center",
        va="center",
        fontsize=11,
    )
    donut.legend(
        wedges,
        labels,
        loc="center left",
        bbox_to_anchor=(0.94, 0.5),
        fontsize=7,
        frameon=False,
    )
    donut.text(
        -0.03,
        -0.14,
        "Donut shows spend shares across all vendors using Q3 logic before the >5% filter.",
        transform=donut.transAxes,
        fontsize=8,
        color="#526179",
    )

    figure.text(
        0.045,
        0.045,
        "KPI purpose: scale of allocation, actual costs, overspend exposure and transaction volume. "
        "Project actual_cost and transaction spend are different source measures.\n"
        "PDF controls are illustrative (not interactive). Null transaction amounts are excluded from monetary sums; "
        "unknown values remain in source CSVs. Snapshot budgets have no year allocation.",
        fontsize=8,
        color="#526179",
        linespacing=1.6,
    )

    figure.savefig(output / "dashboard_mockup.pdf", facecolor=figure.get_facecolor())
    figure.savefig(
        output / "dashboard_preview.png", dpi=110, facecolor=figure.get_facecolor()
    )
    plt.close(figure)
