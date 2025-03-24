import sqlite3
import json
import logging
from datetime import datetime

DATABASE_PATH = 'zoom_engagement.db'

########################################################################################################################
# Database Initialization
########################################################################################################################

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
            sentiment_score REAL DEFAULT 0,
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
        
        # Create final transcripts table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS final_meeting_transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id TEXT NOT NULL UNIQUE,
            meeting_date TEXT NOT NULL,
            transcript_data TEXT NOT NULL,
            participant_data TEXT NOT NULL,
            full_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
    finally:
        conn.close()

########################################################################################################################
# Database Meeting Operations
########################################################################################################################

def get_meeting_info_db(meeting_id):
    """Retrieve meeting details from the database"""
    try:
        # Connect to database
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if meeting exists in engagement data
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
        
        # Check if meeting has ended (has final transcript)
        cursor.execute(
            "SELECT 1 FROM final_meeting_transcripts WHERE meeting_id = ? LIMIT 1",
            (meeting_id,)
        )
        is_ended = cursor.fetchone() is not None
        
        if meeting_data:
            meeting = {
                "id": meeting_data['meeting_id'],
                "topic": f"Meeting {meeting_id}",
                "status": "ended" if is_ended else "active",
                "start_time": meeting_data['start_time'],
                "duration": 0,  # We don't track this yet
                "participant_count": participant_count
            }
        else:
            # Meeting doesn't exist in the database yet
            meeting = {
                "id": meeting_id,
                "topic": f"Meeting {meeting_id}",
                "status": "offline",  # Changed from "unknown" to "offline"
                "start_time": None,
                "duration": 0,
                "participant_count": 0
            }

        return meeting
            
    except Exception as e:
        print(f"Database error in get_meeting_info_db: {str(e)}")
        return None
    finally:
        conn.close()

def get_transcriptions_db(meeting_id):
    """Retrieve transcriptions for a meeting from the database"""
    print("inside get   transcriptions_db")
    print("meeting id:", meeting_id)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT *
        FROM transcriptions
        WHERE meeting_id = ? 
        ORDER BY timestamp ASC
        ''', (meeting_id,))
        
        rows = cursor.fetchall()

        print("num rows:", rows)
        
        # Convert rows to dictionaries
        transcriptions = []
        for row in rows:
            transcription = dict(row)
            transcriptions.append(transcription)
            
        return transcriptions
        
    except Exception as e:
        print(f"Database error in get_transcriptions_db: {str(e)}")
        return []
    finally:
        conn.close()

def save_transcription_db(meeting_id, participant_id, participant_name, transcript, sentiment_score, timestamp, browser_id):
    """Save transcription data to the database"""
    print("meeting_id: ", meeting_id)
    meeting_id = meeting_id.replace(" ", "")    # remove spaces since fetching already has a cleaned meeting id
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
        print(f"Transcription saved for meeting {meeting_id}, participant {participant_name}: {transcript}")
        return transcription_id
    except Exception as e:
        print(f"Error saving transcription: {str(e)}")
        return None
    finally:
        conn.close()

def save_engagement_data_db(meeting_id, participant_data):
    """Save engagement data to the database"""
    print("meeting_id: ", meeting_id)
    meeting_id = meeting_id.replace(" ", "")    # remove spaces!!
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
        print(f"Engagement data saved for meeting {meeting_id}, participant {participant_data.get('name')}")
        return True
    except Exception as e:
        print(f"Error saving engagement data: {str(e)}")
        return False
    finally:
        conn.close()

def save_engagement_snapshot_db(meeting_id, participant_id, is_engaged, timestamp, browser_id):
    """Save engagement snapshot data to the database"""
    meeting_id = meeting_id.replace(" ", "")  # remove spaces to ensure consistency
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # First, we need to make sure the participant exists in the engagement_data table
        cursor.execute('''
        SELECT id FROM engagement_data
        WHERE meeting_id = ? AND participant_id = ?
        ''', (meeting_id, participant_id))
        
        result = cursor.fetchone()
        
        if not result:
            # If participant doesn't exist, create a basic record first
            cursor.execute('''
            INSERT INTO engagement_data (
                meeting_id, participant_id, participant_name, join_time
            )
            VALUES (?, ?, ?, ?)
            ''', (
                meeting_id,
                participant_id,
                f"Participant {participant_id}",  # Default name if not known
                timestamp
            ))
        
        # Now we can update the engagement data
        # Since we don't have a dedicated engagement_snapshots table,
        # we'll update the is_active field in the engagement_data table
        cursor.execute('''
        UPDATE engagement_data
        SET is_active = ?, browser_id = ?
        WHERE meeting_id = ? AND participant_id = ?
        ''', (is_engaged, browser_id, meeting_id, participant_id))
        
        conn.commit()
        print(f"Engagement snapshot saved for meeting {meeting_id}, participant {participant_id}: {is_engaged}")
        return True
    except Exception as e:
        print(f"Error saving engagement snapshot: {str(e)}")
        return False
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
            print(f"Updated leave time for participant {participant_id} in meeting {meeting_id}")
            return True
        else:
            logger.warning(f"Participant {participant_id} not found in meeting {meeting_id}")
            return False
    except Exception as e:
        print(f"Error updating participant leave time: {str(e)}")
        return False
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
        print(f"Updated talk time for participant {participant_id} in meeting {meeting_id}: {talk_time}s")
        return True
    except Exception as e:
        print(f"Error updating participant talk time: {str(e)}")
        return False
    finally:
        conn.close()

def update_participant_status_db(meeting_id, participant_id, is_active, browser_id):
    """Update the active status of a participant in the database"""
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
            # We don't have an is_active field in the database schema,
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
        return True
        
    except Exception as e:
        print(f"Database error in update_participant_status_db: {str(e)}")
        return False
    finally:
        conn.close()

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
        print(f"Error fetching meeting participants: {str(e)}")
        return []
    finally:
        conn.close()

########################################################################################################################
# Database Meeting End Operations
########################################################################################################################

def get_final_transcript_db(meeting_id):
    """
    Retrieve the final transcript for a meeting
    Returns the transcript data or None if not found
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
        SELECT * FROM final_meeting_transcripts
        WHERE meeting_id = ?
        ''', (meeting_id,))

        result = cursor.fetchone()

        if result:
            # Parse the JSON data
            transcript_data_json = result['transcript_data']
            participant_data_json = result['participant_data']

            transcript_data = json.loads(transcript_data_json)
            participant_data = json.loads(participant_data_json)


            # Try to get meeting_topic from transcript data.  Adjust this if your structure is different.
            meeting_topic = transcript_data[0].get('meeting_topic', 'Untitled Meeting') if transcript_data else 'Untitled Meeting'

            final_transcript = {
                'meeting_id': result['meeting_id'],
                'meeting_date': result['meeting_date'],
                'created_at': result['created_at'],
                'transcript_data': transcript_data,
                'participant_data': participant_data,
                'meeting_topic': meeting_topic  # Add meeting topic
            }
            return final_transcript
        else:
            return None

    except Exception as e:
        print(f"Error retrieving final transcript: {str(e)}")
        return None
    finally:
        conn.close()

