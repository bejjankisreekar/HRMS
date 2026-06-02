# HRMS (Multi-tenant SaaS) — Phase 1

Backend: Django + DRF  
Frontend: Django templates + Tailwind (CDN) + Vanilla JS  
DB: PostgreSQL  
Auth: Session + JWT (SimpleJWT)

## Project structure

```text
HRMS/
  hrms/
    apps/
      accounts/
      organizations/
      dashboard/
    config/
    templates/
    static/
    media/
    manage.py
  venv/
```

## Setup (Windows)

```powershell
cd d:\HRMS
python -m venv venv
.\venv\Scripts\Activate
pip install -r .\hrms\requirements.txt
copy .\hrms\.env.example .\hrms\.env
```

## PostgreSQL setup

1. Create a database (example: `hrms`)
2. Update `.env`:

```env
DB_NAME=hrms
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432
```

## Migrations + run server

```powershell
cd d:\HRMS\hrms
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

## Default Super Admin (auto-created)

On first migrate, the system creates a default Super Admin using `.env`:

- `SUPERADMIN_EMAIL` (default `superadmin@hrms.com`)
- `SUPERADMIN_PASSWORD` (default `Admin@123`)

Login at:

- Landing: `http://127.0.0.1:8000/`
- Login: `http://127.0.0.1:8000/accounts/login/`

## Phase 1 pages

- Landing: `/`
- Login: `/accounts/login/`
- Organization registration: `/accounts/register/`
- Dashboard (role redirect): `/dashboard/`

## Notes

- Tailwind is loaded via CDN for phase-1 to keep setup simple. We can switch to a compiled Tailwind pipeline (Node/PostCSS) later.
- Multi-tenancy in phase-1 is modeled via `User.organization` and `Organization` records. Data isolation enforcement will be expanded as we add real modules.

