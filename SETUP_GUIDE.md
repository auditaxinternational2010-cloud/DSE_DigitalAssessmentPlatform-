# DSE Questionnaire System - Complete Setup Guide

## Project Overview

A Django-based questionnaire assessment system with PostgreSQL (Docker), covering 10 assessment categories with 94 criteria, each scored on a 0-5 level scale.

## Folder Structure

```
eya_questionnaire/
├── docker-compose.yml          # Docker orchestration
├── Dockerfile                  # Django app container
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables
├── .env.example               # Environment template
├── manage.py                  # Django management script
├── eya_questionnaire/         # Project settings
│   ├── __init__.py
│   ├── settings.py            # Main configuration
│   ├── urls.py               # URL routing
│   ├── wsgi.py
│   └── asgi.py
├── assessment/               # Main application
│   ├── __init__.py
│   ├── admin.py              # Django admin config
│   ├── apps.py
│   ├── models.py             # Database models
│   ├── views.py              # All views
│   ├── urls.py               # App URLs
│   ├── forms.py              # Django forms
│   ├── serializers.py        # DRF serializers (future API)
│   ├── tests.py              # Unit tests
│   ├── templatetags/         # Custom template filters
│   │   ├── __init__.py
│   │   └── assessment_extras.py
│   ├── management/
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── seed_questionnaire.py    # Data seeder
│   │       └── questionnaire_data.json  # All 94 criteria data
│   ├── templates/
│   │   └── assessment/
│   │       ├── home.html
│   │       ├── questionnaire_list.html
│   │       ├── questionnaire_form.html
│   │       ├── questionnaire_detail.html
│   │       ├── questionnaire_fill.html
│   │       ├── questionnaire_results.html
│   │       └── assessment_table.html
│   └── static/
│       └── assessment/
│           └── css/
│               └── styles.css
├── templates/                # Global templates
│   └── base.html            # Base layout
└── static/                   # Global static files
    └── css/
        └── main.css
```

## Step-by-Step Setup Instructions

### Step 1: Prerequisites

Ensure you have installed:
- Docker Desktop (Windows/Mac) or Docker Engine + Docker Compose (Linux)
- Git (optional, for version control)

### Step 2: Project Setup

1. **Create project directory:**
   ```bash
   mkdir eya_questionnaire
   cd eya_questionnaire
   ```

2. **Copy all project files** into this directory (from the provided structure)

3. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

### Step 3: Build and Start Docker Containers

```bash
# Build and start all services
docker-compose up --build

# Or run in detached mode (background)
docker-compose up -d --build
```

This will:
- Start PostgreSQL container
- Build Django app container
- Run migrations automatically
- Seed questionnaire data
- Start development server on http://localhost:8000

### Step 4: Access the Application

- **Main App:** http://localhost:8000
- **Admin Panel:** http://localhost:8000/admin/
  - Default credentials: Create a superuser (see Step 5)

### Step 5: Create Admin User

```bash
# In a new terminal, run:
docker-compose exec web python manage.py createsuperuser

# Follow prompts to create username, email, and password
```

### Step 6: Using the System

#### View Assessment Framework
1. Navigate to http://localhost:8000/assessment-table/
2. See all 10 categories with 94 criteria and their 0-5 level indicators

#### Create a Questionnaire
1. Click "New Questionnaire" or go to http://localhost:8000/questionnaires/create/
2. Fill in title, description, and organization name
3. Submit to create

#### Fill the Questionnaire
1. From the questionnaire list, click "Continue Assessment"
2. Navigate through categories using the sidebar
3. For each criterion, select a level (0-5) by clicking the card
4. Add optional notes/evidence
5. Click "Save & Continue" to move to next category
6. Repeat until all categories are complete

#### View Results
1. Go to questionnaire detail page
2. Click "View Results"
3. See category averages, weighted scores, and grand total

#### Admin Management
1. Go to http://localhost:8000/admin/
2. Log in with superuser credentials
3. Manage:
   - Assessment Categories
   - Criteria
   - Level Indicators
   - Questionnaires and Responses
   - Evidence Items

