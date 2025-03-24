import os
import json
import logging
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from database import *

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

########################################################################################################################
# HTML Routes
########################################################################################################################

@app.route('/')
def index():
    """Render the main dashboard page"""
    return render_template('index.html')

@app.route('/transcript-list/')
def transcript_list():
    """Render the transcript list page"""
    return render_template('transcript_list.html')

@app.route('/transcript-list/<meeting_id>')
def transcript_detail(meeting_id):
    """Render the transcript detail page"""
    return render_template('transcript_detail.html', meeting_id=meeting_id)

########################################################################################################################
# Webhook Routes
########################################################################################################################

def handle_participant_joined(data):
    """Handle participant joined events from Zoom webhooks"""
    print("WEBHOOK RECEIVED - PARTICIPANT JOINED")
    try:
        data = request.json
        print(f"Received participant joined webhook: {data}")
        
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
            save_engagement_data_db(meeting_id, participant_info)
            
            # Emit to connected clients
            socketio.emit('participant_joined', {
                'meeting_id': meeting_id,
                'participant': participant_info
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error processing participant joined webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

def handle_participant_left(data):
    """Handle participant left events from Zoom webhooks"""
    print("WEBHOOK RECEIVED - PARTICIPANT LEFT")    
    try:
        data = request.json
        print(f"Received participant left webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'meeting.participant_left':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')
            participant = data.get('payload', {}).get('object', {}).get('participant', {})
            participant_id = participant.get('id')
            
            # Update the participant leave time
            update_participant_leave_time_db(meeting_id, participant_id)
            
            # Emit to connected clients
            socketio.emit('participant_left', {
                'meeting_id': meeting_id,
                'participant_id': participant_id
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error processing participant left webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

def handle_meeting_started(data):
    """Handle meeting started events from Zoom webhooks"""
    print("WEBHOOK RECEIVED - MEETING STARTED")
    try:
        data = request.json
        print(f"Received meeting started webhook: {data}")
        
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
        print(f"Error processing meeting started webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

def handle_meeting_ended(data):
    """Handle meeting ended events from Zoom webhooks"""   
    print("WEBHOOK RECEIVED - MEETING ENDED") 
    try:
        data = request.json
        print(f"Received meeting ended webhook: {data}")
        
        # Verify the webhook event type
        if data.get('event') == 'meeting.ended':
            meeting_id = data.get('payload', {}).get('object', {}).get('id')

            # Archive transcripts to final storage and clear interim data
            save_and_archive_meeting_data_db(meeting_id)
            
            # Emit to connected clients
            socketio.emit('meeting_ended', {
                'meeting_id': meeting_id,
            })
            
            return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"Error processing meeting ended webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
    return jsonify({"status": "ignored"}), 200

@app.route("/webhook", methods=["POST"])
def zoom_webhook():
    """Handles Zoom webhook events and routes them accordingly."""
    data = request.json
    event_type = data.get("event")
    print(f"Received event: {event_type}")
    
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
# Dashboard API Routes
########################################################################################################################

@app.route('/api/meetings/<meeting_id>', methods=['GET'])
def get_meeting_data(meeting_id):
    """Fetch meeting data with optional type parameter"""
    try:
        data_type = request.args.get('type', 'info')  # Default to 'info'
        meeting_id = meeting_id.replace(" ", "")
        
        if data_type == 'info':
            # Get basic meeting information
            data = get_meeting_info_db(meeting_id)
            print(f"Fetching meeting info for meeting {meeting_id}: {data}")
        elif data_type == 'transcriptions':
            # Get live transcriptions
            data = get_transcriptions_db(meeting_id)
            print(f"Fetching transcriptions for meeting {meeting_id}: {data}")
        elif data_type == 'participants':
            # Get participants
            data = get_meeting_participants_db(meeting_id)
            print(f"Fetching participants for meeting {meeting_id}: {data}")
        elif data_type == 'transcript':
            # Try to get final transcript first
            data = get_final_transcript_db(meeting_id)
            print(f"Fetching final transcript for meeting {meeting_id}: {data}")
            # If no final transcript exists, get interim transcriptions
            if not data:
                data = get_transcriptions_db(meeting_id)
                return jsonify({
                    "success": True,
                    "is_final": False,
                    "data": data
                }), 200
            else:
                return jsonify({
                    "success": True, 
                    "is_final": True,
                    "data": data
                }), 200
                
        if data:
            return jsonify({"success": True, "data": data}), 200
        else:
            return jsonify({
                "success": False,
                "message": f"No {data_type} found for meeting {meeting_id}"
            }), 404
            
    except Exception as e:
        print(f"Error fetching meeting data: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

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
        print(f"Error updating participant status: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/transcription', methods=['POST'])
def add_transcription():
    """Add a new transcription entry"""
    print("adding transcription: ", request.json)
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
        print(f"Error adding transcription: {str(e)}")
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
        
        if not meeting_id or not participant_id:
            return jsonify({
                "success": False,
                "message": "Missing required fields: meeting_id or participant_id"
            }), 400
            
        # Update talk time in the database
        result = update_participant_talk_time_db(meeting_id, participant_id, talk_time)
        
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
        print(f"Error updating talk time: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/engagement-snapshot', methods=['POST'])
def update_engagement_snapshot():
    """Update engagement data snapshot for a meeting"""
    try:
        data = request.json
        meeting_id = data.get('meeting_id')
        participant_id = data.get('participant_id')
        is_engaged = data.get('is_engaged', False)
        timestamp = data.get('timestamp', datetime.now().isoformat())
        browser_id = data.get('browser_id')
        
        if not meeting_id or not participant_id:
            return jsonify({
                "success": False,
                "message": "Missing required fields: meeting_id or participant_id"
            }), 400
            
        # Save engagement snapshot to database
        result = save_engagement_snapshot_db(meeting_id, participant_id, is_engaged, timestamp, browser_id)
        
        if result:
            # Emit socket event to notify clients
            socketio.emit('engagement_update', {
                'meeting_id': meeting_id,
                'participant_id': participant_id,
                'is_engaged': is_engaged,
                'timestamp': timestamp
            })
            
            return jsonify({
                "success": True,
                "message": f"Engagement snapshot recorded for participant {participant_id}"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Failed to record engagement snapshot"
            }), 500
            
    except Exception as e:
        print(f"Error updating engagement snapshot: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

########################################################################################################################
# Transcript API Routes
########################################################################################################################

@app.route('/api/transcripts', methods=['GET'])
def get_all_transcripts():
    """Retrieve a list of all available transcripts"""
    print("getting all transcripts")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query to get all final transcripts with basic info
        cursor.execute('''
        SELECT
            meeting_id,
            meeting_date,
            created_at,
            transcript_data,
            participant_data
        FROM final_meeting_transcripts
        ORDER BY created_at DESC
        ''')

        rows = cursor.fetchall()

        # Convert to list of dictionaries
        transcripts = []
        for row in rows:
            # Load JSON data
            transcript_data = json.loads(row['transcript_data'])
            participant_data = json.loads(row['participant_data'])

            # Extract meeting topic from transcript data (if available)
            meeting_topic = transcript_data[0].get('meeting_topic', "Untitled Meeting") if transcript_data else "Untitled Meeting"  # Adjust based on actual structure

            # Get participant count from participant data
            participant_count = len(participant_data) if participant_data else 0

            transcripts.append({
                'meeting_id': row['meeting_id'],
                'meeting_date': row['meeting_date'],
                'created_at': row['created_at'],
                'meeting_topic': meeting_topic,
                'participant_count': participant_count
            })

        return jsonify({
            "success": True,
            "data": transcripts
        }), 200

    except Exception as e:
        print(f"Error retrieving transcript list: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
    finally:
        conn.close()

@app.route('/api/transcripts/<meeting_id>', methods=['GET'])
def get_final_transcript(meeting_id):
    """Retrieve archived transcript for a meeting"""
    print("final transcript meeting id: ", meeting_id)
    try:
        result = get_final_transcript_db(meeting_id)
        
        if result:
            return jsonify({
                "success": True,
                "data": result
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": f"No final transcript found for meeting {meeting_id}"
            }), 404
            
    except Exception as e:
        print(f"Error retrieving final transcript: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@app.route('/api/transcripts/<meeting_id>', methods=['DELETE'])
def delete_permanent_transcript(meeting_id):
    """Delete a permanent transcript record"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Delete the final transcript
        cursor.execute('''
        DELETE FROM final_meeting_transcripts
        WHERE meeting_id = ?
        ''', (meeting_id,))
        
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"Deleted permanent transcript for meeting {meeting_id}")
            return jsonify({
                "success": True,
                "message": f"Permanent transcript for meeting {meeting_id} deleted"
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": f"No permanent transcript found for meeting {meeting_id}"
            }), 404
            
    except Exception as e:
        print(f"Error deleting permanent transcript: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500
    finally:
        conn.close()

########################################################################################################################
# Sentiment Analysis
########################################################################################################################

def analyze_sentiment(text):
    """
    Analyze the sentiment of the given text
    Returns a score between -1 (negative) and 1 (positive)
    """
    try:
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
        print(f"Error in sentiment analysis: {str(e)}")
        return 0  # Return neutral on error

########################################################################################################################
# SocketIO Events
########################################################################################################################

@socketio.on('connect')
def handle_connect():
    """Handle client connection to WebSocket"""
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection from WebSocket"""
    print('Client disconnected')

########################################################################################################################
# Main - Run the app
########################################################################################################################

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8000)
