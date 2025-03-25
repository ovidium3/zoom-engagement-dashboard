// Connect to WebSocket server
const socket = io();
let currentMeetingId = '';
let meetingParticipants = [];

// Initialize engagement metrics tracking
const metricsData = {
    sentiment: {
        current: 0,
        previous: 0,
        values: [],
        positive: 0,
        neutral: 0,
        negative: 0
    },
    engagement: {
        current: 0,
        previous: 0,
        values: []
    },
    meetingScore: {
        current: 0,
        previous: 0
    }
};

const sentimentData = {
    positive: 0,
    neutral: 0,
    negative: 0
}

// Speech Recognition Variables
let recognition = null;
let isRecognizing = false;
let isPaused = false;
let finalTranscript = '';
let interimTranscript = '';
let participantName = '';
let participantId = '';
let talkTimeStarted = null;
let totalTalkTime = 0;
let talkTimeInterval = null;
let meetingStarted = false;

// Initialize the dashboard when document is ready
$(document).ready(function() {
    // Check if Speech Recognition is available
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        $('.speech-controls').html('<div class="alert alert-danger">Speech Recognition is not supported in your browser. Please use Chrome, Edge, or Safari.</div>');
    } else {
        setupSpeechRecognition();
    }
    
    // Handle meeting ID form submission
    $('#load-meeting-btn').click(function() {
        loadMeetingData();
    });
    
    $('#meeting-id-input').keypress(function(e) {
        if (e.which === 13) {
            loadMeetingData();
        }
    });
    
    // Speech Recognition Controls
    $('#start-recognition-btn').click(startRecognition);
    $('#pause-recognition-btn').click(pauseRecognition);
    $('#stop-recognition-btn').click(stopRecognition);
    
    // Generate a random browser ID if not set
    if (!localStorage.getItem('browser_id')) {
        localStorage.setItem('browser_id', 'browser_' + Math.random().toString(36).substring(2, 10));
    }
    
    // Handle participant selection
    $('#participant-select').change(function() {
        const selectedValue = $(this).val();
        if (selectedValue) {
            const [id, name] = selectedValue.split('|');
            participantId = id;
            participantName = name;
            console.log(`Selected participant: ${participantName} (${participantId})`);
            resetTalkTime();
        } else {
            participantId = '';
            participantName = '';
        }
    });
    
    // Listen for new transcriptions
    socket.on('new_transcription', function(data) {
        // Only process if this is for the current meeting
        if (currentMeetingId === '' || data.meeting_id === currentMeetingId) {
            addTranscription(data);
            updateSentimentMetrics(data.sentiment_score);
            calculateOverallMetrics();
        }
    });

    // Listen for participant data updates
    socket.on('participant_joined', function(data) {
        if (currentMeetingId === data.meeting_id) {
            console.log('Participant joined:', data);
            fetchParticipants();
        }
    });

    socket.on('participant_left', function(data) {
        if (currentMeetingId === data.meeting_id) {
            console.log('Participant left:', data);
            fetchParticipants();
        }
    });

    socket.on('meeting_started', function(data) {
        if (currentMeetingId === data.meeting_id) {
            $('#meeting-status').html(`<div class="alert alert-success">Meeting ${data.topic} (ID: ${data.meeting_id}) is active</div>`);
            meetingStarted = true;
            fetchParticipants();
        }
    });

    socket.on('meeting_ended', function() {
        meetingStarted = false;
    });
    
    // Listen for talk time updates
    socket.on('talk_time_updated', function(data) {
        if (currentMeetingId === data.meeting_id) {
            console.log('Talk time updated:', data);
            updateParticipantsList();
            calculateEngagementMetrics();
            calculateOverallMetrics();
        }
    });

    // Set update interval for metrics, engagement data, and talk time

    setInterval(function() {
        if (currentMeetingId) {
            calculateOverallMetrics();
        }
    }, 5000); // Update every 5 seconds

    setInterval(saveEngagementSnapshot, 5000);

    setInterval(periodicTalkTimeUpdate, 1000); // Update every second
});

