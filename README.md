# DSE Questionnaire System

A comprehensive Django-based organizational assessment questionnaire system.

## Quick Start

```bash
# 1. Copy project files
# 2. Start Docker
docker-compose up --build

# 3. Access app at http://localhost:8000
```

## Features

- 10 Assessment Categories (94 Criteria total)
- 0-5 Level Scoring System with detailed indicators
- Weighted scoring calculation
- Multi-step questionnaire filling
- Results dashboard with category breakdowns
- Full assessment framework table view
- Django Admin for data management
- PostgreSQL database via Docker

## Documentation

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for complete setup instructions.


## Assessment criterion weights
Criterion weights are stored as percentage points from 0 to 100 and displayed with a `%` sign throughout the member, Secretariat/Judge, and reporting screens. Workbook imports accept either fractional values (for example `0.25` = `25%`) or percentage values (`25` / `25%`).

## Registration questionnaire selection update

Registration requests now allow applicants to select one or more active questionnaire templates in the currently open award cycle. The selected templates are included in the administrator notification email. On approval, the system reuses an organization with a matching name (case-insensitive) without overwriting its existing details, creates the applicant's member account, assigns one questionnaire per selected template, and emails the supplied address with login credentials and the assigned questionnaire list.

Apply the database migrations before starting the updated app:

```bash
python manage.py migrate
```

New migrations:
- `accounts.0015_participationrequest_questionnaires`
- `assessment.0020_questionnaire_unique_per_template`

Email delivery depends on the deployment's Django email settings. The new selection list is saved even if an email server is temporarily unavailable; failed sends are logged in Email Logs.
