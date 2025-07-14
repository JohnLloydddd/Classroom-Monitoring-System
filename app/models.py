from app import db
from werkzeug.security import generate_password_hash, check_password_hash  # For password hashing
from datetime import datetime, timedelta
import pytz
from sqlalchemy.orm import relationship

#password hashing and checking functions
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Room(db.Model):   
    __tablename__ = 'room'
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Vacant')
    occupied_since = db.Column(db.DateTime)
    room_capacity = db.Column(db.Integer, nullable=False, default=30)  

    professors = db.relationship('Professor', back_populates='room')
    amenities = db.relationship(
        'Amenity',
        secondary='room_amenities',
        back_populates='rooms'
    )
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', back_populates='rooms')
    occupied_start_time = db.Column(db.DateTime, nullable=True)
    occupied_end_time = db.Column(db.DateTime, nullable=True)
    occupancy_history = db.relationship('RoomOccupancy', back_populates='room', cascade='all, delete-orphan')
    rfids = db.relationship('RoomRFID', back_populates='room', cascade='all, delete-orphan', passive_deletes=True)
    
class RoomOccupancy(db.Model):
    __tablename__ = 'room_occupancy'
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    room = db.relationship('Room', back_populates='occupancy_history')
    professor_name = db.Column(db.String(100)) 

class Professor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    rfid_tag = db.Column(db.String(100), db.ForeignKey('room_rfid.rfid_tag', ondelete='CASCADE'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    room = db.relationship('Room', back_populates='professors')
    room_rfid = db.relationship('RoomRFID', back_populates='assigned_professors')

class RFIDLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    professor_id = db.Column(db.Integer, db.ForeignKey('professor.id'))
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    timestamp = db.Column(db.DateTime, nullable=False, default=db.func.now())
    
class RoomRFID(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', ondelete='CASCADE'), nullable=False)
    rfid_tag = db.Column(db.String(100), nullable=False, unique=True)
    name = db.Column(db.String(100))
    room = db.relationship('Room', back_populates='rfids')
    assigned_professors = db.relationship('Professor', back_populates='room_rfid', cascade="all, delete")

class Amenity(db.Model):
    __tablename__ = 'amenities'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    rooms = db.relationship(
        'Room',
        secondary='room_amenities',
        back_populates='amenities'
    )

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    rooms = db.relationship('Room', back_populates='department')


room_amenities = db.Table(
    'room_amenities',
    db.Column('room_id', db.Integer, db.ForeignKey('room.id'), primary_key=True),
    db.Column('amenity_id', db.Integer, db.ForeignKey('amenities.id'), primary_key=True)
)