// redirects to the transcripts page
function viewTranscripts() {
    window.location.href = `/transcript-list`;
}

function setupSpeechRecognition() {
    // Initialize speech recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.lang = 'en-US'; // Default language - could make this configurable
    
    recognition.onstart = function() {
        isRecognizing = true;
        updateRecognitionStatus('on');
        $('#start-recognition-btn').prop('disabled', true);
        $('#pause-recognition-btn').prop('disabled', false);
        $('#stop-recognition-btn').prop('disabled', false);
        
        // Start tracking talk time
        talkTimeStarted = new Date();
        talkTimeInterval = setInterval(updateTalkTime, 1000);
    };
    
    recognition.onend = function() {
        if (!isPaused) {
            isRecognizing = false;
            updateRecognitionStatus('off');
            $('#start-recognition-btn').prop('disabled', false);
            $('#pause-recognition-btn').prop('disabled', true);
            $('#stop-recognition-btn').prop('disabled', true);
            
            // Stop tracking talk time
            clearInterval(talkTimeInterval);
            talkTimeInterval = null;
        }
    };
    
    recognition.onresult = function(event) {
        interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
                finalTranscript += event.results[i][0].transcript + ' ';
            } else {
                interimTranscript += event.results[i][0].transcript;
            }
        }
        
        // Display interim results
        $('#interim-transcript').html(interimTranscript);
        
        // Display final results
        $('#final-transcript').html(finalTranscript);
        
        // Send final results to server when appropriate
        if (finalTranscript.trim() !== '' && !event.results[event.resultIndex].isFinal && event.resultIndex > 0) {
            sendTranscriptionToServer(finalTranscript);
            finalTranscript = '';
            $('#final-transcript').html('');
        }
    };
    
    recognition.onerror = function(event) {
        console.error('Speech recognition error:', event.error);
        alert(`Speech recognition error: ${event.error}`);
        stopRecognition();
    };
}

function startRecognition() {
    const selectedParticipant = $('#participant-select').val();
    
    if (!selectedParticipant) {
        alert('Please select your identity from the participants dropdown.');
        return;
    }
    
    if (!currentMeetingId) {
        alert('Please enter a meeting ID before starting recognition.');
        $('#meeting-id-input').focus();
        return;
    }

    if (!meetingStarted) {
        alert('Meeting has not started yet. Please wait for the host to start the meeting.');
        return;
    }
    
    // Reset transcripts
    finalTranscript = '';
    interimTranscript = '';
    $('#interim-transcript').html('');
    $('#final-transcript').html('');
    
    // Start recognition
    try {
        recognition.start();
        console.log('Recognition started');
        
        // Notify server that this participant is active
        $.ajax({
            url: '/api/participant/active',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                meeting_id: currentMeetingId,
                participant_id: participantId,
                is_active: true,
                browser_id: localStorage.getItem('browser_id')
            }),
            success: function(response) {
                console.log('Participant marked active:', response);
            },
            error: function(xhr, status, error) {
                console.error('Error marking participant active:', error);
            }
        });
    } catch (e) {
        console.error('Recognition failed to start:', e);
    }
}

function pauseRecognition() {
    if (isRecognizing) {
        isPaused = true;
        recognition.stop();
        updateRecognitionStatus('pause');
        $('#pause-recognition-btn').prop('disabled', true);
        $('#start-recognition-btn').prop('disabled', false);
        $('#stop-recognition-btn').prop('disabled', false);
        
        // Pause talk time tracking
        clearInterval(talkTimeInterval);
    }
}

