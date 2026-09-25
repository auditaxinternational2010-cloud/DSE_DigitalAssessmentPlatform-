"""Import an assessment workbook into a cycle.

Usage: python import_dse_excel.py path/to/workbook.xlsx 2026
Run from the project root in the same environment as manage.py.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "eya_questionnaire.settings")
import django
django.setup()

from assessment.models import AwardCycle
from assessment.excel_parser import parse_excel_questionnaire
from django.core.files import File


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python import_dse_excel.py WORKBOOK.xlsx YEAR")
    path, year_text = sys.argv[1], sys.argv[2]
    if not os.path.isfile(path):
        raise SystemExit(f"Workbook not found: {path}")
    try:
        year = int(year_text)
    except ValueError:
        raise SystemExit("YEAR must be an integer")
    cycle, _ = AwardCycle.objects.get_or_create(year=year, defaults={"name": f"{year} DSE Assessment"})
    with open(path, "rb") as source:
        warnings = parse_excel_questionnaire(File(source, name=os.path.basename(path)), cycle)
    for warning in warnings:
        print(warning)
    print(f"Import completed for {cycle.name}.")

if __name__ == "__main__":
    main()
