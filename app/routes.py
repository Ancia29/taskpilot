import os, uuid, hashlib, io
from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, send_file, current_app, abort, render_template
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import generate_csrf
import pandas as pd
from . import db, limiter
from .models import User, Task, Submission, Review, Audit, now
from . import services as S

bp = Blueprint("main", __name__)

def manager_only(f):
    @wraps(f)
    @login_required
    def w(*a, **k):
        if current_user.role != "manager": abort(403)
        return f(*a, **k)
    return w

def own_task(tid):
    t = db.get_or_404(Task, tid)
    if current_user.role != "manager" and t.assignee_id != current_user.id: abort(404)
    return t

def tj(t): return dict(id=t.id, code=t.code, title=t.title, description=t.description, criteria=t.criteria, priority=t.priority,
    status=t.status, deadline=t.deadline and t.deadline.isoformat(), review_at=t.review_at and t.review_at.isoformat(), max_attempts=t.max_attempts)

@bp.get("/auth/csrf")
def csrf_token(): return jsonify(token=generate_csrf())

@bp.post("/auth/login")
@limiter.limit("10/minute")
def login():
    d = request.get_json(force=True)
    u = User.query.filter_by(email=str(d.get("email", "")).lower(), active=True).first()
    if not u or not u.check_pw(d.get("password", "")): return jsonify(error="invalid credentials"), 401
    login_user(u); return jsonify(role=u.role, name=u.name)

@bp.post("/auth/logout")
@login_required
def logout(): logout_user(); return jsonify(ok=True)

ACT_HTML = '''<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>Activate account</title>
<body style="font-family:system-ui;max-width:380px;margin:12vh auto;color:#0b1b3a"><h2>Set your password</h2>
<input id=p type=password placeholder="At least 10 characters" style="width:100%;padding:10px;box-sizing:border-box">
<button id=b style="margin-top:12px;padding:10px 16px;background:#1f4fd8;color:#fff;border:0;border-radius:6px">Activate account</button><p id=m></p>
<script>b.onclick=async()=>{const t=(await(await fetch('/auth/csrf')).json()).token;const r=await fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':t},body:JSON.stringify({password:p.value})});const j=await r.json();m.textContent=r.ok?'Account activated. You can sign in now.':(j.error||'Failed')}</script>'''

@bp.get("/activate/<token>")
def activate_page(token):
    u = User.query.filter_by(invite_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    if not u or not u.invite_expires or u.invite_expires < now(): return "Invalid or expired link", 400
    return ACT_HTML

@bp.post("/activate/<token>")
@limiter.limit("10/minute")
def activate(token):
    u = User.query.filter_by(invite_hash=hashlib.sha256(token.encode()).hexdigest()).first()
    pw = (request.get_json(force=True).get("password") or "")
    if not u or not u.invite_expires or u.invite_expires < now(): return jsonify(error="invalid or expired link"), 400
    if len(pw) < 10: return jsonify(error="password must be at least 10 characters"), 400
    u.set_pw(pw); u.invite_hash = None; u.invite_expires = None; db.session.commit()
    return jsonify(ok=True)

@bp.get("/api/template")
@manager_only
def template():
    p = os.path.join(current_app.instance_path, "employee_task_management.xlsx"); os.makedirs(current_app.instance_path, exist_ok=True)
    S.template_xlsx(p); return send_file(p, as_attachment=True)

@bp.post("/api/employees/import")
@manager_only
def import_emp():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".xlsx"): return jsonify(error="upload an .xlsx file"), 400
    try: return jsonify(S.import_employees(f, current_user.id))
    except ValueError as e: return jsonify(error=str(e)), 400

@bp.get("/api/employees")
@manager_only
def employees():
    q = User.query.filter_by(role="employee")
    if request.args.get("q"): q = q.filter(User.name.ilike(f"%{request.args['q']}%"))
    p = q.order_by(User.name).paginate(page=request.args.get("page", 1, type=int), per_page=25)
    return jsonify(total=p.total, items=[dict(id=u.id, employee_id=u.employee_id, name=u.name, email=u.email, department=u.department, job_role=u.job_role, activated=bool(u.pw_hash)) for u in p.items])