def save_and_archive_meeting_data_db(meeting_id):
    """
    Archive meeting data to permanent storage
    This is called when a meeting ends
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row # Enable column access by name
        cursor = conn.cursor()

        # Get meeting transcriptions
        cursor.execute('''
        SELECT * FROM transcriptions
        WHERE meeting_id = ?
        ORDER BY timestamp ASC
        ''', (meeting_id,))
        transcriptions = cursor.fetchall()

        # Get meeting engagement data
        cursor.execute('''
        SELECT * FROM engagement_data
        WHERE meeting_id = ?
        ''', (meeting_id,))
        engagement = cursor.fetchall()

        # Prepare transcript data for archive
        transcript_data = []
        for t in transcriptions:
            transcript_data.append({
                'participant_id': t['participant_id'],
                'participant_name': t['participant_name'],
                'transcript': t['transcript'],
                'sentiment_score': t['sentiment_score'],
                'timestamp': t['timestamp']
            })

        # Prepare participant data for archive
        participant_data = []
        for e in engagement:
            participant_data.append({
                'id': e['participant_id'],
                'name': e['participant_name'],
                'join_time': e['join_time'],
                'leave_time': e['leave_time'],
                'duration': e['duration'],
                'talk_time': e['talk_time']
            })

        # Get meeting info
        meeting_info = get_meeting_info_db(meeting_id)

        # Create archive data structure
        archive_data = {
            'meeting_id': meeting_id,
            'meeting_topic': meeting_info['topic'] if meeting_info else 'Untitled Meeting',
            'start_time': meeting_info['start_time'] if meeting_info else None,
            'end_time': datetime.now().isoformat(),
            'participant_count': len(participant_data),
            'participant_data': participant_data,
            'transcript_data': transcript_data
        }
          # Prepare full text for search purposes
        full_text = ' '.join([t['transcript'] for t in transcript_data])
        # Save to permanent storage
        cursor.execute('''
        INSERT OR REPLACE INTO final_meeting_transcripts
        (meeting_id, meeting_date, transcript_data, participant_data, full_text)
        VALUES (?, ?, ?, ?, ?)
        ''', (
            meeting_id,
            archive_data['start_time'],
            json.dumps(archive_data['transcript_data']),
            json.dumps(archive_data['participant_data']),
            full_text
        ))
        conn.commit()
        print(f"Meeting data archived for meeting {meeting_id}")
        return True
    except Exception as e:
        print(f"Error archiving meeting data: {str(e)}")
        return False
    finally:
        conn.close()
