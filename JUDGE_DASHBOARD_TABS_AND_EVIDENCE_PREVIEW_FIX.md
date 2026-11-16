# Judge Dashboard Tabs and Evidence Preview Fix

## Judge dashboard
- Added clickable tabs for each questionnaire template in the open cycle.
- Each template card shows active judges available to assess it, questionnaires ready for the current judge, questionnaires completed by the current judge, questionnaires completed by at least one other judge, and distinct organizations.
- Selecting a template filters the organization/questionnaire table to that template.
- The current workflow has no separate per-template judge-assignment model: all active judge accounts can assess all eligible submitted questionnaires. Therefore, "Judges assigned" represents the active judge accounts available in this workflow.

## Evidence preview
- Judges are authorized to view evidence linked to submitted questionnaires whose organizations require judging.
- Evidence preview/download is streamed through Django's configured storage backend rather than redirecting the browser to a storage-generated S3/Spaces URL. This avoids failures caused by browser-facing signed preview URLs.
- Preview is inline; download remains an attachment.

## Database
- No database migration is required.

## Validation
- Python source compilation passed.
- A full Django runtime check could not be run in the packaging environment because Django is not installed there. Run `python manage.py check` or `docker compose exec web python manage.py check` in the project environment before deployment.