function stopRecognition() {
    isPaused = false;
    isRecognizing = false;
    
    // Stop tracking talk time
    clearInterval(talkTimeInterval);
    talkTimeInterval = null;
    
    // Send any remaining transcript
    if (finalTranscript.trim() !== '') {
        sendTranscriptionToServer(finalTranscript);
        finalTranscript = '';
    }
    
    // Update UI
    updateRecognitionStatus('off');
    $('#interim-transcript').html('');
    $('#final-transcript').html('');
    $('#start-recognition-btn').prop('disabled', false);
    $('#pause-recognition-btn').prop('disabled', true);
    $('#stop-recognition-btn').prop('disabled', true);
    
    // Stop recognition
    try {
        recognition.stop();
        console.log('Recognition stopped');
    } catch (e) {
        console.error('Recognition failed to stop:', e);
    }
    
    // Send final talk time to server
    sendTalkTimeToServer();
    
    // Notify server that this participant is no longer active
    $.ajax({
        url: '/api/participant/active',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            meeting_id: currentMeetingId,
            participant_id: participantId,
            is_active: false,
            browser_id: localStorage.getItem('browser_id')
        }),
        success: function(response) {
            console.log('Participant marked inactive:', response);
        },
        error: function(xhr, status, error) {
            console.error('Error marking participant inactive:', error);
        }
    });
}

function updateRecognitionStatus(status) {
    const statusElement = $('#recognition-status');
    const indicator = statusElement.find('.status-indicator');
    
    // Remove all status classes
    indicator.removeClass('status-on status-off status-pause');
    
    // Add appropriate class and update text
    if (status === 'on') {
        indicator.addClass('status-on');
        statusElement.html(`<span class="status-indicator status-on"></span> Active for ${participantName}`);
    } else if (status === 'pause') {
        indicator.addClass('status-pause');
        statusElement.html(`<span class="status-indicator status-pause"></span> Paused`);
    } else {
        indicator.addClass('status-off');
        statusElement.html(`<span class="status-indicator status-off"></span> Inactive`);
    }
}

// In sendTranscriptionToServer function
function sendTranscriptionToServer(transcript) {
    if (!transcript || !transcript.trim()) return;
    
    $.ajax({
        url: '/api/transcription',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            meeting_id: currentMeetingId,
            participant_id: participantId,
            participant_name: participantName,
            transcript: transcript.trim(),
            timestamp: new Date().toISOString(),
            browser_id: localStorage.getItem('browser_id')
        }),
        success: function(response) {
            console.log('Transcription sent successfully:', response);
            // Track this activity for engagement metrics
            trackParticipantActivity(participantId, 'transcription');
        },
        error: function(xhr, status, error) {
            console.error('Error sending transcription:', error);
        }
    });
}

function updateTalkTime() {
    if (talkTimeStarted) {
        const now = new Date();
        const currentSessionTime = Math.floor((now - talkTimeStarted) / 1000);
        const talkTimeSec = currentSessionTime + totalTalkTime;
        
        // Add this line to update UI with current talk time
        $('#current-talk-time').text(formatTime(talkTimeSec));
        
        console.log(`Talk time: ${formatTime(talkTimeSec)}`);
    }
}

function sendTalkTimeToServer() {
    if (talkTimeStarted) {
        const now = new Date();
        const currentSessionTime = Math.floor((now - talkTimeStarted) / 1000);
        totalTalkTime += currentSessionTime;
        talkTimeStarted = null;
        
        console.log(`Sending total talk time: ${totalTalkTime}s`);
        
        $.ajax({
            url: '/api/talk-time',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                meeting_id: currentMeetingId,
                participant_id: participantId,
                talk_time: totalTalkTime,
                browser_id: localStorage.getItem('browser_id')
            }),
            success: function(response) {
                console.log('Talk time sent successfully:', response);
                updateParticipantsList();
            },
            error: function(xhr, status, error) {
                console.error('Error sending talk time:', error);
            }
        });
    }
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' + secs : secs}`;
}

