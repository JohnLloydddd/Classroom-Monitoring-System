import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_migrate import Migrate
from sqlalchemy import create_engine, text

# Initialize extensions
db = SQLAlchemy()
socketio = SocketIO()
migrate = Migrate()

# Create a function for setting up database engine and PRAGMA
def setup_database():
    db_path = os.path.abspath('instance/classrooms.db')
    engine = create_engine(f'sqlite:///{db_path}')
    with engine.connect() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL;"))

def create_app():
    # Create Flask app instance
    app = Flask(__name__)

    # App Configurations
    app.config['SECRET_KEY'] = 'your_secret_key'  # For security and sessions
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.abspath("instance/classrooms.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable warnings
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///classrooms.db'
    print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])  # Debugging statement

    # Initialize Flask extensions
    db.init_app(app)
    socketio.init_app(app)
    migrate.init_app(app, db)

    # Setup database
    setup_database()

    # Import and register Blueprints (moved inside the function to prevent circular imports)
    from app.routes import main, auth
    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')  # All auth routes are prefixed with /auth

    return app
