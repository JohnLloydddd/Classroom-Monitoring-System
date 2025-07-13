import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_migrate import Migrate
from sqlalchemy import create_engine, text

db = SQLAlchemy()
socketio = SocketIO()
migrate = Migrate()

def setup_database():
    db_path = os.path.abspath('instance/classrooms.db')
    engine = create_engine(f'sqlite:///{db_path}')
    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL;"))

def create_app():
    app = Flask(__name__)

    # App configuration
    app.config['SECRET_KEY'] = 'your_secret_key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///classrooms.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)

    setup_database()

    # Register Blueprints
    from app.routes import main, auth
    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')

    return app