@bp.get("/api/export")
@manager_only
def export():
    rows = [dict(Task=t.code, Title=t.title, Employee=db.session.get(User, t.assignee_id).name, Status=t.status, Deadline=t.deadline) for t in Task.query.all()]
    b = io.BytesIO(); pd.DataFrame(rows).to_excel(b, index=False); b.seek(0)
    return send_file(b, as_attachment=True, download_name="task_report.xlsx")

@bp.post("/api/tasks")
@manager_only
def create_tasks():
    d = request.get_json(silent=True) or {}; errs = {}
    crit = d.get("criteria")
    crit = [c.strip() for c in crit if isinstance(c, str) and c.strip()] if isinstance(crit, list) else []
    if not crit: errs["criteria"] = "non-empty list of strings required"
    if not str(d.get("title", "")).strip(): errs["title"] = "required"
    ids = d.get("employee_ids")
    if not isinstance(ids, list) or not ids: errs["employee_ids"] = "non-empty list required"; ids = []
    def pdt(k):
        v = d.get(k)
        if not v: return None
        try: return datetime.fromisoformat(v)
        except (TypeError, ValueError): errs[k] = "use ISO format, e.g. 2026-11-05T17:00:00"
    deadline, review_at = pdt("deadline"), pdt("review_at")
    try:
        ma = int(d.get("max_attempts", 3))
        if not 1 <= ma <= 10: raise ValueError
    except (TypeError, ValueError): errs["max_attempts"] = "integer 1-10"; ma = 3
    users = [db.session.get(User, i) if isinstance(i, int) else None for i in ids]
    bad = [i for i, u in zip(ids, users) if not u or u.role != "employee"]
    if bad: errs["employee_ids"] = f"unknown or non-employee ids: {bad}"
    if errs: return jsonify(errors=errs), 400
    made = []
    for u in users:
        t = Task(code="T-" + uuid.uuid4().hex[:8].upper(), title=d["title"].strip(), description=str(d.get("description", "")), deliverables=str(d.get("deliverables", "")),
                 criteria=crit, priority=str(d.get("priority", "Medium")), assignee_id=u.id, deadline=deadline, review_at=review_at, max_attempts=ma)
        db.session.add(t); db.session.flush(); S.audit(current_user.id, "task_created", t.code); made.append((t, u))
    db.session.commit()
    mail_failed = 0
    for t, u in made:
        ok, _ = S.send_mail(u.email, f"New task {t.code}: {t.title}", f"Hello {u.name},\nTask {t.code} is assigned. Deadline: {t.deadline}.\n{t.description}")
        mail_failed += (not ok)
    return jsonify(created=[tj(t) for t, _ in made], mail_failures=mail_failed), 201

@bp.get("/api/tasks")
@login_required
def tasks():
    q = Task.query if current_user.role == "manager" else Task.query.filter_by(assignee_id=current_user.id)
    if request.args.get("status"): q = q.filter_by(status=request.args["status"])
    return jsonify([tj(t) for t in q.order_by(Task.deadline).all()])

@bp.get("/api/tasks/<int:tid>/reviews")
@login_required
def reviews(tid):
    t = own_task(tid)
    rows = db.session.query(Submission, Review).outerjoin(Review, Review.submission_id == Submission.id).filter(Submission.task_id == t.id).order_by(Submission.version).all()
    return jsonify([dict(version=s.version, file=s.original_name, score=r and r.score, decision=r and r.decision, result=r and r.result) for s, r in rows])