// Add this function to periodically update talk time on the server
function periodicTalkTimeUpdate() {
    if (talkTimeStarted && isRecognizing && !isPaused) {
        const now = new Date();
        const currentSessionTime = Math.floor((now - talkTimeStarted) / 1000);
        const currentTotalTime = totalTalkTime + currentSessionTime;
        
        $.ajax({
            url: '/api/talk-time',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                meeting_id: currentMeetingId,
                participant_id: participantId,
                talk_time: currentTotalTime,
                is_interim: true,  // Flag to indicate this is an interim update
                browser_id: localStorage.getItem('browser_id')
            }),
            success: function(response) {
                console.log('Interim talk time sent successfully:', response);
            },
            error: function(xhr, status, error) {
                console.error('Error sending interim talk time:', error);
            }
        });
    }
}

function resetTalkTime() {
    totalTalkTime = 0;
    talkTimeStarted = null;
    if (talkTimeInterval) {
        clearInterval(talkTimeInterval);
        talkTimeInterval = null;
    }
    $('#current-talk-time').text('0:00');
}

function loadMeetingData() {
    const meetingId = $('#meeting-id-input').val().trim();
    
    if (!meetingId) {
        alert('Please enter a meeting ID');
        return;
    }
    
    currentMeetingId = meetingId.replace(/\s+/g, '');
    console.log(`Loading data for meeting ID: ${meetingId}`);
    
    // Check if meeting exists and get status
    $.ajax({
        url: `/api/meetings/${meetingId}`,  // no type specification needed - default "info"
        type: 'GET',
        success: function(response) {
            console.log('Meeting data loaded:', response);
            
            if (response.success) {
                const meetingStatus = response.data.status;
                if (meetingStatus === 'active') {
                    $('#meeting-status').html(`<div class="alert alert-success">Meeting is active</div>`);
                } else if (meetingStatus === 'ended') {
                    $('#meeting-status').html(`<div class="alert alert-warning">Meeting has ended</div>`);
                } else {
                    $('#meeting-status').html(`<div class="alert alert-info">Meeting status: ${meetingStatus}</div>`);
                }
                
                // Fetch participants
                fetchParticipants();
                
                // Get transcriptions
                fetchTranscriptions();
                
                // Reset engagement metrics
                resetMetrics();
            } else {
                $('#meeting-status').html(`<div class="alert alert-danger">Error: ${response.message}</div>`);
            }
        },
        error: function(xhr, status, error) {
            console.error('Error loading meeting data:', error);
            $('#meeting-status').html(`<div class="alert alert-danger">Meeting not found or server error</div>`);
        }
    });
}

function fetchParticipants() {
    if (!meetingStarted) return;
    
    $.ajax({
        url: `/api/meetings/${currentMeetingId}?type=participants`,
        type: 'GET',
        success: function(response) {
            console.log('Participants data loaded:', response);
            
            if (response.success) {
                meetingParticipants = response.data;
                
                // Debug: Check what data we actually received
                console.log('Participant data details:');
                meetingParticipants.forEach(p => {
                    console.log(`${p.name}: talk_time=${p.talk_time}, total_meeting_time=${totalTalkTime}`);
                });
                
                populateParticipantsDropdown(response.data);
                displayParticipantsGrid(response.data);
                displayParticipantsTable(response.data);
                calculateEngagementMetrics();
            } else {
                console.error('Error in participants response:', response.message);
            }
        },
        error: function(xhr, status, error) {
            console.error('Error loading participants data:', error);
        }
    });
}

function populateParticipantsDropdown(participants) {
    const select = $('#participant-select');
    
    // Clear existing options except the placeholder
    select.find('option:not(:first)').remove();
    
    // Sort participants by name
    participants.sort((a, b) => a.name.localeCompare(b.name));
    
    // Add participants to dropdown
    participants.forEach(participant => {
        select.append(`<option value="${participant.id}|${participant.name}">${participant.name}</option>`);
    });
    
    // If we previously selected a participant who is still in the meeting, select them again
    if (participantId) {
        const participantExists = participants.some(p => p.id === participantId);
        if (participantExists) {
            select.val(`${participantId}|${participantName}`);
        } else {
            participantId = '';
            participantName = '';
        }
    }
}

