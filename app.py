import cv2
import numpy as np
import yt_dlp
import datetime
import os
from collections import deque
import subprocess
import time
import sys

class MotionAnalyzer:
    def __init__(self):
        # Background subtractor with parameters tuned for heat haze
        self.fgbg = cv2.createBackgroundSubtractorKNN(
            history=500,
            dist2Threshold=1200,
            detectShadows=False
        )

        # Motion validation parameters
        self.min_contour_area = 1500  # Minimum contour area to consider
        self.motion_buffer = deque(maxlen=5)  # Stores recent motion states
        self.required_consecutive = 5  # Frames needed to confirm motion
        self.heat_haze_kernel_size = 25
        # Video clip parameters
        self.clip_before = 1.0  # Seconds to include before motion
        self.clip_after = 2.0  # Seconds to include after motion
        self.min_clip_length = 1.5  # Minimum clip length in seconds

        # Tracking state
        self.is_recording = False
        self.clip_frames = []
        self.clip_start_time = None
        self.last_motion_time = None
        self.frame_buffer = deque()  # Stores frames for pre-motion recording
        self.circular_mask = None
        self.mask_radius = 1232 // 2

    def _create_circular_mask(self, frame):
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        center = (width // 2, height // 2)
        cv2.circle(mask, center, self.mask_radius, 255, -1)
        return mask

    def detect_significant_motion(self, frame):
        if self.circular_mask is None:
            self.circular_mask = self._create_circular_mask(frame)
        # Preprocessing to reduce heat haze effects
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.heat_haze_kernel_size, self.heat_haze_kernel_size), 0)
        blurred = cv2.bitwise_and(blurred, blurred, mask=self.circular_mask)
        # Background subtraction
        fgmask = self.fgbg.apply(blurred)

        # Morphological operations to reduce noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_OPEN, kernel)
        fgmask = cv2.morphologyEx(fgmask, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Check for significant contours
        significant_motion = False
        for contour in contours:
            if cv2.contourArea(contour) > self.min_contour_area:
                significant_motion = True
                break

        # Update motion buffer
        self.motion_buffer.append(significant_motion)

        # Check for consecutive motion frames
        if len(self.motion_buffer) >= self.required_consecutive:
            return all(self.motion_buffer)
        return False

def get_youtube_stream(url, resolution='720p'):

    ydl_opts = {
        'format': f'bestvideo[height<={resolution.split("p")[0]}]',
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url = info['url']

        cap = cv2.VideoCapture(stream_url)
        return cap

    except Exception as e:
        # Check if it's a fatal error (like the authentication error)
        if "Sign in to confirm you're not a bot" in str(e) or isinstance(e, yt_dlp.utils.DownloadError):
            print("Fatal error encountered. Restarting program in 10 seconds...")
            time.sleep(10)
            os.execl(sys.executable, sys.executable, *sys.argv)
        # For other errors, re-raise them
        raise

def save_video_clip(frames, fps, output_dir, timestamp):
    if not frames:
        return

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Format filename with timestamp
    filename = f"motion_{timestamp.strftime('%Y%m%d_%H%M%S')}.mp4"
    output_path = os.path.join(output_dir, filename)

    # Get frame size from first frame
    height, width = frames[0].shape[:2]

    # Write video using FFmpeg (more efficient than OpenCV's VideoWriter)
    process = subprocess.Popen([
        'ffmpeg',
        '-y',  # Overwrite without asking
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{width}x{height}',
        '-pix_fmt', 'bgr24',
        '-r', str(fps),
        '-i', '-',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        output_path
    ], stdin=subprocess.PIPE)

    for frame in frames:
        process.stdin.write(frame.tobytes())

    process.stdin.close()
    process.wait()

    return output_path

def main():
    # Configuration
    youtube_url = "https://www.youtube.com/watch?v=oHYVFlpuAlI"
    output_directory = "motion_clips"
    frame_buffer_size = 5  # Number of frames to keep in buffer
    restart_delay = 1

    while True:
        # Initialize
        cap = get_youtube_stream(youtube_url)
        fps = cap.get(cv2.CAP_PROP_FPS)
        analyzer = MotionAnalyzer()
        frame_buffer = deque(maxlen=int(fps * analyzer.clip_before))

        print(f"Starting stream analysis at {datetime.datetime.now()}")
        print(f"Stream FPS: {fps}")

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    print("Stream ended or connection lost")
                    break

                current_time = datetime.datetime.now()

                # Store frame in buffer
                frame_buffer.append(frame.copy())

                # Detect motion
                has_motion = analyzer.detect_significant_motion(frame)

                if has_motion:
                    if not analyzer.is_recording:
                        # Start new clip
                        analyzer.is_recording = True
                        analyzer.clip_start_time = current_time
                        analyzer.clip_frames = list(frame_buffer)  # Include pre-motion frames
                        print(f"Motion detected at {current_time}")

                    # Add current frame to clip
                    analyzer.clip_frames.append(frame.copy())
                    analyzer.last_motion_time = current_time
                else:
                    if analyzer.is_recording:
                        # Add current frame to clip (continue briefly after motion stops)
                        analyzer.clip_frames.append(frame.copy())

                        # Check if we should end the clip
                        if (current_time - analyzer.last_motion_time).total_seconds() > analyzer.clip_after:
                            # Save clip if it meets minimum length
                            clip_length = (current_time - analyzer.clip_start_time).total_seconds()
                            if clip_length >= analyzer.min_clip_length:
                                save_video_clip(
                                    analyzer.clip_frames,
                                    fps,
                                    output_directory,
                                    analyzer.clip_start_time
                                )
                                print(f"Saved clip: {clip_length:.2f} seconds")

                            # Reset recording state
                            analyzer.is_recording = False
                            analyzer.clip_frames = []

                # Display preview (optional)
                #cv2.imshow('Stream Preview', frame)
                #if cv2.waitKey(1) & 0xFF == ord('q'):
                #    break

        except KeyboardInterrupt:
            print("Stopping analysis...")
            sys.exit(0)
        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
        finally:
            cap.release()
            #cv2.destroyAllWindows()

            # Save any pending clip when stopping
            if analyzer.is_recording and analyzer.clip_frames:
                clip_length = (datetime.datetime.now() - analyzer.clip_start_time).total_seconds()
                if clip_length >= analyzer.min_clip_length:
                    save_video_clip(
                        analyzer.clip_frames,
                        fps,
                        output_directory,
                        analyzer.clip_start_time
                    )
                    print(f"Saved final clip: {clip_length:.2f} seconds")

if __name__ == "__main__":
    main()