@bp.post("/api/tasks/<int:tid>/submit")
@login_required
@limiter.limit("10/hour")
def submit(tid):
    t = own_task(tid)
    if current_user.role != "employee": abort(403)
    if t.status not in ("Assigned", "In Progress", "Revision Required"): return jsonify(error=f"cannot submit while status is {t.status}"), 409
    f = request.files.get("file")
    ext = f.filename.rsplit(".", 1)[-1].lower() if f and "." in f.filename else ""
    if ext not in current_app.config["ALLOWED_EXT"]: return jsonify(error="unsupported file type"), 400
    ver = Submission.query.filter_by(task_id=t.id).count() + 1
    name = uuid.uuid4().hex + "." + ext; path = os.path.join(current_app.config["UPLOAD_DIR"], name)
    os.makedirs(current_app.config["UPLOAD_DIR"], exist_ok=True); f.save(path)
    if not S.sniff_ok(path, ext): os.remove(path); return jsonify(error="file content does not match its type"), 400
    try: text = S.extract_text(path, ext)
    except Exception as e: os.remove(path); return jsonify(error="could not read this file"), 422
    if len(text.strip()) < 20: os.remove(path); return jsonify(error="no readable text found (scanned PDF? OCR not enabled)"), 422
    sub = Submission(task_id=t.id, version=ver, stored_name=name, original_name=os.path.basename(f.filename)[:255], text_len=len(text))
    db.session.add(sub); t.status = "Under Review"; db.session.commit()
    try: out = S.llm_review(t, text)
    except Exception as e:
        t.status = "Awaiting Manager Review"; current_app.logger.exception('review failed'); S.audit(current_user.id, 'review_failed', type(e).__name__); db.session.commit()
        return jsonify(error="AI review failed; sent to manager for review"), 502
    t.status, why = S.decide(out, ver, t.max_attempts, len(t.criteria))
    db.session.add(Review(submission_id=sub.id, score=out["score"], decision=t.status, result=out))
    S.audit(current_user.id, "review_done", f"{t.code} v{ver} -> {t.status} ({why})"); db.session.commit()
    ok, err = S.send_mail(current_user.email, f"Review for {t.code}: {t.status}", out["summary"])
    return jsonify(status=t.status, review=out, email_sent=ok)

@bp.post("/api/tasks/<int:tid>/override")
@manager_only
def override(tid):
    t = db.get_or_404(Task, tid); d = request.get_json(force=True)
    if d.get("status") not in ("Completed", "Revision Required", "Assigned", "Cancelled") or not d.get("reason"):
        return jsonify(error="valid status and reason required"), 400
    S.audit(current_user.id, "override", f"{t.code}: {t.status} -> {d['status']} | {d['reason']}"); t.status = d["status"]; db.session.commit()
    return jsonify(tj(t))
@bp.get("/")
def home():
    return render_template("index.html")


@bp.get("/dashboard")
@manager_only
def dashboard():
    return """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>TaskPilot AI Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f3f5fa; color: #17233c; }
            main { max-width: 900px; margin: auto; }
            section { background: white; padding: 24px; border-radius: 12px; margin-top: 20px; }
            button { padding: 10px 16px; background: #315bea; color: white; border: 0; border-radius: 7px; cursor: pointer; }
            pre { white-space: pre-wrap; overflow-wrap: anywhere; }
        </style>
    </head>
    <body>
        <main>
            <h1>TaskPilot AI</h1>
            <p>Manager workspace</p>
            <section>
                <h2>Employees</h2>
                <button onclick="loadData('/api/employees', 'employees')">Load employees</button>
                <pre id="employees">Click to load employee data.</pre>
            </section>
            <section>
                <h2>Tasks</h2>
                <button onclick="loadData('/api/tasks', 'tasks')">Load tasks</button>
                <pre id="tasks">Click to load task data.</pre>
            </section>
            <button onclick="logout()">Sign out</button>
        </main>
        <script>
            async function loadData(url, id) {
                const box = document.getElementById(id);
                try {
                    const response = await fetch(url);
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.error || 'Request failed');
                    box.textContent = JSON.stringify(data, null, 2);
                } catch (error) {
                    box.textContent = error.message;
                }
            }

            async function logout() {
                const csrf = await (await fetch('/auth/csrf')).json();
                await fetch('/auth/logout', {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrf.token }
                });
                window.location.href = '/';
            }
        </script>
    </body>
    </html>
    """