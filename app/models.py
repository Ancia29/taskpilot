from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db, login

def now(): return datetime.utcnow()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(32), unique=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), unique=True, nullable=False, index=True)
    role = db.Column(db.String(16), default="employee")
    department = db.Column(db.String(80)); job_role = db.Column(db.String(80))
    pw_hash = db.Column(db.String(255))
    invite_hash = db.Column(db.String(64), index=True); invite_expires = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)
    def set_pw(self, p): self.pw_hash = generate_password_hash(p)
    def check_pw(self, p): return bool(self.pw_hash) and check_password_hash(self.pw_hash, p)

@login.user_loader
def _load(uid): return db.session.get(User, int(uid))

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(24), unique=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text); deliverables = db.Column(db.Text)
    criteria = db.Column(db.JSON, nullable=False)  # list of strings
    priority = db.Column(db.String(12), default="Medium")
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    deadline = db.Column(db.DateTime); review_at = db.Column(db.DateTime)
    max_attempts = db.Column(db.Integer, default=3)
    status = db.Column(db.String(32), default="Assigned", index=True)
    created_at = db.Column(db.DateTime, default=now)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), index=True, nullable=False)
    version = db.Column(db.Integer, nullable=False)
    stored_name = db.Column(db.String(80)); original_name = db.Column(db.String(255))
    text_len = db.Column(db.Integer); created_at = db.Column(db.DateTime, default=now)
    __table_args__ = (db.UniqueConstraint("task_id", "version"),)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), unique=True)
    score = db.Column(db.Integer); decision = db.Column(db.String(24))
    result = db.Column(db.JSON); created_at = db.Column(db.DateTime, default=now)

class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer); action = db.Column(db.String(60)); detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now)
