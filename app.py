import os
import json
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from database import init_db, save_transcription, save_engagement_data, get_meeting_participants, get_meeting_transcriptions, update_participant_leave_time

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

@app.route('/meeting-transcript/<meeting_id>')
def meeting_transcript_page(meeting_id):
    """Render the meeting transcript page on meeting end"""
    return render_template('meeting_transcript.html', meeting_id=meeting_id)

#@app.route('/webhook/participant_joined', methods=['POST'])
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

#@app.route('/webhook/participant_left', methods=['POST'])
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

#@app.route('/webhook/meeting_started', methods=['POST'])
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

#@app.route('/webhook/meeting_ended', methods=['POST'])
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

@app.route('/api/transcription', methods=['POST'])
def receive_transcription():
    """Receive transcription data from Web Speech API via the client"""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        participant_id = data.get('participant_id')
        participant_name = data.get('participant_name')
        transcript = data.get('transcript')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # Perform sentiment analysis
        sentiment_score = analyze_sentiment(transcript)
        
        # Save transcription to database
        save_transcription(
            meeting_id=meeting_id,
            participant_id=participant_id,
            participant_name=participant_name,
            transcript=transcript,
            timestamp=timestamp,
            sentiment_score=sentiment_score
        )
        
        # Emit to connected clients
        socketio.emit('new_transcription', {
            'meeting_id': meeting_id,
            'participant_id': participant_id,
            'participant_name': participant_name,
            'transcript': transcript,
            'timestamp': timestamp,
            'sentiment_score': sentiment_score
        })
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error processing transcription: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/engagement/<meeting_id>', methods=['GET'])
def get_engagement_data(meeting_id):
    """Fetch engagement data for a specific meeting"""
    try:
        # Clean meeting_id by removing spaces
        meeting_id = meeting_id.replace(" ", "")
        
        # Get meeting participants from database
        participants = get_meeting_participants(meeting_id)
        logger.info(f"Fetched {len(participants)} participants for meeting {meeting_id}")
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
        logger.info(f"Fetched {len(transcriptions)} transcriptions for meeting {meeting_id}")
        return jsonify({"status": "success", "data": transcriptions}), 200
    except Exception as e:
        logger.error(f"Error fetching transcriptions: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/talk-time', methods=['POST'])
def update_talk_time():
    """Update participant talk time"""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        participant_id = data.get('participant_id')
        talk_time = data.get('talk_time', 0)
        
        # Update talk time in database
        from database import update_participant_talk_time
        update_participant_talk_time(meeting_id, participant_id, talk_time)
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"Error updating talk time: {str(e)}")
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
