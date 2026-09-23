"""Import the DSE assessment workbook format.

Workbook layout:
  Sheet = assessment profile (Bond Issuer, Bond Trader, ...)
  Row 9 = headers
  Row 10+ = measurable parameters

Columns:
  A Code, B Assessment Category, C S/N, D Assessment Areas,
  E S/N, F Assessment Criteria, G S/N, H Measurable Parameters,
  I Relevant CMSA Act / Guideline / DSE Rule / Regulation,
  J Weight (%), K Response, L Remarks, M Score.

The Response/Remarks/Score columns are intentionally NOT imported as template
content: they are populated by Member, Secretariat and Judges respectively.
"""

import os
from decimal import Decimal, InvalidOperation

import openpyxl

from .models import AssessmentCategory, Criterion, LevelIndicator

PROFILE_MAP = {
    'bond issuer': 'bond_issuer',
    'bond trader': 'bond_trader',
    'custodian': 'custodian',
    'egm': 'egm',
    'mims': 'mims',
    'mims ': 'mims',
    'nomads': 'nomads',
    'ldms': 'ldms',
    'ldm': 'ldms',
}

DASHBOARD_SHEET = 'assement dashboard'


def _text(value):
    return str(value).strip() if value is not None else ''


def _decimal(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        d = Decimal(str(value).replace('%', '').strip())
        # The supplied workbook stores 0.01 for 1%, so preserve the value.
        return d
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _profile_from_sheet(name):
    return PROFILE_MAP.get(_text(name).lower())


def _load_rows(file_obj):
    """Return (sheet_name, rows) pairs for xlsx and legacy xls files."""
    ext = os.path.splitext(getattr(file_obj, 'name', ''))[1].lower()
    try:
        file_obj.seek(0)
    except Exception:
        pass

    if ext == '.xls':
        try:
            import xlrd
        except ImportError:
            raise RuntimeError('Legacy .xls support requires xlrd. Install xlrd>=2.0.1.')
        book = xlrd.open_workbook(file_contents=file_obj.read())
        result = []
        for sheet in book.sheets():
            result.append((sheet.name, [sheet.row_values(r) for r in range(sheet.nrows)]))
        return result

    wb = openpyxl.load_workbook(file_obj, data_only=True)
    return [(ws.title, list(ws.iter_rows(values_only=True))) for ws in wb.worksheets]


def parse_excel_questionnaire(file_obj, cycle):
    warnings = []
    try:
        sheets = _load_rows(file_obj)
    except Exception as exc:
        return [f'Could not read Excel file: {exc}']

    imported_profiles = set()
    imported_categories = 0
    imported_parameters = 0

    for sheet_order, (sheet_name, rows) in enumerate(sheets):
        profile = _profile_from_sheet(sheet_name)
        if not profile:
            if _text(sheet_name).lower() != DASHBOARD_SHEET:
                warnings.append(f"Sheet '{sheet_name}' is not a recognised DSE assessment profile and was skipped.")
            continue

        imported_profiles.add(profile)
        # This upload is the source of truth for this profile in this cycle.
        # Deactivate old profile sections first; historical responses remain intact.
        AssessmentCategory.objects.filter(
            cycle=cycle, assessment_profile=profile
        ).update(is_active=False)
        # Workbook has its table header on row 9 (1-based), i.e. index 8.
        data_rows = rows[9:] if len(rows) > 9 else []
        current_category = None
        current_category_code = ''
        current_category_name = ''
        current_category_weight = Decimal('0')
        category_order = 0
        seen_categories = set()
        seen_parameters = set()

        for raw in data_rows:
            row = list(raw) + [None] * max(0, 13 - len(raw))
            code = _text(row[0])
            category_name = _text(row[1])
            area_no = _text(row[2])
            area_name = _text(row[3])
            criterion_no = _text(row[4])
            criterion_name = _text(row[5])
            parameter_no = _text(row[6])
            parameter_name = _text(row[7])
            regulation = _text(row[8])
            weight = _decimal(row[9])

            # Sub-total / grand-total rows are not assessment parameters.
            if any('total' == x.lower().strip() or x.lower().strip().endswith('total')
                   for x in (code, category_name, area_name, criterion_name, parameter_name)
                   if x):
                continue

            # A category starts when the code/category are supplied. The workbook
            # only repeats them on the first row of each category.
            if code and category_name:
                current_category_code = code
                current_category_name = category_name
                current_category_weight = weight
                category_order += 1
                current_category, _ = AssessmentCategory.objects.update_or_create(
                    cycle=cycle,
                    assessment_profile=profile,
                    code=code,
                    defaults={
                        'name': category_name,
                        'weight': weight,
                        'order': category_order,
                        'is_active': True,
                        'is_informal_sector_only': False,
                    },
                )
                seen_categories.add(current_category.pk)
                imported_categories += 1

            if not current_category:
                continue

            # Every populated parameter row becomes one Criterion record. The
            # existing model name is retained for compatibility with workflow,
            # while the fields below expose the workbook's true hierarchy.
            if not parameter_no or not parameter_name:
                continue

            # Excel occasionally repeats the category code but not the name.
            if not code:
                code = current_category_code
            parameter_key = (current_category.pk, parameter_no)
            if parameter_key in seen_parameters:
                warnings.append(f"Duplicate measurable parameter '{parameter_no}' in '{sheet_name}' was skipped.")
                continue
            seen_parameters.add(parameter_key)

            obj, _ = Criterion.objects.update_or_create(
                category=current_category,
                number=parameter_no,
                defaults={
                    'name': parameter_name,
                    'description': criterion_name,
                    'area_code': area_no,
                    'assessment_area': area_name,
                    'assessment_criterion_code': criterion_no,
                    'assessment_criterion': criterion_name,
                    'regulation': regulation,
                    'weight': weight,
                    'order': imported_parameters + 1,
                    'is_active': True,
                    'is_numeric': False,
                    'numeric_fields': [],
                },
            )
            # The old level model is not used for this workbook format.
            LevelIndicator.objects.filter(criterion=obj).delete()
            imported_parameters += 1

        # Deactivate old criteria in this profile/category that disappeared from
        # the latest workbook import, without deleting historical responses.
        for cat_id in seen_categories:
            cat = AssessmentCategory.objects.get(pk=cat_id)
            active_numbers = [
                number for (cid, number) in seen_parameters if cid == cat_id
            ]
            if active_numbers:
                Criterion.objects.filter(category=cat).exclude(number__in=active_numbers).update(is_active=False)

    if not imported_profiles:
        warnings.append('No recognised DSE assessment profile sheets were found.')
    else:
        warnings.append(
            f'Imported {imported_parameters} measurable parameters across {len(imported_profiles)} DSE assessment profiles.'
        )
    return warnings
