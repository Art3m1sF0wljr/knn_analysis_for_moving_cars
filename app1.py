import os
import sys
import datetime
import subprocess
import glob
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow

# Configuration
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
CHANNEL_ID = ""  # Replace with your channel ID
MOTION_CLIPS_FOLDER = "motion_clips"
OUTPUT_FOLDER = "output"
BLACK_FRAME_DURATION = 30  # frames at 30fps = 0.5 seconds
TEXT_FILE = "video_titles.txt"

def get_authenticated_service():
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=YOUTUBE_UPLOAD_SCOPE)
    storage = Storage("%s-oauth2.json" % sys.argv[0])
    credentials = storage.get()
    
    if credentials is None or credentials.invalid:
        credentials = run_flow(flow, storage)
    
    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 credentials=credentials)

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
            'description': "tbd",
            'tags': ['motion', 'security', 'timelapse'],
            'categoryId': '22'  # See https://developers.google.com/youtube/v3/docs/videoCategories/list
        },
        'status': {
            'privacyStatus': 'unlisted',  # or 'public', 'private'
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
        video_title = f"Motion Compilation {timestamp}"
        
        with open(TEXT_FILE, 'r') as f:
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
