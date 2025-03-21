import os
import json
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from database import init_db, get_meeting_info_db, save_transcription_db, save_engagement_data_db, get_meeting_participants_db, get_meeting_transcriptions_db, update_participant_leave_time_db, update_participant_status_db, update_participant_talk_time_db, get_transcriptions_db

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret!')
socketio = SocketIO(app, async_mode='gevent')

# Initialize database
init_db()

def get_db_connection():
    """Get a connection to the SQLite database"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

########################################################################################################################
# HTML Routes
########################################################################################################################

@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/meeting-transcript/<meeting_id>')
def meeting_transcript_page(meeting_id):
    """Render the meeting transcript page on meeting end"""
    return render_template('meeting_transcript.html', meeting_id=meeting_id)

########################################################################################################################
# Webhook Routes
########################################################################################################################

def handle_participant_joined(data):
    """Handle participant joined events from Zoom webhooks"""
    logger.info("WEBHOOK RECEIVED - PARTICIPANT JOINED")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {request.get_data()}")
    
    try:
        data = request.json
        logger.info(f"Received participant joined webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'meeting.participant_joined':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')
            participant = data.get('payload', {}).get('object', {}).get('participant', {})
            
            participant_info = {
                'id': participant.get('id'),
                'name': participant.get('user_name'),
                'user_id': participant.get('user_id'),
                'join_time': datetime.now().isoformat(),
                'leave_time': None,
                'duration': 0,
                'talk_time': 0
            }
            
            # Save participant data to database
            save_engagement_data(meeting_id, participant_info)
            
            # Emit to connected clients
            socketio.emit('participant_joined', {
                'meeting_id': meeting_id,
                'participant': participant_info
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error processing participant joined webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

def handle_participant_left(data):
    """Handle participant left events from Zoom webhooks"""
    logger.info("WEBHOOK RECEIVED - PARTICIPANT LEFT")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {request.get_data()}")
    
    try:
        data = request.json
        logger.info(f"Received participant left webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'meeting.participant_left':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')
            participant = data.get('payload', {}).get('object', {}).get('participant', {})
            participant_id = participant.get('id')
            
            # Update the participant leave time
            update_participant_leave_time(meeting_id, participant_id)
            
            # Emit to connected clients
            socketio.emit('participant_left', {
                'meeting_id': meeting_id,
                'participant_id': participant_id
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error processing participant left webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

def handle_meeting_started(data):
    """Handle meeting started events from Zoom webhooks"""
    logger.info("WEBHOOK RECEIVED - MEETING STARTED")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {request.get_data()}")
    
    try:
        data = request.json
        logger.info(f"Received meeting started webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'meeting.started':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')
            topic = data.get('payload', {}).get('object', {}).get('topic', 'Untitled Meeting')
            
            # Emit to connected clients
            socketio.emit('meeting_started', {
                'meeting_id': meeting_id,
                'topic': topic
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error processing meeting started webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

def handle_meeting_ended(data):
    """Handle meeting ended events from Zoom webhooks"""
    logger.info("WEBHOOK RECEIVED - MEETING ENDED")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {request.get_data()}")
    
    try:
        data = request.json
        logger.info(f"Received meeting ended webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'meeting.ended':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')
            
            # Emit to connected clients
            socketio.emit('meeting_ended', {
                'meeting_id': meeting_id
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error processing meeting ended webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

@app.route("/webhook", methods=["POST"])
def zoom_webhook():
    """Handles Zoom webhook events and routes them accordingly."""
    data = request.json
    event_type = data.get("event")
    
    print(f"Received event: {event_type}")  # Debugging output
    
    try:
        if event_type == "meeting.started":
            return handle_meeting_started(data)
        elif event_type == "meeting.ended":
            return handle_meeting_ended(data)
        elif event_type == "meeting.participant_joined":
            return handle_participant_joined(data)
        elif event_type == "meeting.participant_left":
            return handle_participant_left(data)
        else:
            print(f"Unhandled event type: {event_type}")

    except Exception as e:
        print(f"Error processing webhook event: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "ignored"}), 200

########################################################################################################################
# API Routes
########################################################################################################################

@app.route('/api/meeting/<meeting_id>', methods=['GET'])
def get_meeting_info(meeting_id):
    """Fetch information about a specific meeting"""
    try:
        # Clean meeting_id by removing spaces
        meeting_id = meeting_id.replace(" ", "")
        
        # Get meeting details from the database
        meeting = get_meeting_info_db(meeting_id)
        
        if meeting:
            logger.info(f"Fetched meeting info for meeting {meeting_id}")
            return jsonify({
                "success": True,
                "data": meeting
            }), 200
        else:
            logger.warning(f"Meeting {meeting_id} not found")
            return jsonify({
                "success": False,
                "message": f"Meeting {meeting_id} not found"
            }), 404
            
    except Exception as e:
        logger.error(f"Error fetching meeting info: {str(e)}")
        return jsonify({
            "success": False, 
            "message": str(e)
        }), 500

@app.route('/api/transcriptions/<meeting_id>', methods=['GET'])
def get_transcriptions(meeting_id):
    """Fetch transcriptions for a specific meeting"""
    try:
        # Clean meeting_id by removing spaces
        meeting_id = meeting_id.replace(" ", "")
        
        # Get transcriptions from the database
        transcriptions = get_transcriptions_db(meeting_id)
        
        if transcriptions:
            logger.info(f"Fetched {len(transcriptions)} transcriptions for meeting {meeting_id}")
            return jsonify({
                "success": True,
                "data": transcriptions
            }), 200
        else:
            logger.warning(f"No transcriptions found for meeting {meeting_id}")
            return jsonify({
                "success": False,
                "message": f"No transcriptions found for meeting {meeting_id}"
            }), 404
            
    except Exception as e:
        logger.error(f"Error fetching transcriptions: {str(e)}")
        return jsonify({
            "success": False, 
            "message": str(e)
        }), 500

@app.route('/api/participants/<meeting_id>', methods=['GET'])
def get_participants(meeting_id):
    """Fetch participants for a specific meeting"""
    try:
        # Clean meeting_id by removing spaces
        meeting_id = meeting_id.replace(" ", "")
        
        # Get meeting participants from database
        participants = get_meeting_participants_db(meeting_id)
        logger.info(f"Fetched {len(participants)} participants for meeting {meeting_id}")
        return jsonify({
            "success": True,
            "data": participants
        }), 200
    except Exception as e:
        logger.error(f"Error fetching participants: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/participant/active', methods=['POST'])
def update_participant_active_status():
    """Update the active status of a participant"""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        participant_id = data.get('participant_id')
        is_active = data.get('is_active', False)
        browser_id = data.get('browser_id')
        
        if not meeting_id or not participant_id:
            return jsonify({
                "success": False,
                "message": "Missing required fields: meeting_id or participant_id"
            }), 400
            
        # Update participant active status in the database
        result = update_participant_status_db(meeting_id, participant_id, is_active, browser_id)
        
        if result:
            # Emit socket event to notify clients
            socketio.emit('participant_status_change', {
                'meeting_id': meeting_id,
                'participant_id': participant_id,
                'is_active': is_active
            })
            
            return jsonify({
                "success": True,
                "message": f"Participant status updated to {'active' if is_active else 'inactive'}"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Failed to update participant status"
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating participant status: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/transcription', methods=['POST'])
def add_transcription():
    """Add a new transcription entry"""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        participant_id = data.get('participant_id')
        participant_name = data.get('participant_name')
        transcript = data.get('transcript')
        timestamp = data.get('timestamp')
        browser_id = data.get('browser_id')
        
        if not all([meeting_id, participant_id, participant_name, transcript]):
            return jsonify({
                "success": False,
                "message": "Missing required fields"
            }), 400
            
        # Process the transcription (sentiment analysis, etc.)
        sentiment_score = analyze_sentiment(transcript)
        
        # Save to database
        transcription_id = save_transcription_db(
            meeting_id, 
            participant_id, 
            participant_name, 
            transcript, 
            sentiment_score, 
            timestamp, 
            browser_id
        )
        
        if transcription_id:
            # Emit socket event with the new transcription
            transcription_data = {
                'id': transcription_id,
                'meeting_id': meeting_id,
                'participant_id': participant_id,
                'participant_name': participant_name,
                'transcript': transcript,
                'sentiment_score': sentiment_score,
                'timestamp': timestamp
            }
            
            socketio.emit('new_transcription', transcription_data)
            
            return jsonify({
                "success": True,
                "id": transcription_id,
                "sentiment_score": sentiment_score
            }), 201
        else:
            return jsonify({
                "success": False,
                "message": "Failed to save transcription"
            }), 500
            
    except Exception as e:
        logger.error(f"Error adding transcription: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/talk-time', methods=['POST'])
def update_talk_time():
    """Update talk time for a participant"""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        participant_id = data.get('participant_id')
        talk_time = data.get('talk_time', 0)
        browser_id = data.get('browser_id')
        
        if not meeting_id or not participant_id:
            return jsonify({
                "success": False,
                "message": "Missing required fields: meeting_id or participant_id"
            }), 400
            
        # Update talk time in the database
        result = update_participant_talk_time_db(meeting_id, participant_id, talk_time, browser_id)
        
        if result:
            # Emit socket event to notify clients
            socketio.emit('talk_time_updated', {
                'meeting_id': meeting_id,
                'participant_id': participant_id,
                'talk_time': talk_time
            })
            
            return jsonify({
                "success": True,
                "message": f"Talk time updated to {talk_time} seconds"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Failed to update talk time"
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating talk time: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# Helper functions for database operations
def analyze_sentiment(text):
    """
    Analyze the sentiment of the given text
    Returns a score between -1 (negative) and 1 (positive)
    """
    try:
        # Here you would integrate with a sentiment analysis library
        # For simplicity, this example uses a basic approach
        # In a production app, you might use NLTK, TextBlob, or a cloud service
        
        # Simple dictionary of positive and negative words
        positive_words = [
            'good', 'great', 'excellent', 'amazing', 'happy', 'like', 'love', 
            'best', 'better', 'yes', 'agree', 'thanks', 'thank', 'appreciate'
        ]
        
        negative_words = [
            'bad', 'terrible', 'awful', 'hate', 'dislike', 'worst', 'worse',
            'no', 'not', 'disagree', 'difficult', 'problem', 'issue', 'sorry'
        ]
        
        # Convert to lowercase and split into words
        words = text.lower().split()
        
        # Count positive and negative words
        positive_count = sum(1 for word in words if word in positive_words)
        negative_count = sum(1 for word in words if word in negative_words)
        
        # Calculate sentiment score between -1 and 1
        total = positive_count + negative_count
        if total == 0:
            return 0  # Neutral
        
        score = (positive_count - negative_count) / total
        return score
        
    except Exception as e:
        logger.error(f"Error in sentiment analysis: {str(e)}")
        return 0  # Return neutral on error

@socketio.on('connect')
def handle_connect():
    """Handle client connection to WebSocket"""
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection from WebSocket"""
    logger.info('Client disconnected')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)
