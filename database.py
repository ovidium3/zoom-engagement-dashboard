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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
    finally:
        conn.close()

def save_transcription(meeting_id, participant_id, participant_name, transcript, timestamp, sentiment_score=0):
    """Save transcription data to the database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO transcriptions (meeting_id, participant_id, participant_name, transcript, timestamp, sentiment_score)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (meeting_id, participant_id, participant_name, transcript, timestamp, sentiment_score))
        
        conn.commit()
        logger.info(f"Transcription saved for meeting {meeting_id}, participant {participant_name}")
    except Exception as e:
        logger.error(f"Error saving transcription: {str(e)}")
    finally:
        conn.close()

def save_engagement_data(meeting_id, participant_data):
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

def get_meeting_participants(meeting_id):
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

def get_meeting_transcriptions(meeting_id, limit=50):
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
