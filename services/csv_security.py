"""Protect spreadsheet consumers from formula injection in CSV exports."""


def safe_csv_cell(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("\t", "\r")) or text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def safe_csv_row(values):
    return [safe_csv_cell(value) for value in values]
