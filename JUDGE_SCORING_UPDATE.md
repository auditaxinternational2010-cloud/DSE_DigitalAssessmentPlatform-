# Judge scoring and administrator score dashboard update

- The judge entry label is now **Judge Score**.
- Judge scores are stored as decimals with up to two decimal places.
- Entries must be numeric (a `%` suffix or other non-numeric text is rejected), non-negative, and strictly greater than the criterion's assigned weight.
- There is no artificial upper limit on the score; the assigned criterion weight remains on its existing 0–100 percentage-point scale.
- The administrator navigation and dashboard include **Judges Dashboard Scores**.
- The new admin page groups individual judge scores by questionnaire template, organization, category and criterion, and shows criterion, category and questionnaire averages to two decimal places.
- Existing integer judge scores are preserved by migration `0021_judgeresponse_score_decimal` and become decimal values.

## Deployment

Run the migration after deploying the updated code:

```bash
docker compose exec web python manage.py migrate
```

Then run:

```bash
docker compose exec web python manage.py check
```

The project ZIP intentionally excludes `.env`, `.git`, `local_accounts.json`, Python cache files and database files. Keep your existing environment file and database backup.
