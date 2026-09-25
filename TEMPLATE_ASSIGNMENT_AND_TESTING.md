# Reusable questionnaire templates: setup and verification

## Data model

- `AwardCycle` owns reusable `QuestionnaireTemplate` records.
- Each template has a stable code/profile and contains its own assessment categories.
- Each organization has at most one `Questionnaire` per cycle; that questionnaire points to the selected template.
- Responses, Secretariat records and judge records remain attached to the organization-specific questionnaire, not to the shared template.
- Importing a workbook creates/updates a template for each recognized assessment-profile sheet and associates imported categories with that template.

## Local Docker checks

Run these from the directory containing `docker-compose.yml`:

```bash
docker compose config
docker compose ps
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py migrate --plan
```

If the migration plan is expected, apply it:

```bash
docker compose exec web python manage.py migrate
```

Then run tests:

```bash
docker compose exec web python manage.py test accounts assessment share audit
```

If the app labels differ in your checkout, use `python manage.py test` to run the full suite.

## Workflow smoke test

1. Create or select an award cycle and upload the workbook while the cycle is closed.
2. Confirm each recognized profile appears as a reusable template in Django Admin.
3. Create two test organizations that should use the same template and one organization that should use a different template.
4. Open the cycle. Opening a cycle does not automatically assign questionnaires.
5. On the cycle page, assign each organization and explicitly select its template.
6. Log in as each member and confirm only their organization’s questionnaire is available and the criteria match its assigned template.
7. Enter responses and attach evidence; submit as the member.
8. Log in as Secretariat and confirm the submitted questionnaire is available for review, without adding a Secretariat score unless the workflow explicitly requires one. Add notes/coverage and submit the Secretariat stage.
9. Log in as each judge. Confirm each judge can enter scores/comments and optional Excel attachments, but cannot see another judge’s scores/comments.
10. Confirm results remain hidden from Member and Secretariat until the cycle is closed, according to the configured workflow.
11. Close the cycle; verify aggregate results and rankings only compare organizations assigned to the same questionnaire template.
12. Repeat with an organization assigned to a different template and verify its criteria and ranking cohort remain separate.

## Database safety

Back up the database before applying migrations. Do not use `docker compose down -v` unless you intentionally want to delete the local PostgreSQL volume and all data stored in it.
