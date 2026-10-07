# Assessment Criterion Weight Update

The assessment system now treats **Criterion Weight** as a percentage from **0% to 100%**.

Examples:
- `0.25` in an imported workbook becomes `25%`.
- `25` remains `25%`.
- `25%` remains `25%`.

The scoring scale remains 0–5. Existing weighted-score calculations continue to work because they normalize the percentage weights. A new data migration converts existing fractional criterion weights to percentage points.

Migration: `assessment.0019_criterion_weight_percentage`
