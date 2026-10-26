import click
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy(); login = LoginManager(); csrf = CSRFProtect()
limiter = Limiter(get_remote_address)

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    db.init_app(app); login.init_app(app); csrf.init_app(app); limiter.init_app(app)

    @login.unauthorized_handler
    def _unauth():
        return jsonify(error="login required"), 401

    from .routes import bp
    app.register_blueprint(bp)

    @app.cli.command("init-db")
    def init_db():
        db.create_all(); print("tables created")

    @app.cli.command("create-manager")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_manager(email, name, password):
        from .models import User
        if User.query.filter_by(email=email.lower()).first(): raise click.ClickException("that email already exists")
        u = User(email=email.lower(), name=name, role="manager"); u.set_pw(password)
        db.session.add(u); db.session.commit(); print("manager created")
    return app
