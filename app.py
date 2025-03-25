from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from flask_cors import CORS

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Environment variables
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
WEBSHARE_USERNAME = os.getenv('WEBSHARE_USERNAME', 'otntczny')
WEBSHARE_PASSWORD = os.getenv('WEBSHARE_PASSWORD', '1w8maa9o5q5r')
PORT = int(os.getenv('PORT', 8000))

def get_youtube_client():
    if not YOUTUBE_API_KEY:
        raise ValueError("YouTube API key is not configured")
    return build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

@app.route('/')
def home():
    return jsonify({
        'message': 'ClipSmart API is running',
        'status': True
    })

@app.route('/transcript/<video_id>')
def get_transcript(video_id):
    try:
        # Input validation
        if not video_id:
            return jsonify({
                'message': "Video ID is required",
                'status': False
            }), 400

        if not YOUTUBE_API_KEY:
            return jsonify({
                'message': "Server configuration error: YouTube API key is missing",
                'status': False
            }), 500

        # Check if video exists
        try:
            youtube = get_youtube_client()
            video_response = youtube.videos().list(
                part='snippet',
                id=video_id
            ).execute()

            if not video_response.get('items'):
                return jsonify({
                    'message': "Video not found or is not accessible",
                    'status': False
                }), 404

        except HttpError as e:
            return jsonify({
                'message': "Error accessing YouTube API",
                'error': str(e),
                'status': False
            }), 500

        # Fetch transcript
        transcript_list = None
        transcript_error = None

        try:
            ytt_api = YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=WEBSHARE_USERNAME,
                    proxy_password=WEBSHARE_PASSWORD,
                )
            )
            transcript_list = ytt_api.fetch(
                video_id,
                languages=['en']
            )
        except Exception as e:
            transcript_error = str(e)

            try:
                ytt_api = YouTubeTranscriptApi(
                    proxy_config=WebshareProxyConfig(
                        proxy_username=WEBSHARE_USERNAME,
                        proxy_password=WEBSHARE_PASSWORD,
                    )
                )
                transcript_list = ytt_api.fetch(
                    video_id,
                    languages=['en']
                )
            except Exception as fallback_err:
                return jsonify({
                    'message': "No transcript available for this video. The video might not have captions enabled.",
                    'originalError': transcript_error,
                    'fallbackError': str(fallback_err),
                    'status': False
                }), 404

        if not transcript_list:
            return jsonify({
                'message': "No transcript segments found for this video. The video might not have captions.",
                'status': False
            }), 404

        # Process transcript into desired format
        processed_transcript = []
        for index, item in enumerate(transcript_list):
            try:
                # Access attributes directly from the FetchedTranscriptSnippet object
                text = getattr(item, 'text', None)
                start = getattr(item, 'start', None)
                duration = getattr(item, 'duration', None)

                if text is not None and start is not None and duration is not None:
                    segment = {
                        'id': index + 1,
                        'text': text.strip(),
                        'startTime': float(start),
                        'endTime': float(start + duration),
                        'duration': float(duration)
                    }
                    if segment['text']:
                        processed_transcript.append(segment)
            except Exception:
                continue

        if not processed_transcript:
            return jsonify({
                'message': "Failed to process transcript segments. The transcript may be malformed.",
                'status': False
            }), 404

        return jsonify({
            'message': "Transcript fetched successfully",
            'data': processed_transcript,
            'status': True,
            'totalSegments': len(processed_transcript),
            'metadata': {
                'videoId': video_id,
                'language': 'en',
                'isAutoGenerated': True
            }
        }), 200

    except Exception as error:
        return jsonify({
            'message': "Failed to fetch transcript",
            'error': str(error),
            'status': False
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
