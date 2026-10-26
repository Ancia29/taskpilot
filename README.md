# TaskPilot AI (core backend)
Use Python 3.11 or 3.12 (3.13 may need newer pinned packages). Windows PowerShell:
```
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # fill SECRET_KEY, DATABASE_URL (MySQL or leave for SQLite), OPENAI_API_KEY, SMTP_*
$env:FLASK_APP="run.py"
flask init-db
flask create-manager
flask run
```
API: all POSTs need header `X-CSRFToken` from `GET /auth/csrf` (after cookies are set). See app/routes.py.
Manager: /api/template, /api/employees/import, /api/employees, /api/tasks (POST bulk), /api/export, /api/tasks/<id>/override.
Employee: /api/tasks, /api/tasks/<id>/submit, /api/tasks/<id>/reviews. Activation: POST /activate/<token>.
Failures (SMTP, LLM) are reported in responses, never faked.
