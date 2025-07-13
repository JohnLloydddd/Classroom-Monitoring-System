from datetime import datetime, timezone
import pytz
import sqlite3


original_timezone = pytz.timezone('Asia/Shanghai')


conn = sqlite3.connect('instance/classrooms.db')
cursor = conn.cursor()


cursor.execute('SELECT id, occupied_start_time, occupied_end_time FROM room')
rows = cursor.fetchall()


for row in rows:
    record_id, start_time, end_time = row
    
    try:
        
        naive_start = datetime.fromisoformat(start_time) if start_time else None
        naive_end = datetime.fromisoformat(end_time) if end_time else None

       
        utc_start = original_timezone.localize(naive_start).astimezone(timezone.utc).isoformat() if naive_start else None
        utc_end = original_timezone.localize(naive_end).astimezone(timezone.utc).isoformat() if naive_end else None

       
        cursor.execute('''
            UPDATE room 
            SET occupied_start_time = ?, occupied_end_time = ? 
            WHERE id = ?
        ''', (utc_start, utc_end, record_id))

    except Exception as e:
        print(f"Error processing record ID {record_id}: {e}")


conn.commit()
conn.close()

print("Timestamps updated to UTC successfully.")