function displayParticipantsGrid(participants) {
    const grid = $('#participants-video-grid');
    
    if (!participants || participants.length === 0) {
        grid.html(`<div class="text-center text-muted py-4">
            <p>No participants in this meeting</p>
        </div>`);
        return;
    }
    
    // Clear existing grid
    grid.empty();
    
    // Add participants to grid
    participants.forEach(participant => {
        // Calculate talk time percentage of total meeting time if available
        let talkTimePercentage = 0;
        if (totalTalkTime > 0) {
            talkTimePercentage = Math.round((participant.talk_time / totalTalkTime) * 100);
        }
        
        // Add active indicator if participant is currently speaking
        const activeClass = participant.is_active ? 'video-active' : '';
        
        grid.append(`
            <div class="video-container ${activeClass}">
                <div class="video-overlay">${participant.name}</div>
                <div class="engagement-indicator">${talkTimePercentage}% Talk Time</div>
                <!-- Placeholder for video -->
                <div class="d-flex align-items-center justify-content-center h-100">
                    <i class="fas fa-user-circle fa-3x text-secondary"></i>
                </div>
            </div>
        `);
    });
}

function displayParticipantsTable(participants) {
    const tableBody = $('#participants-table tbody');
    
    // Clear existing rows
    tableBody.empty();
    
    if (!participants || participants.length === 0) {
        tableBody.html(`<tr><td colspan="3" class="text-center">No participants</td></tr>`);
        return;
    }

    // Calculate engagement scores based on talk time distribution and active status
    calculateParticipantEngagementScores(participants);
    
    // Sort participants by engagement score (descending)
    participants.sort((a, b) => (b.engagement_score || 0) - (a.engagement_score || 0));
    
    // Add participants to table
    participants.forEach(participant => {
        // Calculate talk time percentage
        let talkTimePercentage = 0;
        if (totalTalkTime > 0) {
            talkTimePercentage = Math.round((participant.talk_time / totalTalkTime) * 100);
        }
        
        const engagementScore = Math.round(participant.engagement_score) || '-';
        
        tableBody.append(`
            <tr>
                <td class="text-secondary">${participant.name}</td>
                <td>${engagementScore}</td>
                <td>${talkTimePercentage}%</td>
            </tr>
        `);
    });
}

function fetchTranscriptions() {
    if (!meetingStarted) return;
    
    $.ajax({
        url: `/api/meetings/${currentMeetingId}?type=transcriptions`,
        type: 'GET',
        success: function(response) {
            console.log('Transcriptions loaded:', response);
            if (response.success) {
                displayTranscriptions(response.data);
                calculateSentimentFromTranscriptions(response.data);
            } else {
                console.error('Error in transcriptions response:', response.message);
            }
        },
        error: function(xhr, status, error) {
            console.error('Error loading transcriptions:', error);
        }
    });
}

function fetchTalkTime(participantId, callback) {
    if (!meetingStarted) return;

    $.ajax({
        url: `/api/meetings/${currentMeetingId}?type=participants`,
        type: 'GET',
        success: function(response) {
            console.log('participants loaded:', response);
            if (response.success) {
                // Find the participant and pass their talk_time to the callback
                const participant = response.data.find(p => p.id === participantId);
                if (participant) {
                    console.log(participant.talk_time); // Call the callback with the talk time
                    return participant.talk_time;
                } else {
                    console.error('Participant not found');
                }
            } else {
                console.error('Error in participants response:', response.message);
            }
        },
        error: function(xhr, status, error) {
            console.error('Error loading participants:', error);
        }
    });
}