### Step 7: Database Operations

```bash
# Make migrations after model changes
docker-compose exec web python manage.py makemigrations

# Apply migrations
docker-compose exec web python manage.py migrate

# Reset and re-seed data
docker-compose exec web python manage.py flush
docker-compose exec web python manage.py seed_questionnaire

# Access PostgreSQL directly
docker-compose exec db psql -U postgres -d eya_questionnaire

# Backup database
docker-compose exec db pg_dump -U postgres eya_questionnaire > backup.sql

# Restore database
docker-compose exec -T db psql -U postgres eya_questionnaire < backup.sql
```

### Step 8: Development Commands

```bash
# Run tests
docker-compose exec web python manage.py test

# Django shell
docker-compose exec web python manage.py shell

# Check system
docker-compose exec web python manage.py check

# Collect static files (production)
docker-compose exec web python manage.py collectstatic --noinput
```

### Step 9: Stopping the Application

```bash
# Stop containers
docker-compose down

# Stop and remove volumes (WARNING: deletes database data)
docker-compose down -v
```

## Data Model

### AssessmentCategory
- name, weight (percentage), description, order, is_active

### Criterion
- category (FK), number, name, description, order, is_active

### LevelIndicator
- criterion (FK), level (0-5), indicator (description)

### EvidenceItem
- category (FK), name, description, is_required

### Questionnaire
- title, description, organization_name, assessment_date, is_completed
- Properties: total_score, completion_percentage

### Response
- questionnaire (FK), criterion (FK), score (0-5), notes

### EvidenceUpload
- response (FK), file, description

## Scoring System

Each criterion is scored 0-5:
- **0:** Not present / No evidence
- **1:** Minimal / Informal
- **2:** Basic / Limited
- **3:** Developing / Moderate
- **4:** Advanced / Strong
- **5:** Excellent / Leading practice

Weighted total calculation:
```
Category Score = Average of criteria scores × Category Weight%
Grand Total = Sum of all Category Scores
```

## API Endpoints (for future expansion)

| URL | Method | Description |
|-----|--------|-------------|
| `/` | GET | Home page |
| `/questionnaires/` | GET | List all questionnaires |
| `/questionnaires/create/` | POST | Create new questionnaire |
| `/questionnaires/<id>/` | GET | Questionnaire detail |
| `/questionnaires/<id>/fill/` | GET/POST | Fill questionnaire |
| `/questionnaires/<id>/results/` | GET | View results |
| `/assessment-table/` | GET | View all criteria in table |
| `/ajax/level-indicator/` | GET | Get level description (AJAX) |
| `/admin/` | GET | Django admin panel |

## Troubleshooting

### Port 5432 already in use
```bash
# Change port in docker-compose.yml:
ports:
  - "5433:5432"  # Use 5433 on host
```

### Database connection failed
```bash
# Check if PostgreSQL is healthy
docker-compose ps

# View logs
docker-compose logs db
```

### Static files not loading
```bash
# Collect static files
docker-compose exec web python manage.py collectstatic --noinput
```

### Permission denied on Linux
```bash
# Fix permissions
sudo chown -R $USER:$USER .
```

## Production Deployment Notes

1. Change `SECRET_KEY` in `.env` to a secure random string
2. Set `DEBUG=False` in `.env`
3. Update `ALLOWED_HOSTS` with your domain
4. Use a production WSGI server (Gunicorn included in requirements)
5. Set up a reverse proxy (Nginx)
6. Use SSL/TLS certificates
7. Configure proper logging
8. Set up database backups

## Technology Stack

- **Backend:** Django 5.x (Python 3.12)
- **Database:** PostgreSQL 16
- **Frontend:** Bootstrap 5, vanilla JavaScript
- **Forms:** Django Crispy Forms
- **Containerization:** Docker & Docker Compose
- **Static Files:** WhiteNoise

## License

This project is created for DSE assessment purposes.
