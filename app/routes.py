from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, session, make_response, current_app as app, Flask, Response, get_flashed_messages
from app import db, socketio
from app.models import Room, User, Amenity, Department, RoomOccupancy, room_amenities, Professor, RoomRFID, db
from sqlalchemy.exc import IntegrityError
from functools import wraps
from flask_wtf.csrf import generate_csrf
import pytz, sqlite3
from datetime import datetime, timezone
from sqlalchemy.sql import text
from sqlalchemy.orm import joinedload
from sqlalchemy import func, desc, extract

# Define Blueprints
main = Blueprint('main', __name__)
auth = Blueprint('auth', __name__)

utc = pytz.UTC

local_tz = pytz.timezone('Asia/Singapore')  # Replace with your local timezone
naive_datetime = datetime.now()
aware_datetime = local_tz.localize(naive_datetime)

def nocache(view):
    """Decorator to prevent caching of a view."""
    @wraps(view)
    def no_cache_response(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    return nocache_response

# Main Blueprint Routes
@main.route('/')
def home():
    rooms = Room.query.all()
    amenities = Amenity.query.all()
    departments = Department.query.all()

    for room in rooms:
        if room.status == 'Occupied':
            # Join room_occupancy and room_rfid to fetch the correct tag holder
            result = db.session.execute(text("""
                SELECT professor_name
                FROM room_occupancy
                WHERE room_id = :room_id
                ORDER BY start_time DESC
                LIMIT 1
            """), {'room_id': room.id}).fetchone()


            room.professor_name = result[0] if result else "Unknown"
        else:
            room.professor_name = "Unknown"

    return render_template('index.html', rooms=rooms, amenities=amenities, departments=departments)

# Custom login_required decorator using session
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("isLoggedIn"):
            flash("You need to log in first!", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

@main.route('/update_room/<int:room_id>', methods=['GET', 'POST'])
@login_required
def update_room(room_id):
    room = Room.query.get_or_404(room_id)

    if not room:
        flash('Room not found.', 'error')
        return redirect(url_for('main.dashboard'))

    amenities = Amenity.query.all()
    selected_amenities = [amenity.id for amenity in room.amenities]
    departments = Department.query.all()

    if request.method == 'POST':
        room_name = request.form.get('room_name', '').strip()
        department_id = request.form.get('department')
        selected_amenity_ids = request.form.getlist('amenities')
        room_capacity = request.form.get('room_capacity')

        # Validate and update room name
        if room_name:
            if Room.query.filter(Room.room_number == room_name, Room.id != room_id).first():
                flash('A room with this name already exists!', 'error')
                return redirect(url_for('main.update_room', room_id=room_id))
            room.room_number = room_name
        else:
            flash('Room name cannot be empty.', 'error')
            return redirect(url_for('main.update_room', room_id=room_id))

        # Validate and update room capacity
        if room_capacity and room_capacity.isnumeric():
            room.room_capacity = int(room_capacity)
        else:
            flash('Invalid room capacity. Please enter a valid number.', 'error')
            return redirect(url_for('main.update_room', room_id=room_id))

        # Update department if provided
        if department_id and department_id.isdigit():
            room.department_id = int(department_id)
        else:
            room.department_id = None

        # Update amenities
        db.session.execute(
            room_amenities.delete().where(room_amenities.c.room_id == room_id)
        )
        if selected_amenity_ids:
            for amenity_id in selected_amenity_ids:
                db.session.execute(
                    room_amenities.insert().values(room_id=room_id, amenity_id=amenity_id)
                )

        try:
            db.session.commit()
            flash('Room updated successfully!', 'success')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating room: {str(e)}', 'danger')

    return render_template(
        'update_room.html',
        room=room,
        amenities=amenities,
        selected_amenities=selected_amenities,
        departments=departments
    )

@main.route('/update_room_status', methods=['GET'])
def update_room_status():
    rfid_tag = request.args.get('rfid_tag')
    room_id_from_esp = request.args.get('room_id')

    print(f"\n[INFO] Request received at {datetime.now().isoformat()}")
    print(f"[INFO] Incoming RFID: {rfid_tag}, Room ID: {room_id_from_esp}")

    if not rfid_tag or not room_id_from_esp:
        return jsonify({'status': 'error', 'message': 'Missing RFID tag or Room ID.'}), 400

    try:
        room_id = int(room_id_from_esp)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid room ID format.'}), 400

    try:
        room = db.session.query(Room).with_for_update().get(room_id)
        if not room:
            return jsonify({'status': 'error', 'message': 'Room not found.'}), 404

        assigned_room = RoomRFID.query.filter_by(rfid_tag=rfid_tag, room_id=room_id).first()
        if not assigned_room:
            socketio.emit('unregistered_tag_scanned', {
                'rfid_tag': rfid_tag.lower(),
                'name': 'Unknown',
                'room_name': room.room_number,
                'message': 'This RFID tag is not registered for this room.'
            }, namespace="/")
            return jsonify({'status': 'error', 'message': 'Unauthorized tag for this room.'}), 403

        tag_holder_name = assigned_room.name if assigned_room.name else "Unknown"

        if room.status == 'Vacant':
            room.status = 'Occupied'
            room.occupied_since = datetime.utcnow()
            room.occupied_end_time = None

            # Create a temporary log of who tapped in
            temp_record = RoomOccupancy(
                room_id=room.id,
                start_time=datetime.utcnow(),
                professor_name=tag_holder_name
            )
            db.session.add(temp_record)
        elif room.status == 'Occupied':
            room.status = 'Vacant'
            occupied_start_time = room.occupied_since
            occupied_end_time = datetime.utcnow()

            # Update the last entry to set end_time
            last_record = RoomOccupancy.query.filter_by(room_id=room.id).order_by(desc(RoomOccupancy.id)).first()
            if last_record and last_record.end_time is None:
                last_record.end_time = occupied_end_time

            room.occupied_since = None
            room.occupied_end_time = occupied_end_time

        db.session.commit()

        socketio.emit('room_status_updated', {
            'room_id': room.id,
            'room_number': room.room_number,
            'status': room.status,
            'occupied_since': room.occupied_since.isoformat() if room.occupied_since else None,
            'professor_name': tag_holder_name,
            'rfid_tag': rfid_tag
        }, namespace="/")

        print(f"[SUCCESS] Room {room.room_number} status updated to {room.status} for RFID {rfid_tag}")

        return jsonify({
            'status': 'success',
            'message': f'Room {room.room_number} status updated to {room.status}.',
            'room_id': room.id
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"[ERROR] update_room_status failed: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Server error occurred.'}), 500

@main.route('/get_room_status', methods=['GET'])
def get_room_status():
    rooms = Room.query.all()
    room_data = []

    for room in rooms:
    # Get the current occupant (latest RoomOccupancy with no end_time)
        current_occupant = RoomOccupancy.query.filter_by(room_id=room.id, end_time=None).order_by(RoomOccupancy.start_time.desc()).first()
        professor_name = current_occupant.professor_name if current_occupant else "Unknown"

        room_data.append({
            'room_id': room.id,
            'room_number': room.room_number,
            'status': room.status,
            'occupied_since': room.occupied_since.isoformat() if room.occupied_since else None,
            'professor_name': professor_name
        })

    return jsonify(room_data)

@main.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    rooms = Room.query.all()
    departments = Department.query.all()
    amenities = Amenity.query.all()

    response = Response(render_template(
        "dashboard.html",
        rooms=rooms,
        departments=departments,
        amenities=amenities,
        selected_departments=[],
        selected_amenities=[],
        messages=get_flashed_messages(with_categories=True)  # ? Pass flashed messages
    ))

    # Prevent browser caching
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['isLoggedIn'] = True  # ? Store login status
            flash('Login successful!', 'success')
            return redirect(url_for('main.dashboard'))
        flash('Invalid username or password.', 'error')

    response = Response(render_template('login.html'))
    
    # Prevent browser caching
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

@auth.route('/logout', methods=['GET'])
def logout():
    if 'user_id' in session:
        session.pop('user_id', None)
    session.pop('isLoggedIn', None)  # ? Remove login status
    session.clear()  # ? Clears the entire session
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/check_login_status', methods=['GET'])
def check_login_status():
    is_logged_in = session.get('isLoggedIn', False)
    return jsonify({'isLoggedIn': is_logged_in})

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Both username and password are required.', 'error')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('auth.register'))

        new_user = User(username=username)
        new_user.set_password(password)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            db.session.rollback()
            flash('Error during registration.', 'error')

    return render_template('register.html')

@main.route('/add_amenity', methods=['POST'])
def add_amenity():
    data = request.get_json()
    amenity_name = data.get('name', '').strip()

    if not amenity_name:
        return jsonify(success=False, message="Amenity name cannot be empty.")

    existing_amenity = Amenity.query.filter_by(name=amenity_name).first()
    if existing_amenity:
        return jsonify(success=False, message="Amenity already exists.")

    new_amenity = Amenity(name=amenity_name)
    try:
        db.session.add(new_amenity)
        db.session.commit()
        print("Amenity added:", new_amenity)  # Debugging statement
        return jsonify(success=True, message="Amenity added successfully.")
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=False, message="Database error.")
    socketio.emit('amenity_udpated')


from flask import jsonify, current_app as app

@main.route('/get_amenities', methods=['GET'])
def get_amenities():
    try:
        # Fetch all amenities from the database
        amenities = Amenity.query.all()
        
        # Debugging log for raw query results
        app.logger.debug("Raw amenities query: %s", amenities)
        
        # Process amenities into a list of dictionaries
        amenities_list = [
            {"id": amenity.id, "name": amenity.name} 
            for amenity in amenities if amenity and amenity.id is not None
        ]
        
        # Debugging log for processed results
        app.logger.debug("Processed amenities list: %s", amenities_list)
        
        # Return the JSON response
        return jsonify(amenities_list), 200
    except Exception as e:
        # Log the exception for debugging
        app.logger.error("Error fetching amenities: %s", str(e))
        
        # Return an error response
        return jsonify({"error": "An error occurred while fetching amenities."}), 500



@main.route('/delete_amenity', methods=['POST'])
def delete_amenity():
    data = request.get_json()
    amenity_name = data.get('name', '').strip()

    if not amenity_name:
        return jsonify(success=False, message="Amenity name cannot be empty.")

    amenity = Amenity.query.filter_by(name=amenity_name).first()
    if not amenity:
        return jsonify(success=False, message="Amenity not found.")

    try:
        db.session.delete(amenity)
        db.session.commit()
        return jsonify(success=True, message="Amenity deleted successfully.")
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=False, message="Database error.")

@main.route('/add_department', methods=['POST'])
def add_department():
    data = request.get_json()
    department_name = data.get('name')
    
    if department_name:
        
        existing_department = Department.query.filter_by(name=department_name).first()
        if existing_department:
            return jsonify(success=False, message="Department already exists.")
        
        new_department = Department(name=department_name)
        db.session.add(new_department)
        db.session.commit()
        return jsonify(success=True, message="Department added successfully.")
    return jsonify(success=False, message="Invalid data.")

@main.route('/get_departments', methods=['GET'])
def get_departments():
    departments = Department.query.all()
    department_list = [{'id': department.id, 'name': department.name} for department in departments]
    return jsonify(department_list)

@main.route('/delete_department', methods=['POST'])
def delete_department():
    data = request.get_json()
    department_name = data.get('name', '').strip()

    if not department_name:
        return jsonify(success=False, message="Department name cannot be empty.")

    department = Department.query.filter_by(name=department_name).first()
    if not department:
        return jsonify(success=False, message="Department not found.")

    try:
        db.session.delete(department)
        db.session.commit()
        return jsonify(success=True, message="Department deleted successfully.")
    except IntegrityError:
        db.session.rollback()
        return jsonify(success=False, message="Database error.")
    
@main.route('/generate_report/<int:room_id>', methods=['GET'])
@login_required
def generate_report(room_id):
    room = Room.query.get(room_id)
    if not room:
        return jsonify({'status': 'error', 'message': 'Room not found.'}), 404
    
    # Read month/year query params (optional)
    selected_month = request.args.get('month')  # e.g., "5"
    selected_year = request.args.get('year')    # e.g., "2025"

    # Fetch all occupancy records for the room
    sql_query = text("SELECT start_time, end_time FROM room_occupancy WHERE room_id = :room_id")
    params = {"room_id": room_id}
    
     # Add month/year filters to SQL query
    if selected_month and selected_year and selected_month != "all" and selected_year != "all":
        sql_query = text("""
            SELECT start_time, end_time FROM room_occupancy
            WHERE room_id = :room_id
            AND strftime('%m', start_time) = :month
            AND strftime('%Y', start_time) = :year
        """)
        params.update({
            "month": f"{int(selected_month):02d}",  # pad to 2 digits
            "year": selected_year
        })  
    
    occupancy_records = db.session.execute(sql_query, {"room_id": room_id}).fetchall()

    # Total seconds calculation
    total_seconds = 0
    detailed_usage = []

    for record in occupancy_records:
        start_time, end_time = record
        if start_time and end_time:
            # Parse timestamps into datetime objects
            start_time_dt = datetime.fromisoformat(start_time)
            end_time_dt = datetime.fromisoformat(end_time)

            # Calculate duration in seconds
            duration = (end_time_dt - start_time_dt).total_seconds()
            total_seconds += duration

            # Add record to detailed usage
            detailed_usage.append({
                'start_time': start_time,  # Use raw UTC format for JavaScript processing
                'end_time': end_time,
                'duration': f"{int(duration // 3600)} hour(s), {int((duration % 3600) // 60)} minute(s)"
            })

    # Helper functions
    def format_days(seconds):
        return seconds // 86400  # 1 day = 86400 seconds

    def format_weeks(seconds):
        return seconds // (7 * 86400)  # 1 week = 7 days

    def format_months(seconds):
        return seconds // (30 * 86400)  # Approximation for months

    def format_years(seconds):
        return seconds // (365 * 86400)  # Approximation for years

    # Calculate usage summary
    total_days = int(format_days(total_seconds))
    total_weeks = int(format_weeks(total_seconds))
    total_months = int(format_months(total_seconds))
    total_years = int(format_years(total_seconds))
    hours_minutes_format = f"{int(total_seconds // 3600)} hour(s) and {int((total_seconds % 3600) // 60)} minute(s)"

    return render_template(
        'report.html',
        room=room,  # ? Add this line
        room_id=room.room_number,
        total_days=total_days,
        total_weeks=total_weeks,
        total_months=total_months,
        total_years=total_years,
        hours_minutes_format=hours_minutes_format,
        detailed_usage=detailed_usage
    )

@main.route('/reset_report/<int:room_id>', methods=['POST'])
def reset_report(room_id):
    try:
        data = request.get_json()
        selected_month = data.get('month')  # string, e.g., '5' for May
        selected_year = data.get('year')    # string, e.g., '2025'

        if selected_month == "all" or selected_year == "all":
            # Reset all records for the room
            deleted_rows = RoomOccupancy.query.filter_by(room_id=room_id).delete()
        else:
            # Reset records for the specific month and year
            deleted_rows = RoomOccupancy.query.filter(
                RoomOccupancy.room_id == room_id,
                extract('month', RoomOccupancy.start_time) == int(selected_month),
                extract('year', RoomOccupancy.start_time) == int(selected_year)
            ).delete()

        db.session.commit()
        return jsonify({"message": f"Success: {deleted_rows} record(s) successfully deleted."}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Error: {str(e)}"}), 500

@main.route('/filter_rooms', methods=['GET'])
def filter_rooms():
    selected_amenities = request.args.getlist('amenities', type=int)
    selected_departments = [int(d) for d in request.args.getlist('department') if d.isdigit()]
    
    query = Room.query

    if selected_amenities:
        query = query.join(Room.amenities).filter(Amenity.id.in_(selected_amenities)) \
            .group_by(Room.id).having(db.func.count(Amenity.id) == len(selected_amenities))

    if selected_departments:
        query = query.filter(Room.department_id.in_(selected_departments))

    rooms = query.all()
    departments = Department.query.all()
    amenities = Amenity.query.all()

    # Check which page the request came from
    page = request.args.get("page", "index")  # Default to index.html
    template = "dashboard.html" if page == "dashboard" else "index.html"

    return render_template(
        template,
        rooms=rooms,
        departments=departments,
        amenities=amenities,
        selected_amenities=selected_amenities,
        selected_departments=selected_departments
    )

@main.route('/add_room', methods=['GET', 'POST'])
def add_room():
    if request.method == 'POST':
        room_name = request.form.get('room_name', '').strip()
        department_id = request.form.get('department')
        selected_amenity_ids = request.form.getlist('amenities')

        if not room_name:
            return jsonify({"error": "Room name cannot be empty."}), 400

        # Debugging: Print existing rooms
        existing_rooms = db.session.query(Room.room_number).all()
        print("Existing rooms:", [r[0] for r in existing_rooms])

        # Proper case-insensitive duplicate check
        existing_room = db.session.query(Room).filter(
            func.lower(Room.room_number) == func.lower(room_name)
        ).first()

        if existing_room:
            return jsonify({"error": "A room with this name already exists!"}), 400

        # Create and add new room
        new_room = Room(
            room_number=room_name,
            department_id=int(department_id) if department_id else None,  # Convert department_id if provided
            status="Vacant"
        )
        db.session.add(new_room)

        try:
            db.session.commit()
            print("Room successfully added:", new_room.room_number)  # Debugging
        except IntegrityError:
            db.session.rollback()
            print("Integrity error: Room with this name already exists.")  # Debugging
            return jsonify({"error": "A room with this name already exists!"}), 400

        # Assign selected amenities (if any)
        if selected_amenity_ids:
            try:
                for amenity_id in selected_amenity_ids:
                    db.session.execute(
                        room_amenities.insert().values(room_id=new_room.id, amenity_id=int(amenity_id))
                    )
                db.session.commit()
                print(f"Amenities assigned to room {new_room.room_number}: {selected_amenity_ids}")  # Debugging
            except Exception as e:
                db.session.rollback()
                print(f"Error assigning amenities: {str(e)}")
                return jsonify({"error": "Error assigning amenities."}), 500

        return jsonify({
            "message": "Successfully added a room",
            "room": {"id": new_room.id, "room_number": new_room.room_number}
        }), 200

    # Handle GET request
    amenities = Amenity.query.all()
    departments = Department.query.all()
    return render_template('add_room.html', amenities=amenities, departments=departments)

@main.route('/delete_room', methods=['GET', 'POST'])
def delete_room():
    if request.method == 'POST':
        data = request.get_json()
        room_ids = data.get("room_ids", [])

        if not room_ids:
            return jsonify({"error": "No rooms selected"}), 400

        try:
            # Convert room IDs to integers
            room_ids = [int(rid) for rid in room_ids]

            # Fetch the rooms to ensure they exist before deleting
            rooms_to_delete = Room.query.filter(Room.id.in_(room_ids)).all()

            if not rooms_to_delete:
                return jsonify({"error": "No valid rooms found"}), 404

            # Delete rooms (cascade will handle associated RFID tags)
            for room in rooms_to_delete:
                db.session.delete(room)

            db.session.commit()

            return jsonify({"message": "Rooms and associated RFID tags deleted successfully"}), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    # If it's a GET request, fetch all rooms and render the page
    rooms = Room.query.all()
    return render_template('delete_room.html', rooms=rooms)

@main.route('/add_tag', methods=['GET', 'POST'])
@login_required
def add_tag():
    if request.method == 'POST':
        rfid_tag = request.form['rfid_tag']
        name = request.form['name']
        room_number = request.form.get('assign_room')  # Get room number as a string

        room = None  # Default to None in case no room is assigned
        if room_number:
            room = Room.query.filter_by(room_number=room_number).first()  # Query using room_number
            if not room:
                flash("Error: Room does not exist!", "error")
                return redirect(url_for('main.add_tag'))

        # Check if the RFID tag already exists in RoomRFID
        existing_tag = RoomRFID.query.filter_by(rfid_tag=rfid_tag).first()
        if existing_tag:
            # If the RFID tag exists, ensure the name matches
            if existing_tag.name != name:
                flash(f"Error: The tag ID '{rfid_tag}' is already registered with the name '{existing_tag.name}'. Please use the same name.", "error")
                return redirect(url_for('main.add_tag'))

        # Check if the name is already assigned to another RFID tag
        name_in_other_rfid = RoomRFID.query.filter_by(name=name).filter(RoomRFID.rfid_tag != rfid_tag).first()
        if name_in_other_rfid:
            flash("This name is already assigned to another RFID tag!", "error")
            return redirect(url_for('main.add_tag'))

        # Add the RFID tag to the new room without removing existing registrations
        new_tag = RoomRFID(rfid_tag=rfid_tag, room_id=room.id if room else None, name=name)
        db.session.add(new_tag)

        try:
            db.session.commit()
            flash("Successfully added the RFID tag to the room!", "success")
        except IntegrityError as e:
            db.session.rollback()
            if "UNIQUE constraint failed" in str(e):
                flash("There is an existing tag in this room", "error")
            else:
                flash(f"Error adding RFID tag: {str(e)}", "error")

        return redirect(url_for('main.add_tag'))

    rooms = Room.query.all()
    return render_template('add_tag.html', rooms=rooms)

@main.route("/delete_tag", methods=["GET", "POST"])
@login_required
def delete_tag():
    if request.method == "POST":
        try:
            data = request.get_json()
            tag_rooms = data.get("tag_ids", [])  # Contains {"tag_id": x, "room_id": y} pairs

            if not tag_rooms:
                return jsonify({"error": "No tags selected."}), 400

            deleted_tags = []

            for tag_room in tag_rooms:
                tag_id = tag_room.get("tag_id")
                room_id = tag_room.get("room_id")

                if not tag_id or room_id is None:
                    continue

                # Delete only the specific tag-room association
                tag_entry = RoomRFID.query.filter_by(rfid_tag=tag_id, room_id=room_id).first()
                if tag_entry:
                    db.session.delete(tag_entry)
                    db.session.commit()

                # Check if the tag is still associated with any other room
                remaining_room_count = RoomRFID.query.filter_by(rfid_tag=tag_id).count()
                if remaining_room_count == 0:
                    # If no other room is associated, delete the professor entry
                    professor_entry = Professor.query.filter_by(rfid_tag=tag_id).first()
                    if professor_entry:
                        db.session.delete(professor_entry)
                        db.session.commit()
                        deleted_tags.append(tag_id)

            return jsonify({"message": "Tags deleted successfully.", "deleted_tag_ids": deleted_tags}), 200

        except Exception as e:
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

    # Fetch all RFID tags from RoomRFID including room name
    room_tags = (
        db.session.query(RoomRFID.rfid_tag, RoomRFID.name, Room.room_number, RoomRFID.room_id)
        .join(Room, RoomRFID.room_id == Room.id)
        .all()
    )

    # Fetch RFID tags from the professor table (if applicable)
    professor_tags = (
        db.session.query(Professor.rfid_tag, Professor.name, Room.room_number, Professor.room_id)
        .join(Room, Professor.room_id == Room.id)
        .all()
    )

    # Combine both sources of tags
    formatted_tags = [
        {
            "rfid_tag": tag.rfid_tag,
            "name": tag.name,
            "room_name": tag.room_number,
            "room_id": tag.room_id,
        }
        for tag in room_tags + professor_tags  # Merging both queries
    ]

    return render_template("delete_tag.html", tags=formatted_tags)