function calculateParticipantEngagementScores(participants) {
    // Calculate total talk time across all participants
    // const totalTalkTime = participants.reduce((sum, p) => sum + (p.talk_time || 0), 0);
    // const totalMeetingTime = Math.max(...participants.map(p => p.total_meeting_time || 0));
    
    participants.forEach(participant => {
        let talkTimeScore = fetchTalkTime(participant.id);
        
        // Talk time portion score (0-60 points)
        if (totalTalkTime > 0) {
            const expectedShare = 1 / participants.length;
            const actualShare = (participant.talk_time || 0) / totalTalkTime;
            
            // Score higher if close to expected share (neither too quiet nor dominating)
            const deviation = Math.abs(actualShare - expectedShare);
            talkTimeScore = 60 * Math.max(0, 1 - (deviation / expectedShare) * 1.5);
        }
        
        // Active status bonus (0-20 points)
        const activeBonus = participant.is_active ? 20 : 0;
        
        // Participation consistency score (0-20 points)
        let consistencyScore = 0;
        if (participant.recent_activity && participant.recent_activity.length > 0) {
            // Calculate time between contributions
            consistencyScore = 20; // Add logic to reduce score for long gaps
        }
        
        // Calculate final score (0-100)
        participant.engagement_score = Math.min(100, talkTimeScore + activeBonus + consistencyScore);
    });
}


function trackParticipantActivity(participantId, activityType) {
    // Find participant in array
    const participant = meetingParticipants.find(p => p.id === participantId);
    if (!participant) return;
    
    // Initialize recent activity array if not exists
    if (!participant.recent_activity) {
        participant.recent_activity = [];
    }
    
    // Add activity timestamp
    participant.recent_activity.push({
        type: activityType, // 'talk', 'transcription', etc.
        timestamp: new Date()
    });
    
    // Keep only last 10 activities for performance
    if (participant.recent_activity.length > 10) {
        participant.recent_activity.shift();
    }
    
    // Recalculate engagement after activity update
    calculateParticipantEngagementScores(meetingParticipants);
    calculateEngagementMetrics();
}

function calculateEngagementMetrics() {
    if (!meetingParticipants || meetingParticipants.length === 0) return;
    
    // Calculate total engagement score across all participants
    let totalEngagement = 0;
    let participantCount = 0;
    
    meetingParticipants.forEach(participant => {
        if (participant.engagement_score) {
            totalEngagement += participant.engagement_score;
            participantCount++;
        }
    });
    
    // Calculate average engagement score
    const averageEngagement = participantCount > 0 ? Math.round(totalEngagement / participantCount) : 0;
    
    // Store timestamp with this data point for time series
    const timestamp = new Date();
    
    // Update engagement metrics
    metricsData.engagement.previous = metricsData.engagement.current;
    metricsData.engagement.current = averageEngagement;
    metricsData.engagement.values.push({
        value: averageEngagement,
        timestamp: timestamp
    });
    
    // Limit history to last 10 minutes of data
    const cutoffTime = new Date(timestamp.getTime() - 10 * 60 * 1000);
    metricsData.engagement.values = metricsData.engagement.values.filter(
        item => item.timestamp >= cutoffTime
    );
    
    // Update UI
    $('#engagement-score').text(averageEngagement);
    
    // Update trend indicator
    const engagementDiff = metricsData.engagement.current - metricsData.engagement.previous;
    if (Math.abs(engagementDiff) < 5) {
        $('#engagement-trend').html('<i class="fas fa-arrow-right text-warning"></i>');
    } else if (engagementDiff >= 5) {
        $('#engagement-trend').html('<i class="fas fa-arrow-up text-success"></i>');
    } else {
        $('#engagement-trend').html('<i class="fas fa-arrow-down text-danger"></i>');
    }
}

function saveEngagementSnapshot() {
    if (!meetingStarted) return;
    
    const snapshot = {
        meeting_id: currentMeetingId,
        timestamp: new Date().toISOString(),
        overall_engagement: metricsData.engagement.current,
        overall_sentiment: metricsData.sentiment.current,
        meeting_score: metricsData.meetingScore.current,
        participants: meetingParticipants.map(p => ({
            id: p.id,
            name: p.name,
            engagement_score: p.engagement_score || 0,
            talk_time: p.talk_time || 0,
            is_active: p.is_active || false
        }))
    };
    
    $.ajax({
        url: '/api/engagement-snapshot',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(snapshot),
        success: function(response) {
            console.log('Engagement snapshot saved:', response);
        },
        error: function(xhr, status, error) {
            console.error('Error saving engagement snapshot:', error);
        }
    });
}

