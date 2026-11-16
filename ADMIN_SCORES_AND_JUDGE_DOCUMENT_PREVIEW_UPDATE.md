# Admin Judge Score Summary and Judge Evidence Preview

## Admin Judges Dashboard Scores
- Added an aggregate table with one row per judge and questionnaire.
- Columns: Judge Name, Organization, Questionnaire Template, Score, Total Score, Average.
- Score is the sum of that judge's entered criterion scores for the questionnaire.
- Total Score is the sum of the applicable scorable criterion weights.
- Average is Score divided by Total Score, expressed as a percentage and rounded to two decimal places.
- Existing category and criterion-level score detail and averages remain below the summary.

## Judge evidence review
- Member evidence now has separate Preview and Download actions on the judge questionnaire page.
- Preview serves files inline (or requests an inline S3/Spaces URL) after the existing permission check.
- Download remains an explicit attachment action.
- PDF and image files are normally viewable directly in modern browsers. Word and Excel preview depends on browser support; the inline response does not convert Office documents to PDF.

No database schema changes or migrations are required.
