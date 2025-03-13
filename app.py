import os
import json
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from database import init_db, save_transcription, save_engagement_data, get_meeting_participants, get_meeting_transcriptions

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret!')
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
init_db()

# Zoom API credentials
ZOOM_API_KEY = os.getenv('ZOOM_API_KEY')
ZOOM_API_SECRET = os.getenv('ZOOM_API_SECRET')
#ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')

# Routes
@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/webhook/transcription', methods=['POST'])
def transcription_webhook():
    """
    Handle incoming transcription data from Zoom webhooks
    Documentation: https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/webhookTranscription
    """
    try:
        data = request.json
        logger.info(f"Received transcription webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'caption':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')
            participant_id = data.get('payload', {}).get('object', {}).get('participant', {}).get('id')
            participant_name = data.get('payload', {}).get('object', {}).get('participant', {}).get('name')
            transcript_text = data.get('payload', {}).get('object', {}).get('caption')
            timestamp = data.get('payload', {}).get('object', {}).get('timestamp')
            
            # Perform sentiment analysis
            sentiment_score = analyze_sentiment(transcript_text)
            
            # Save transcription to database
            save_transcription(
                meeting_id=meeting_id,
                participant_id=participant_id,
                participant_name=participant_name,
                transcript=transcript_text,
                timestamp=timestamp,
                sentiment_score=sentiment_score
            )
            
            # Emit to connected clients
            socketio.emit('new_transcription', {
                'meeting_id': meeting_id,
                'participant_id': participant_id,
                'participant_name': participant_name,
                'transcript': transcript_text,
                'timestamp': timestamp,
                'sentiment_score': sentiment_score
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error processing transcription webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

@app.route('/api/engagement/<meeting_id>', methods=['GET'])
def get_engagement_data(meeting_id):
    """Fetch engagement data for a specific meeting"""
    try:
        # Get meeting participants from database
        participants = get_meeting_participants(meeting_id)
        
        # If no participants found, fetch from Zoom API
        if not participants:
            participants = fetch_zoom_meeting_participants(meeting_id)
        
        return jsonify({"status": "success", "data": participants}), 200
    except Exception as e:
        logger.error(f"Error fetching engagement data: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transcriptions/<meeting_id>', methods=['GET'])
def get_transcriptions(meeting_id):
    """Fetch transcriptions for a specific meeting"""
    try:
        transcriptions = get_meeting_transcriptions(meeting_id)
        return jsonify({"status": "success", "data": transcriptions}), 200
    except Exception as e:
        logger.error(f"Error fetching transcriptions: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def fetch_zoom_meeting_participants(meeting_id):
    """
    Fetch participant data from Zoom API
    Documentation: https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/meetingParticipants
    """
    try:
        # Generate JWT token for Zoom API
        headers = {
            "Authorization": f"Bearer {generate_zoom_jwt_token()}",
            "Content-Type": "application/json"
        }
        
        # Make request to Zoom API
        response = requests.get(
            f"https://api.zoom.us/v2/metrics/meetings/{meeting_id}/participants",
            headers=headers
        )
        
        if response.status_code == 200:
            participants_data = response.json().get('participants', [])
            
            # Process and store participant data
            processed_participants = []
            for participant in participants_data:
                participant_info = {
                    'id': participant.get('id'),
                    'name': participant.get('name'),
                    'user_id': participant.get('user_id'),
                    'join_time': participant.get('join_time'),
                    'leave_time': participant.get('leave_time'),
                    'duration': participant.get('duration'),
                    'talk_time': participant.get('talk_time', 0)
                }
                
                # Save to database
                save_engagement_data(meeting_id, participant_info)
                processed_participants.append(participant_info)
                
            return processed_participants
        else:
            logger.error(f"Failed to fetch participants: {response.status_code}, {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error fetching Zoom meeting participants: {str(e)}")
        return []

def analyze_sentiment(text):
    """
    Simple sentiment analysis function
    In a production environment, you might want to use a more sophisticated solution
    like NLTK, TextBlob, or a cloud-based sentiment analysis service
    """
    # This is a very basic implementation
    positive_words = ['good', 'great', 'excellent', 'happy', 'positive', 'agree', 'yes', 'awesome']
    negative_words = ['bad', 'poor', 'terrible', 'sad', 'negative', 'disagree', 'no', 'awful']
    
    text = text.lower()
    words = text.split()
    
    positive_count = sum(1 for word in words if word in positive_words)
    negative_count = sum(1 for word in words if word in negative_words)
    
    if positive_count > negative_count:
        return 1  # Positive
    elif negative_count > positive_count:
        return -1  # Negative
    else:
        return 0  # Neutral

def generate_zoom_jwt_token():
    """
    Generate a JWT token for Zoom API authentication
    In a production environment, you'd want to use a proper JWT library
    """
    # This is a placeholder. In a real app, you would use a proper JWT implementation
    import jwt
    import time
    
    payload = {
        'iss': ZOOM_API_KEY,
        'exp': int(time.time() + 3600)
    }
    
    token = jwt.encode(payload, ZOOM_API_SECRET, algorithm='HS256')
    return token

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
