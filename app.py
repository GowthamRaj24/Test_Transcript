from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

app = Flask(__name__)

def get_youtube_client():
    return build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))

def get_proxied_transcript_api():
    """Get a YouTubeTranscriptApi instance configured with proxy settings from .env"""
    # Parse the proxy string in format "IP:Port:Username:Password"
    proxy_string = "23.106.53.93:80:otntczny-1:1w8maa9o5q5r"
    parts = proxy_string.split(":")
    
    if len(parts) >= 4:
        proxy_host = parts[0]
        proxy_port = parts[1]
        username = urllib.parse.quote(parts[2])
        password = urllib.parse.quote(parts[3])
    else:
        proxy_host = "23.106.53.93"
        proxy_port = "80"
        username = urllib.parse.quote(os.getenv('PROXY_USERNAME', ''))
        password = urllib.parse.quote(os.getenv('PROXY_PASSWORD', ''))
    
    auth_part = f"{username}:{password}@" if username and password else ""

    proxy_url = f"http://{auth_part}{proxy_host}:{proxy_port}"
    https_url = f"https://{auth_part}{proxy_host}:{proxy_port}"

    print(f"Configuring proxy: {proxy_host}:{proxy_port} with auth")
    return YouTubeTranscriptApi(
        proxy_config=GenericProxyConfig(
            http_url=proxy_url,
            https_url=https_url
        )
    )

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
            print('Request failed: No video ID provided')
            return jsonify({
                'message': "Video ID is required",
                'status': False
            }), 400

        if not os.getenv('YOUTUBE_API_KEY'):
            print('YouTube API key is not configured')
            return jsonify({
                'message': "Server configuration error: YouTube API key is missing",
                'status': False
            }), 500

        # Check if video exists
        try:
            print(f'Checking if video {video_id} exists...')
            youtube = get_youtube_client()
            video_response = youtube.videos().list(
                part='snippet',
                id=video_id
            ).execute()

            if not video_response.get('items'):
                print(f'Video with ID {video_id} not found or is not accessible')
                return jsonify({
                    'message': "Video not found or is not accessible",
                    'status': False
                }), 404

            print(f'Video found: {video_response["items"][0]["snippet"]["title"]}')
        except HttpError as e:
            print("Error checking video existence:", str(e))

        # Fetch transcript with proxy
        print(f'Attempting to fetch transcript for video {video_id} using proxy...')
        transcript_list = None
        transcript_error = None
        
        # Get proxied transcript API instance
        proxied_api = get_proxied_transcript_api()

        try:
            print('Trying to fetch English transcript...')
            transcript_list = proxied_api.get_transcript(
                video_id, 
                languages=['en']
            )
            print('Successfully fetched English transcript')
        except Exception as e:
            transcript_error = str(e)
            print('Failed to fetch English transcript:', transcript_error)

            try:
                print('Trying to fetch transcript in any language...')
                transcript_list = proxied_api.get_transcript(video_id)
                print('Successfully fetched transcript in non-English language')
            except Exception as fallback_err:
                print('Failed to fetch transcript in any language:', str(fallback_err))
                return jsonify({
                    'message': "No transcript available for this video. The video might not have captions enabled.",
                    'originalError': transcript_error,
                    'fallbackError': str(fallback_err),
                    'status': False
                }), 404

        if not transcript_list:
            print('No transcript segments found')
            return jsonify({
                'message': "No transcript segments found for this video. The video might not have captions.",
                'status': False
            }), 404

        print(f'Fetched {len(transcript_list)} transcript segments')

        # Process transcript into desired format
        processed_transcript = []
        for index, item in enumerate(transcript_list):
            try:
                if not all(key in item for key in ['text', 'start', 'duration']):
                    print(f'Warning: Invalid segment at index {index}:', item)
                    continue

                segment = {
                    'id': index + 1,
                    'text': item['text'].strip(),
                    'startTime': float(item['start']),
                    'endTime': float(item['start'] + item['duration']),
                    'duration': float(item['duration'])
                }
                if segment['text']:
                    processed_transcript.append(segment)
            except Exception as err:
                print(f'Error processing segment {index}:', str(err))

        if not processed_transcript:
            return jsonify({
                'message': "Failed to process transcript segments. The transcript may be malformed.",
                'status': False
            }), 404

        print(f'Successfully processed {len(processed_transcript)} transcript segments')

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
        print("Detailed transcript fetch error:", {
            'message': str(error),
            'videoId': video_id
        })
        return jsonify({
            'message': "Failed to fetch transcript",
            'error': str(error),
            'status': False
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5001))  
    host = os.getenv('FLASK_HOST', '127.0.0.1')  
    print(f"Starting server on {host}:{port}")
    app.run(debug=True, host=host, port=port, use_reloader=False)  # Disable auto-reloader to avoid watchdog errors
