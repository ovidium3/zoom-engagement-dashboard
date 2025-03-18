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
socketio = SocketIO(app, async_mode='gevent')

# Initialize database
init_db()

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
    logger.info("WEBHOOK RECEIVED - TRANSCRIPTION")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Body: {request.get_data()}")
    
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

@app.route('/webhook/participant_joined', methods=['POST'])
def participant_joined_webhook():
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

@app.route('/webhook/participant_left', methods=['POST'])
def participant_left_webhook():
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
            
            # Get the participant from database to update leave time
            from database import update_participant_leave_time
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

@app.route('/api/engagement/<meeting_id>', methods=['GET'])
def get_engagement_data(meeting_id):
    """Fetch engagement data for a specific meeting"""
    try:
        # Clean meeting_id by removing spaces
        meeting_id = meeting_id.replace(" ", "")
        
        # Get meeting participants from database only (no API fallback for free accounts)
        participants = get_meeting_participants(meeting_id)
        print(f"participants: {participants}")
        return jsonify({"status": "success", "data": participants}), 200
    except Exception as e:
        logger.error(f"Error fetching engagement data: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transcriptions/<meeting_id>', methods=['GET'])
def get_transcriptions(meeting_id):
    """Fetch transcriptions for a specific meeting"""
    try:
        # Clean meeting_id by removing spaces
        meeting_id = meeting_id.replace(" ", "")

        transcriptions = get_meeting_transcriptions(meeting_id)
        print(f"transcriptions: {transcriptions}")
        return jsonify({"status": "success", "data": transcriptions}), 200
    except Exception as e:
        logger.error(f"Error fetching transcriptions: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Add the new test endpoint here
@app.route('/test/store-dummy-data/<meeting_id>', methods=['GET'])
def store_dummy_data(meeting_id):
    """Store some dummy data for testing"""
    try:
        # Clean meeting_id
        meeting_id = meeting_id.replace(" ", "")
        
        # Store dummy participant
        dummy_participant = {
            'id': '123456',
            'name': 'Test User',
            'user_id': '789',
            'join_time': datetime.now().isoformat(),
            'leave_time': None,
            'duration': 0,
            'talk_time': 0
        }
        save_engagement_data(meeting_id, dummy_participant)
        
        # Store dummy transcription
        save_transcription(
            meeting_id=meeting_id,
            participant_id='123456',
            participant_name='Test User',
            transcript='This is a test transcription',
            timestamp=datetime.now().isoformat(),
            sentiment_score=0
        )
        
        return jsonify({"status": "success", "message": "Dummy data stored"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook-test', methods=['GET'])
def webhook_test():
    """Test page for webhook verification"""
    return "Zoom Webhook Verification Successful", 200

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
