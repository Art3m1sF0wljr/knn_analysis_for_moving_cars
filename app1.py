import os
import sys
import datetime
import subprocess
import glob
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
import logging

# Configuration
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
SCOPES = [YOUTUBE_UPLOAD_SCOPE]
TOKEN_FILE = f"{os.path.splitext(os.path.basename(sys.argv[0]))[0]}-oauth2.json"
CHANNEL_ID = ""  # Replace with your channel ID
MOTION_CLIPS_FOLDER = "motion_clips"
OUTPUT_FOLDER = "output"
BLACK_FRAME_DURATION = 30  # frames at 30fps = 0.5 seconds
TEXT_FILE = "video_titles.txt"
DESCRIPTION_FILE = "description.txt"
logger = logging.getLogger(__name__)

def get_authenticated_service():
    """Authenticate and return the YouTube service, caching credentials"""
    creds = None

    # Load existing credentials if available
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            os.remove(TOKEN_FILE)
            creds = None

    # If credentials are invalid or expired, refresh them
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                logger.error(f"Failed to refresh token: {e}")
                os.remove(TOKEN_FILE)  # Remove invalid token
                return get_authenticated_service()  # Retry with new auth flow
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE,
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save the credentials for next time
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=creds)


def create_black_clip(duration, output_path):
    """Create a short black video clip"""
    cmd = [
        'ffmpeg',
        '-f', 'lavfi',
        '-i', 'color=c=black:s=1920x1080:r=30',  # Adjust resolution as needed
        '-t', str(duration/30.0),  # Convert frames to seconds
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '18',
        output_path
    ]
    subprocess.run(cmd, check=True)

def get_video_title(filename):
    """Extract title from filename (without extension)"""
    return os.path.splitext(os.path.basename(filename))[0]

def add_text_to_video(input_path, output_path, text):
    """Add text overlay to a video"""
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-vf', f"drawtext=text='{text}':fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w-10):y=(h-text_h-10)",
        '-c:a', 'copy',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '18',
        output_path
    ]
    subprocess.run(cmd, check=True)

def combine_videos(video_files, output_file):
    """Combine videos with black frames in between"""
    # Create a text file for ffmpeg concat
    with open('concat_list.txt', 'w') as f:
        for i, video in enumerate(video_files):
            f.write(f"file '{video}'\n")
            # Add black clip after each video except the last one
            if i < len(video_files) - 1:
                black_clip = f"black_{i}.mp4"
                create_black_clip(BLACK_FRAME_DURATION, black_clip)
                f.write(f"file '{black_clip}'\n")

    # Combine all videos
    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', 'concat_list.txt',
        '-c', 'copy',
        output_file
    ]
    subprocess.run(cmd, check=True)

    # Clean up temporary black clips
    for i in range(len(video_files) - 1):
        black_clip = f"black_{i}.mp4"
        if os.path.exists(black_clip):
            os.remove(black_clip)
    if os.path.exists('concat_list.txt'):
        os.remove('concat_list.txt')

def upload_to_youtube(youtube, file_path, title, description):
    """Upload video to YouTube"""
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['motion', 'security', 'timelapse'],
            'categoryId': '22'  # See https://developers.google.com/youtube/v3/docs/videoCategories/list
        },
        'status': {
            'privacyStatus': 'public',  # or 'public', 'private'
            'selfDeclaredMadeForKids': False
        }
    }

    insert_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
    )

    response = None
    while response is None:
        status, response = insert_request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%")

    print(f"Video uploaded! ID: {response['id']}")
    return response

def main():
    # Ensure output folder exists
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Get all video files in motion_clips folder
    video_files = sorted(glob.glob(os.path.join(MOTION_CLIPS_FOLDER, '*.mp4')))

    if not video_files:
        print("No video files found in motion_clips folder.")
        return

    # Process each video to add title text
    processed_files = []
    titles = []
    for i, video in enumerate(video_files):
        title = get_video_title(video)
        titles.append(title)

        output_path = os.path.join(OUTPUT_FOLDER, f"processed_{i}.mp4")
        add_text_to_video(video, output_path, title)
        processed_files.append(output_path)

    # Save titles to text file
    with open(TEXT_FILE, 'a') as f:
        f.write("\n".join(titles))

    # Generate output filename with timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_FOLDER, f"combined_{timestamp}.mp4")

    # Combine all videos with black frames in between
    combine_videos(processed_files, output_file)

    # Upload to YouTube
    try:
        youtube = get_authenticated_service()
        video_title = f"Motion Compilation AI-based KNN statistical learning {timestamp}"

        with open(DESCRIPTION_FILE, 'r') as f:
            description = f.read()

        upload_to_youtube(youtube, output_file, video_title, description)
    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred:\n{e.content}")

    # Clean up
    for video in video_files:
        os.remove(video)
    for processed in processed_files:
        if os.path.exists(processed):
            os.remove(processed)

    print("Processing complete!")

if __name__ == "__main__":
    main()
