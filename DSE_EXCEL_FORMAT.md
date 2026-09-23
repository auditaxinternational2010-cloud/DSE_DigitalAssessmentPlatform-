# DSE Assessment Excel Format

The assessment importer now follows the supplied DSE workbook.

## Workbook structure

The `Assement Dashboard` sheet is informational. The assessment sheets are:

- Bond Issuer
- Bond Trader
- Custodian
- EGM
- MIMs
- NOMADs
- LDMs

Each assessment sheet uses the table beginning at row 9:

| Column | Meaning | System field |
|---|---|---|
| A | Code | Assessment Category code |
| B | Assessment Category | Assessment Category name |
| C | S/N | Assessment Area number |
| D | Assessment Areas | Assessment Area |
| E | S/N | Assessment Criteria number |
| F | Assessment Criteria | Assessment Criteria |
| G | S/N | Measurable Parameter code |
| H | Measurable Parameters | Measurable Parameter |
| I | Relevant CMSA Act / Guideline / DSE Rule / Applicable Regulation | Regulation/reference |
| J | Weight (%) | Parameter weight |
| K | Response | Filled by Member in the system |
| L | Remarks | Filled by Secretariat in the system |
| M | Score | Filled by Judges in the system |

## Workflow retained

The application still follows:

**Member → Secretariat → Judges → Final Results**

- Member enters `Response` and evidence.
- Secretariat does **not** score. Secretariat enters `Remarks` and may attach evidence to a specific measurable parameter.
- Judges independently enter a score from 0–5, comments and an optional Excel attachment.
- A judge cannot see another judge's score or comments.
- Secretariat and Member cannot see judge marks/comments while the cycle is open.
- When the cycle is closed, judge results are revealed to authorised Secretariat/admin views and final results are calculated.
- Final parameter results use the average of the submitted judge scores.
- Parameter weights from column J and category weights from the workbook are used in final weighted results.

## Organisation assessment profile

Each organisation must have the matching assessment profile selected in the Organisation form:

- Bond Issuer
- Bond Trader
- Custodian
- EGM
- MIMs
- NOMADs
- LDMs

This prevents an organisation from receiving another participant class's assessment criteria.

## Excel upload

Both `.xlsx` and legacy `.xls` files are accepted. The project now includes `xlrd` for reading `.xls` files.

The `Response`, `Remarks`, and `Score` columns are template/output columns. The importer uses the assessment structure and does not overwrite user workflow responses with blank template cells.
