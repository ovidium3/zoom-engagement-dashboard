import sqlite3
import json
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_PATH = 'zoom_engagement.db'

def init_db():
    """Initialize the database with required tables"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create transcriptions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            participant_name TEXT NOT NULL,
            transcript TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            sentiment_score INTEGER DEFAULT 0,
            browser_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create engagement data table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS engagement_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            participant_name TEXT NOT NULL,
            join_time TEXT,
            leave_time TEXT,
            duration INTEGER DEFAULT 0,
            talk_time INTEGER DEFAULT 0,
            browser_id TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute('''
            ALTER TABLE transcriptions ADD COLUMN browser_id TEXT;
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
    finally:
        conn.close()

def get_meeting_info_db(meeting_id):
    """
    Retrieve meeting details from the database
    
    Args:
        meeting_id (str): The ID of the meeting to retrieve
        
    Returns:
        dict: Meeting details or None if not found
    """
    try:
        # Connect to database
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Since we don't have a meetings table, we'll get meeting info from engagement data
        cursor.execute(
            "SELECT meeting_id, MIN(join_time) as start_time FROM engagement_data WHERE meeting_id = ? GROUP BY meeting_id",
            (meeting_id,)
        )
        meeting_data = cursor.fetchone()
        
        # Query for participant count
        cursor.execute(
            "SELECT COUNT(DISTINCT participant_id) FROM engagement_data WHERE meeting_id = ?",
            (meeting_id,)
        )
        participant_count_row = cursor.fetchone()
        participant_count = participant_count_row[0] if participant_count_row else 0
        
        if meeting_data:
            # Convert database row to dictionary
            meeting = {
                "id": meeting_data['meeting_id'],
                "topic": f"Meeting {meeting_id}",
                "status": "active" if meeting_data['start_time'] else "unknown",
                "start_time": meeting_data['start_time'],
                "duration": 0,  # We don't track this yet
                "participant_count": participant_count
            }
            return meeting
        else:
            # If meeting doesn't exist in the database yet, create a placeholder
            meeting = {
                "id": meeting_id,
                "topic": f"Meeting {meeting_id}",
                "status": "unknown",
                "start_time": None,
                "duration": 0,
                "participant_count": 0
            }
            return meeting
            
    except Exception as e:
        logger.error(f"Database error in get_meeting_details: {str(e)}")
        return None
    finally:
        conn.close()

def get_transcriptions_db(meeting_id):
    """
    Retrieve transcriptions for a meeting from the database
    
    Args:
        meeting_id (str): The ID of the meeting
        
    Returns:
        list: List of transcription objects or empty list if none found
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, meeting_id, participant_id, participant_name, 
               transcript, timestamp, sentiment_score, browser_id
        FROM transcriptions 
        WHERE meeting_id = ? 
        ORDER BY timestamp ASC
        ''', (meeting_id,))
        
        rows = cursor.fetchall()
        
        # Convert rows to dictionaries
        transcriptions = []
        for row in rows:
            transcription = dict(row)
            transcriptions.append(transcription)
            
        return transcriptions
        
    except Exception as e:
        logger.error(f"Database error in get_transcriptions_db: {str(e)}")
        return []
    finally:
        conn.close()

def save_transcription_db(meeting_id, participant_id, participant_name, transcript, sentiment_score, timestamp, browser_id):
    """Save transcription data to the database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO transcriptions (meeting_id, participant_id, participant_name, transcript, timestamp, sentiment_score, browser_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (meeting_id, participant_id, participant_name, transcript, timestamp, sentiment_score, browser_id))
        
        # Get the inserted ID
        transcription_id = cursor.lastrowid
        
        conn.commit()
        logger.info(f"Transcription saved for meeting {meeting_id}, participant {participant_name}")
        return transcription_id
    except Exception as e:
        logger.error(f"Error saving transcription: {str(e)}")
        return None
    finally:
        conn.close()

def save_engagement_data_db(meeting_id, participant_data):
    """Save engagement data to the database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if participant already exists
        cursor.execute('''
        SELECT id FROM engagement_data
        WHERE meeting_id = ? AND participant_id = ?
        ''', (meeting_id, participant_data.get('id')))
        
        result = cursor.fetchone()
        
        if result:
            # Update existing record
            cursor.execute('''
            UPDATE engagement_data
            SET leave_time = ?, duration = ?, talk_time = ?
            WHERE meeting_id = ? AND participant_id = ?
            ''', (
                participant_data.get('leave_time'),
                participant_data.get('duration', 0),
                participant_data.get('talk_time', 0),
                meeting_id,
                participant_data.get('id')
            ))
        else:
            # Insert new record
            cursor.execute('''
            INSERT INTO engagement_data (
                meeting_id, participant_id, participant_name, join_time, leave_time, duration, talk_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                meeting_id,
                participant_data.get('id'),
                participant_data.get('name'),
                participant_data.get('join_time'),
                participant_data.get('leave_time'),
                participant_data.get('duration', 0),
                participant_data.get('talk_time', 0)
            ))
        
        conn.commit()
        logger.info(f"Engagement data saved for meeting {meeting_id}, participant {participant_data.get('name')}")
    except Exception as e:
        logger.error(f"Error saving engagement data: {str(e)}")
    finally:
        conn.close()