function calculateSentimentFromTranscriptions(transcriptions) {
    if (!transcriptions || transcriptions.length === 0) return;
    
    // Reset sentiment data
    metricsData.sentiment.positive = 0;
    metricsData.sentiment.neutral = 0;
    metricsData.sentiment.negative = 0;
    
    // Calculate sentiment distribution
    transcriptions.forEach(transcription => {
        if (transcription.sentiment_score > 0.1) {
            metricsData.sentiment.positive++;
        } else if (transcription.sentiment_score < -0.1) {
            metricsData.sentiment.negative++;
        } else {
            metricsData.sentiment.neutral++;
        }
    });
    
    // Calculate overall sentiment score (-100 to 100)
    const total = metricsData.sentiment.positive + metricsData.sentiment.neutral + metricsData.sentiment.negative;
    if (total > 0) {
        // Weight: positive +1, neutral 0, negative -1
        const weightedSum = metricsData.sentiment.positive - metricsData.sentiment.negative;
        const sentimentScore = Math.round((weightedSum / total) * 100);
        
        // Update sentiment metrics
        metricsData.sentiment.previous = metricsData.sentiment.current;
        metricsData.sentiment.current = sentimentScore;
        metricsData.sentiment.values.push(sentimentScore);
        
        // Limit history to last 10 values
        if (metricsData.sentiment.values.length > 10) {
            metricsData.sentiment.values.shift();
        }
    }
    
    // Update sentiment chart
    updateSentimentUI();
}

function updateSentimentMetrics(score) {
    // Add sentiment to appropriate category
    if (score > 0.1) {
        metricsData.sentiment.positive++;
    } else if (score < -0.1) {
        metricsData.sentiment.negative++;
    } else {
        metricsData.sentiment.neutral++;
    }
    
    // Calculate overall sentiment score (-100 to 100)
    const total = metricsData.sentiment.positive + metricsData.sentiment.neutral + metricsData.sentiment.negative;
    if (total > 0) {
        // Weight: positive +1, neutral 0, negative -1
        const weightedSum = metricsData.sentiment.positive - metricsData.sentiment.negative;
        const sentimentScore = Math.round((weightedSum / total) * 100);
        
        // Update sentiment metrics
        metricsData.sentiment.previous = metricsData.sentiment.current;
        metricsData.sentiment.current = sentimentScore;
        metricsData.sentiment.values.push(sentimentScore);
        
        // Limit history to last 10 values
        if (metricsData.sentiment.values.length > 10) {
            metricsData.sentiment.values.shift();
        }
    }
    
    // Update sentiment UI
    updateSentimentUI();
}

function updateSentimentUI() {
    // Update sentiment score display
    $('#sentiment-score').text(metricsData.sentiment.current);
    
    // Update trend indicator
    const sentimentDiff = metricsData.sentiment.current - metricsData.sentiment.previous;
    if (Math.abs(sentimentDiff) < 10) {
        $('#sentiment-trend').html('<i class="fas fa-arrow-right text-warning"></i>');
    } else if (sentimentDiff >= 10) {
        $('#sentiment-trend').html('<i class="fas fa-arrow-up text-success"></i>');
    } else {
        $('#sentiment-trend').html('<i class="fas fa-arrow-down text-danger"></i>');
    }
}

