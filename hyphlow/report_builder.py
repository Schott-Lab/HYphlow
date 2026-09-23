import pandas as pd

from hyphlow import common_utils

BOLD = {"bold": True}
GREEN = {"bg_color": "#EBF9EE", "font_color": "#16A34A", "bold": True}
RED = {"bg_color": "#FFECEB", "font_color": "#FF3B30", "bold": True}
ORANGE = {"bg_color": "#FFF9E5", "font_color": "#FF9500", "bold": True}

SUMMARY_SHEET = "Summary"
DETAIL_SHEET = "Detailed Report"

_TINTS = {"green": GREEN, "red": RED, "orange": ORANGE}


def build_report(
    path,
    title,
    source,
    output,
    stats,
    rows=None,
    columns=None,
    color_column=None,
    color_map=None,
    widths=None,
    int_columns=None,
):
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        book = writer.book
        bold = book.add_format(BOLD)
        fmts = {name: book.add_format(spec) for name, spec in _TINTS.items()}

        _write_summary(book, bold, fmts, title, source, output, stats)
        if rows and columns:
            _write_detail(
                writer,
                fmts,
                rows,
                columns,
                color_column,
                color_map,
                widths,
                int_columns,
            )


def _write_summary(book, bold, fmts, title, source, output, stats):
    ws = book.add_worksheet(SUMMARY_SHEET)
    ws.set_column("A:B", 30)

    ws.write("A1", f"HYphlow {title} Report", bold)
    ws.write("A2", "Date & Time", bold)
    ws.write("B2", common_utils.timestamp())
    ws.write("A3", "Source File", bold)
    ws.write("B3", source)
    ws.write("A4", "Output File", bold)
    ws.write("B4", output)

    ws.write("A6", "--- Statistics ---", bold)
    for i, entry in enumerate(stats, start=7):
        label, value = entry[0], entry[1]
        tint = entry[2] if len(entry) > 2 else None
        ws.write(f"A{i}", label, bold)
        ws.write(f"B{i}", value, fmts.get(tint) if tint else None)


def _write_detail(
    writer, fmts, rows, columns, color_column, color_map, widths, int_columns
):
    df = pd.DataFrame(rows, columns=columns)
    for name in int_columns or ():
        df[name] = df[name].astype("Int64")
    df.to_excel(writer, sheet_name=DETAIL_SHEET, index=False)
    ws = writer.sheets[DETAIL_SHEET]

    for spec, width in (widths or {"A:Z": 30}).items():
        ws.set_column(spec, width)

    if not (color_column and color_map):
        return

    col = chr(ord("A") + columns.index(color_column))
    cells = f"{col}2:{col}{len(rows) + 1}"
    for value, tint in color_map.items():
        ws.conditional_format(
            cells,
            {
                "type": "cell",
                "criteria": "==",
                "value": f'"{value}"',
                "format": fmts[tint],
            },
        )
