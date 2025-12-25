#!/usr/bin/env python3
from pathlib import Path
import os
import pandas as pd

TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Readmit30 Leaderboard</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #ddd; padding: 0.5rem; text-align: left; }
    th { position: sticky; top: 0; background: #fff; }
    .small { color: #666; font-size: 0.9rem; }
    .ok { color: #0a0; font-weight: 600; }
    .err { color: #a00; font-weight: 600; }
  </style>
</head>
<body>
  <h1>Readmit30 Leaderboard</h1>
  <p class="small">Primary metric: AUROC. Tie-breakers: AUPRC, then Brier (lower is better).</p>
  {table}
  <p class="small">Updated from <code>leaderboard/leaderboard.csv</code>.</p>
</body>
</html>
"""

IMG_OUT = Path("docs/leaderboard.png")
IMG_MAX_ROWS = int(os.getenv("LEADERBOARD_IMAGE_ROWS", "25"))  # top N rows in PNG
IMG_DPI = int(os.getenv("LEADERBOARD_IMAGE_DPI", "200"))       # PNG resolution

def render_leaderboard_image(df_sorted: pd.DataFrame, out_png: Path, max_rows: int = 25, dpi: int = 200) -> None:
    """
    Render a PNG image of the leaderboard table (for README embedding).
    Uses matplotlib in headless mode.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless/CI-safe
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"Skipping image render (matplotlib unavailable): {e}")
        return

    out_png.parent.mkdir(parents=True, exist_ok=True)

    if df_sorted is None or df_sorted.empty:
        fig, ax = plt.subplots(figsize=(7, 1.6))
        ax.axis("off")
        ax.text(0.5, 0.5, "No submissions yet.", ha="center", va="center", fontsize=14)
        fig.savefig(out_png, dpi=dpi, bbox_inches="tight", pad_inches=0.25)
        plt.close(fig)
        return

    # Limit rows for a reasonable README image
    df_img = df_sorted.head(max_rows).copy() if max_rows and len(df_sorted) > max_rows else df_sorted.copy()

    # Format numeric columns nicely for display
    for col in df_img.columns:
        if pd.api.types.is_numeric_dtype(df_img[col]):
            df_img[col] = df_img[col].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")

    # Ensure everything is text for matplotlib's table
    df_img = df_img.astype(str)

    nrows, ncols = df_img.shape

    # Heuristic figure sizing (inches)
    fig_w = max(7.5, ncols * 1.6)
    fig_h = max(2.0, (nrows + 1) * 0.55)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.axis("off")

    tbl = ax.table(
        cellText=df_img.values,
        colLabels=list(df_img.columns),
        cellLoc="left",
        colLoc="left",
        loc="center",
    )

    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.4)

    # Header styling
    for c in range(ncols):
        cell = tbl[(0, c)]
        cell.set_text_props(weight="bold")
        cell.set_facecolor("#f2f2f2")
        cell.set_edgecolor("#dddddd")
        cell.set_linewidth(1.0)

    # Body styling (zebra stripes + status color)
    status_col = None
    if "status" in df_img.columns:
        status_col = list(df_img.columns).index("status")

    for r in range(1, nrows + 1):
        for c in range(ncols):
            cell = tbl[(r, c)]
            cell.set_edgecolor("#eeeeee")
            cell.set_linewidth(0.5)

            # zebra stripes
            cell.set_facecolor("#fbfbfb" if (r % 2 == 0) else "white")

            # colorize status
            if status_col is not None and c == status_col:
                status = df_img.iloc[r - 1, c]
                if status == "OK":
                    cell.get_text().set_color("#0a0")
                    cell.get_text().set_weight("bold")
                else:
                    cell.get_text().set_color("#a00")
                    cell.get_text().set_weight("bold")

    title = "Readmit30 Leaderboard"
    if max_rows and len(df_sorted) > max_rows:
        title += f" (Top {max_rows} of {len(df_sorted)})"
    fig.suptitle(title, fontsize=14, y=0.98)

    foot = "Primary metric: AUROC. Tie-breakers: AUPRC, then Brier (lower is better)."
    fig.text(0.5, 0.015, foot, ha="center", va="bottom", fontsize=9, color="#666666")

    fig.savefig(out_png, dpi=dpi, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def main():
    lb_csv = Path("leaderboard/leaderboard.csv")
    out_html = Path("docs/index.html")
    out_html.parent.mkdir(parents=True, exist_ok=True)

    if not lb_csv.exists():
        out_html.write_text(TEMPLATE.replace("{table}", "<p>No submissions yet.</p>"), encoding="utf-8")
        render_leaderboard_image(pd.DataFrame(), IMG_OUT, max_rows=IMG_MAX_ROWS, dpi=IMG_DPI)
        print(f"Wrote {out_html} (empty)")
        print(f"Wrote {IMG_OUT} (empty)")
        return

    df = pd.read_csv(lb_csv)

    # Sort: AUROC desc, AUPRC desc, Brier asc (NaNs go last)
    for col in ["auroc", "auprc", "brier"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    sort_cols = [c for c in ["auroc", "auprc", "brier"] if c in df.columns]
    sort_asc = [False, False, True][: len(sort_cols)]  # matches the above order
    df_sorted = df.sort_values(by=sort_cols, ascending=sort_asc) if sort_cols else df

    # HTML version gets colored status spans; image version uses plain "OK"/other text
    df_html = df_sorted.copy()
    if "status" in df_html.columns:
        df_html["status"] = df_html["status"].apply(
            lambda s: "<span class='ok'>OK</span>" if s == "OK" else f"<span class='err'>{s}</span>"
        )

    table_html = df_html.to_html(index=False, escape=False)
    html = TEMPLATE.replace("{table}", table_html)
    out_html.write_text(html, encoding="utf-8")
    print(f"Wrote {out_html}")

    render_leaderboard_image(df_sorted, IMG_OUT, max_rows=IMG_MAX_ROWS, dpi=IMG_DPI)
    print(f"Wrote {IMG_OUT}")


if __name__ == "__main__":
    main()