function calculateOverallMetrics() {
    // Calculate meeting score (50% engagement + 50% sentiment)
    const engagementContribution = (metricsData.engagement.current / 100) * 50;
    const sentimentContribution = ((metricsData.sentiment.current + 100) / 200) * 50; // Convert -100..100 to 0..100 then scale to 0..50
    
    const meetingScore = Math.round(engagementContribution + sentimentContribution);
    
    // Update meeting score metrics
    metricsData.meetingScore.previous = metricsData.meetingScore.current;
    metricsData.meetingScore.current = meetingScore;
    
    // Update UI
    $('#meeting-score').text(meetingScore);
    
    // Update trend indicator
    const scoreDiff = metricsData.meetingScore.current - metricsData.meetingScore.previous;
    if (Math.abs(scoreDiff) < 5) {
        $('#meeting-score-trend').html('<i class="fas fa-arrow-right text-warning"></i>');
    } else if (scoreDiff >= 5) {
        $('#meeting-score-trend').html('<i class="fas fa-arrow-up text-success"></i>');
    } else {
        $('#meeting-score-trend').html('<i class="fas fa-arrow-down text-danger"></i>');
    }
}

function resetMetrics() {
    // Reset all metrics to initial state
    metricsData.sentiment = {
        current: 0,
        previous: 0,
        values: [],
        positive: 0,
        neutral: 0,
        negative: 0
    };
    
    metricsData.engagement = {
        current: 0,
        previous: 0,
        values: []
    };
    
    metricsData.meetingScore = {
        current: 0,
        previous: 0
    };
    
    // Reset UI
    $('#meeting-score').text('0');
    $('#meeting-score-trend').html('<i class="fas fa-arrow-right"></i>');
    $('#engagement-score').text('0');
    $('#engagement-trend').html('<i class="fas fa-arrow-right"></i>');
    $('#sentiment-score').text('0');
    $('#sentiment-trend').html('<i class="fas fa-arrow-right"></i>');
} 

function displayTranscriptions(transcriptions) {
    const container = $('#transcription-container');
    
    if (!transcriptions || transcriptions.length === 0) {
        container.html(`<div class="text-center text-muted">
            <p>No transcriptions available. Start a meeting and enable live transcriptions.</p>
        </div>`);
        return;
    }
    
    // Hide the "no transcripts" message
    $('#no-transcripts-message').hide();
    
    // Clear container if loading for the first time
    if (container.find('.transcription-item').length === 0) {
        container.empty();
    }
    
    // Sort by timestamp (newest first for display purposes)
    transcriptions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // Add each transcription
    transcriptions.forEach(transcription => {
        addTranscription(transcription);
    });
}

function addTranscription(transcription) {
    const container = $('#transcription-container');
    
    // Hide the "no transcripts" message
    $('#no-transcripts-message').hide();
    
    // Format timestamp
    const timestamp = moment(transcription.timestamp).format('HH:mm:ss');
    
    // Determine sentiment class
    let sentimentClass = 'neutral';
    let sentimentIcon = 'meh';
    
    if (transcription.sentiment_score > 0.1) {
        sentimentClass = 'positive';
        sentimentIcon = 'smile';
    } else if (transcription.sentiment_score < -0.1) {
        sentimentClass = 'negative';
        sentimentIcon = 'frown';
    }
    
    // Check if this transcription already exists
    const existingItem = container.find(`.transcription-item[data-id="${transcription.id}"]`);
    if (existingItem.length > 0) {
        return; // Skip if already added
    }
    
    // Create the transcription item
    const transcriptionItem = $(`
        <div class="transcription-item sentiment-${sentimentClass}" data-id="${transcription.id}">
            <div class="transcription-header">
                <span class="transcription-participant">${transcription.participant_name}</span>
                <span class="transcription-time">${timestamp}</span>
                <span class="transcription-sentiment">
                    <i class="fas fa-${sentimentIcon}"></i>
                </span>
            </div>
            <div class="transcription-content">${transcription.transcript}</div>
        </div>
    `);
    
    // Add to the beginning of the container
    container.prepend(transcriptionItem);
    
    // Limit to latest 100 transcriptions for performance
    const items = container.find('.transcription-item');
    if (items.length > 100) {
        items.slice(100).remove();
    }
}

function updateParticipantsList() {
    // Update the participants table and video grid
    fetchParticipants();
}