def update_participant_leave_time_db(meeting_id, participant_id):
    """Update the leave time for a participant"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Get current time
        leave_time = datetime.now().isoformat()
        
        # Get join time to calculate duration
        cursor.execute('''
        SELECT join_time FROM engagement_data
        WHERE meeting_id = ? AND participant_id = ?
        ''', (meeting_id, participant_id))
        
        result = cursor.fetchone()
        
        if result:
            join_time = datetime.fromisoformat(result[0])
            leave_time_dt = datetime.fromisoformat(leave_time)
            duration = int((leave_time_dt - join_time).total_seconds())
            
            # Update record
            cursor.execute('''
            UPDATE engagement_data
            SET leave_time = ?, duration = ?
            WHERE meeting_id = ? AND participant_id = ?
            ''', (leave_time, duration, meeting_id, participant_id))
            
            conn.commit()
            logger.info(f"Updated leave time for participant {participant_id} in meeting {meeting_id}")
        else:
            logger.warning(f"Participant {participant_id} not found in meeting {meeting_id}")
    except Exception as e:
        logger.error(f"Error updating participant leave time: {str(e)}")
    finally:
        conn.close()

def update_participant_talk_time_db(meeting_id, participant_id, talk_time):
    """Update the talk time for a participant"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Update record
        cursor.execute('''
        UPDATE engagement_data
        SET talk_time = ?
        WHERE meeting_id = ? AND participant_id = ?
        ''', (talk_time, meeting_id, participant_id))
        
        conn.commit()
        logger.info(f"Updated talk time for participant {participant_id} in meeting {meeting_id}: {talk_time}s")
    except Exception as e:
        logger.error(f"Error updating participant talk time: {str(e)}")
    finally:
        conn.close()

def update_participant_status_db(meeting_id, participant_id, is_active, browser_id):
    """
    Update the active status of a participant in the database
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if participant exists in engagement_data
        cursor.execute(
            "SELECT participant_id FROM engagement_data WHERE meeting_id = ? AND participant_id = ?",
            (meeting_id, participant_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            # We don't have an is_active field in the database.py schema,
            # so we'll update other fields as a way to track activity
            cursor.execute(
                "UPDATE engagement_data SET leave_time = ? WHERE meeting_id = ? AND participant_id = ?",
                (None if is_active else datetime.now().isoformat(), meeting_id, participant_id)
            )
        else:
            # Insert new participant with an active status
            cursor.execute(
                "INSERT INTO engagement_data (meeting_id, participant_id, participant_name, join_time) VALUES (?, ?, ?, ?)",
                (meeting_id, participant_id, f"Participant {participant_id}", datetime.now().isoformat())
            )
            
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Database error in update_participant_status: {str(e)}")
        return False

def get_meeting_participants_db(meeting_id):
    """Get all participants for a specific meeting"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM engagement_data
        WHERE meeting_id = ?
        ORDER BY talk_time DESC
        ''', (meeting_id,))
        
        rows = cursor.fetchall()
        participants = []
        
        for row in rows:
            participants.append({
                'id': row['participant_id'],
                'name': row['participant_name'],
                'join_time': row['join_time'],
                'leave_time': row['leave_time'],
                'duration': row['duration'],
                'talk_time': row['talk_time']
            })
        
        return participants
    except Exception as e:
        logger.error(f"Error fetching meeting participants: {str(e)}")
        return []
    finally:
        conn.close()

def get_meeting_transcriptions_db(meeting_id, limit=50):
    """Get transcriptions for a specific meeting"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM transcriptions
        WHERE meeting_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (meeting_id, limit))
        
        rows = cursor.fetchall()
        transcriptions = []
        
        for row in rows:
            transcriptions.append({
                'id': row['id'],
                'participant_id': row['participant_id'],
                'participant_name': row['participant_name'],
                'transcript': row['transcript'],
                'timestamp': row['timestamp'],
                'sentiment_score': row['sentiment_score']
            })
        
        return transcriptions
    except Exception as e:
        logger.error(f"Error fetching meeting transcriptions: {str(e)}")
        return []
    finally:
        conn.close()

def save_meeting_transcript_db(meeting_id, transcript_data):
    """Save a consolidated meeting transcript when meeting ends"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Add a new table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS meeting_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL UNIQUE,
            full_transcript TEXT NOT NULL,
            transcript_data TEXT NOT NULL,  # JSON string containing all transcript segments
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Consolidate all transcript text
        full_transcript = '\n\n'.join(f"{item.get('participant_name')} ({item.get('timestamp')}): {item.get('transcript')}" 
                                     for item in transcript_data)
        
        # Convert transcript data to JSON string
        transcript_json = json.dumps(transcript_data)
        
        # Save consolidated transcript
        cursor.execute('''
        INSERT INTO meeting_transcripts (meeting_id, full_transcript, transcript_data)
        VALUES (?, ?, ?)
        ON CONFLICT(meeting_id) DO UPDATE SET
        full_transcript = ?, transcript_data = ?, created_at = CURRENT_TIMESTAMP
        ''', (meeting_id, full_transcript, transcript_json, full_transcript, transcript_json))
        
        conn.commit()
        logger.info(f"Saved consolidated transcript for meeting {meeting_id}")
    except Exception as e:
        logger.error(f"Error saving meeting transcript: {str(e)}")
    finally:
        conn.close()
