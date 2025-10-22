import threading
import time
import logging
from flask import Flask, Response, render_template_string
import socket
import collections
from typing import Dict, Set
import cv2
import numpy as np
import datetime
import os
import subprocess
import sys
import av
import io


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
CONFIG = {
    'streams': {
        'stream1': {
            'host': '192.168.8.123',
            'port': 42069,
            'name': 'Main Camera',
            'active': True,
            'motion_detection': True,
            'output_directory': 'motion_clips'
        }
        # Add more streams here as needed
    }
}

# Global variables for stream management
stream_managers: Dict[str, 'StreamManager'] = {}

# HTML template for the streaming page
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>H264 Multi-Stream Viewer</title>
    <style>
        body { 
            margin: 20px; 
            font-family: Arial, sans-serif;
            background: #1a1a1a;
            color: white;
        }
        .container {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
        }
        .stream-container {
            background: #2d2d2d;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            max-width: 800px;
        }
        .stream-title {
            text-align: center;
            margin-bottom: 10px;
            font-size: 18px;
            font-weight: bold;
        }
        .video-container {
            border-radius: 5px;
            max-width: 100%;
            max-height: 600px;
            background: black;
            width: 100%;
            overflow: hidden;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        img {
            max-width: 100%;
            max-height: 600px;
            width: auto;
            height: auto;
        }
        .status {
            text-align: center;
            margin-top: 5px;
            font-size: 12px;
        }
        .online { color: #4CAF50; }
        .offline { color: #f44336; }
        .client-count {
            text-align: center;
            margin-top: 5px;
            font-size: 12px;
            color: #888;
        }
        .motion-status {
            text-align: center;
            margin-top: 5px;
            font-size: 12px;
            color: #ff9800;
        }
        .stream-controls {
            text-align: center;
            margin-top: 10px;
        }
        .stream-controls button {
            background: #4CAF50;
            color: white;
            border: none;
            padding: 8px 16px;
            margin: 0 5px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .stream-controls button:hover {
            background: #45a049;
        }
        .stream-controls button:disabled {
            background: #666;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <h1>Live Camera Stream Viewer</h1>
    <div class="container">
        {% for stream_id, stream_config in config.streams.items() %}
        <div class="stream-container">
            <div class="stream-title">{{ stream_config.name }}</div>
            <div class="video-container">
                <img id="video-{{ stream_id }}" src="" alt="{{ stream_config.name }} Stream">
            </div>
            <div class="status" id="status-{{ stream_id }}">
                <span class="offline">●</span> Loading...
            </div>
            <div class="client-count" id="clients-{{ stream_id }}">
                Clients: 0
            </div>
            {% if stream_config.motion_detection %}
            <div class="motion-status" id="motion-{{ stream_id }}">
                Motion: No detection
            </div>
            {% endif %}
            <div class="stream-controls">
                <button onclick="switchStream('{{ stream_id }}', 'mjpg')">MJPEG Stream</button>
                <button onclick="switchStream('{{ stream_id }}', 'h264')" disabled>H264 Stream (Coming Soon)</button>
                <button onclick="reconnectStream('{{ stream_id }}')">Reconnect</button>
            </div>
        </div>
        {% endfor %}
    </div>

    <script>
        // Store current stream types for each video
        const streamTypes = {};
        
        // Initialize streams when page loads
        function initializeStreams() {
            {% for stream_id in config.streams.keys() %}
            initializeStream('{{ stream_id }}', 'mjpg');
            {% endfor %}
        }
        
        function initializeStream(streamId, streamType) {
            const img = document.getElementById('video-' + streamId);
            const status = document.getElementById('status-' + streamId);
            
            // Always use MJPEG for compatibility
            const streamUrl = '/mjpg_feed/' + streamId;
            
            // Set image source for MJPEG stream
            img.src = streamUrl;
            status.innerHTML = '<span class="online">●</span> Connecting...';
            
            // Image event handlers
            img.onerror = function() {
                console.error('Image error for stream ' + streamId);
                status.innerHTML = '<span class="offline">●</span> Connection error';
                setTimeout(() => initializeStream(streamId, streamType), 5000);
            };
            
            img.onload = function() {
                status.innerHTML = '<span class="online">●</span> Live';
                console.log('Stream loaded successfully: ' + streamId);
            };
            
            // Store current stream type
            streamTypes[streamId] = streamType;
            
            // Start status updates
            startStatusUpdates(streamId);
        }
        
        function switchStream(streamId, newStreamType) {
            console.log('Switching stream ' + streamId + ' to ' + newStreamType);
            if (newStreamType === 'mjpg') {
                initializeStream(streamId, newStreamType);
            } else {
                alert('H264 streaming not yet implemented. Using MJPEG.');
                initializeStream(streamId, 'mjpg');
            }
        }
        
        function reconnectStream(streamId) {
            const currentType = streamTypes[streamId] || 'mjpg';
            console.log('Reconnecting stream ' + streamId + ' with type ' + currentType);
            
            // Force reload by adding timestamp to URL
            const img = document.getElementById('video-' + streamId);
            const streamUrl = '/mjpg_feed/' + streamId + '?t=' + new Date().getTime();
            img.src = streamUrl;
            
            const status = document.getElementById('status-' + streamId);
            status.innerHTML = '<span class="online">●</span> Reconnecting...';
        }
        
        function startStatusUpdates(streamId) {
            // Update client count and motion status periodically
            const updateInterval = setInterval(() => {
                const img = document.getElementById('video-' + streamId);
                const status = document.getElementById('status-' + streamId);
                const clients = document.getElementById('clients-' + streamId);
                const motion = document.getElementById('motion-' + streamId);
                
                // Only update if image is still on the page
                if (!img) {
                    clearInterval(updateInterval);
                    return;
                }
                
                // Update client count
                fetch('/api/streams/' + streamId + '/clients')
                    .then(response => {
                        if (!response.ok) {
                            throw new Error('Network response was not ok');
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (clients) {
                            clients.textContent = 'Clients: ' + data.client_count;
                        }
                    })
                    .catch(error => {
                        console.error('Error fetching client count:', error);
                        if (clients) {
                            clients.textContent = 'Clients: Error';
                        }
                    });
                
                // Update motion status if motion detection is enabled
                if (motion) {
                    fetch('/api/streams/' + streamId + '/motion')
                        .then(response => {
                            if (!response.ok) {
                                throw new Error('Network response was not ok');
                            }
                            return response.json();
                        })
                        .then(data => {
                            motion.textContent = 'Motion: ' + (data.motion_detected ? 'DETECTED' : 'No detection');
                            motion.style.color = data.motion_detected ? '#ff4444' : '#ff9800';
                        })
                        .catch(error => {
                            console.error('Error fetching motion status:', error);
                            motion.textContent = 'Motion: Unknown';
                        });
                }
            }, 3000); // Update every 3 seconds
            
            // Store the interval ID so we can clear it if needed
            img.dataset.updateInterval = updateInterval;
        }
        
        // Clean up intervals when page is unloaded
        window.addEventListener('beforeunload', function() {
            {% for stream_id in config.streams.keys() %}
            const img = document.getElementById('video-{{ stream_id }}');
            if (img && img.dataset.updateInterval) {
                clearInterval(parseInt(img.dataset.updateInterval));
            }
            {% endfor %}
        });
        
        // Start streams when page loads
        document.addEventListener('DOMContentLoaded', function() {
            initializeStreams();
        });
        
        // Reconnect streams if page becomes visible again
        document.addEventListener('visibilitychange', function() {
            if (!document.hidden) {
                // Reinitialize streams when page becomes visible
                setTimeout(() => {
                    {% for stream_id in config.streams.keys() %}
                    const currentType = streamTypes['{{ stream_id }}'] || 'mjpg';
                    initializeStream('{{ stream_id }}', currentType);
                    {% endfor %}
                }, 1000);
            }
        });
    </script>
</body>
</html>
'''

class StreamClient:
    """Represents a client consuming the stream"""
    def __init__(self):
        self.connected = True
        self.buffer = collections.deque(maxlen=100)  # Buffer for recent frames
        
    def add_frame(self, frame_data):
        """Add a frame to client's buffer"""
        self.buffer.append(frame_data)
        
    def get_frames(self):
        """Generator that yields frames from buffer"""
        while self.connected:
            if self.buffer:
                yield self.buffer.popleft()
            else:
                time.sleep(0.001)  # Small sleep to prevent busy waiting
                
                
class MotionAnalyzer:
    def __init__(self, output_directory="motion_clips", fps=30):
        # Background subtractor with parameters tuned for heat haze
        self.fgbg = cv2.createBackgroundSubtractorKNN(
            history=400,
            dist2Threshold=1000,
            detectShadows=False
        )
        
        # Motion validation parameters
        self.min_contour_area = 500  # formerly 1500, Minimum contour area to consider
        self.motion_buffer = collections.deque(maxlen=5)  # Stores recent motion states
        self.required_consecutive = 3  # Reduced from 5 to be more responsive
        self.heat_haze_kernel_size = 25
        
        # Video clip parameters
        self.clip_before = 1.0  # Increased from 0.5 to capture more pre-motion
        self.clip_after = 2.0  # Increased from 1.0 to capture more post-motion
        self.min_clip_length = 2.0  # Increased from 1.5 seconds
        
        # Tracking state
        self.is_recording = False
        self.clip_frames = []  # Store OpenCV frames for video writing
        self.clip_start_time = None
        self.last_motion_time = None
        self.frame_buffer = collections.deque(maxlen=int(fps * 4))  # Store 3 seconds of frames
        self.circular_mask = None
        self.mask_radius = 1232 // 2
        self.output_directory = output_directory
        self.motion_detected = False
        self.last_motion_update = time.time()
        
        # Frame processing
        self.frame_counter = 0
        self.process_every_n_frames = 1  # Process every 2nd frame (was 3)
        self.fps = fps
        
        # Timing control for recording
        self.last_frame_time = None
        self.frame_interval = 1.0 / fps
        
        # Create output directory
        os.makedirs(output_directory, exist_ok=True)

    def _create_circular_mask(self, frame):
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        center = (width // 2, height // 2)
        cv2.circle(mask, center, self.mask_radius, 255, -1)
        return mask

    def detect_significant_motion(self, frame):
        """Same as your original motion detection"""
        #if self.circular_mask is None:
            #self.circular_mask = self._create_circular_mask(frame) #uncomment to add the mask
        
        # Preprocessing to reduce heat haze effects
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (self.heat_haze_kernel_size, self.heat_haze_kernel_size), 0)
        #blurred = cv2.bitwise_and(blurred, blurred, mask=self.circular_mask)  # Uncomment if using mask
        
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

    def process_frame(self, frame, frame_bytes):
        """Process a frame for motion detection with proper timing"""
        current_time = time.time()
        
        # Store frame with timestamp for accurate timing
        frame_data = {
            'frame': frame.copy(),
            'timestamp': current_time
        }
        self.frame_buffer.append(frame_data)
        
        # Frame sampling to reduce CPU load
        self.frame_counter += 1
        if self.frame_counter % self.process_every_n_frames != 0:
            return self.motion_detected
            
        # Detect motion
        has_motion = self.detect_significant_motion(frame)
        
        if has_motion:
            if not self.is_recording:
                # Start new clip - calculate how many pre-motion frames to include
                self.is_recording = True
                self.clip_start_time = current_time
                
                # Find frames from before motion started
                pre_motion_frames = []
                cutoff_time = current_time - self.clip_before
                
                for frame_data in list(self.frame_buffer):
                    if frame_data['timestamp'] >= cutoff_time:
                        pre_motion_frames.append(frame_data)
                
                self.clip_frames = pre_motion_frames
                logger.info(f"Motion detected at {datetime.datetime.fromtimestamp(current_time)}")
        
            # Add current frame to clip
            self.clip_frames.append(frame_data)
            self.last_motion_time = current_time
            self.motion_detected = True
            self.last_motion_update = current_time
            
        else:
            if self.is_recording:
                # Add current frame to clip (continue briefly after motion stops)
                self.clip_frames.append(frame_data)
            
                # Check if we should end the clip
                if (current_time - self.last_motion_time) > self.clip_after:
                    # Save clip if it meets minimum length
                    clip_length = current_time - self.clip_start_time
                    if clip_length >= self.min_clip_length:
                        self._save_video_clip(self.clip_frames, self.clip_start_time)
                        logger.info(f"Saved motion clip: {clip_length:.2f} seconds")
                
                    # Reset recording state
                    self.is_recording = False
                    self.clip_frames = []
        
            # Reset motion detected status after 2 seconds of no motion
            if current_time - self.last_motion_update > 2.0:
                self.motion_detected = False
        
        return has_motion

    def _save_video_clip(self, frames, timestamp):
        """Save video clip with proper timing"""
        if not frames:
            return
        
        try:
            # Format filename with timestamp
            filename = f"motion_{datetime.datetime.fromtimestamp(timestamp).strftime('%Y%m%d_%H%M%S')}.mp4"
            output_path = os.path.join(self.output_directory, filename)
            
            # Get frame size from first frame - FIXED: access the 'frame' key
            height, width = frames[0]['frame'].shape[:2]  # CHANGED THIS LINE
            
            # Calculate actual clip duration from timestamps
            actual_duration = frames[-1]['timestamp'] - frames[0]['timestamp']
            
            # Ensure minimum duration
            if actual_duration < self.min_clip_length:
                # Extend the clip by duplicating frames to meet minimum duration
                needed_frames = int((self.min_clip_length - actual_duration) * self.fps)
                last_frame = frames[-1]['frame']  # CHANGED: access 'frame' key
                for _ in range(needed_frames):
                    frames.append({
                        'frame': last_frame.copy(),
                        'timestamp': frames[-1]['timestamp'] + (1.0 / self.fps)
                    })
                actual_duration = self.min_clip_length
            
            # Calculate FPS based on actual duration and frame count
            actual_fps = len(frames) / actual_duration
            
            # Clamp FPS to reasonable range (5-30 FPS)
            actual_fps = max(5.0, min(30.0, actual_fps))
            
            logger.info(f"Saving clip with {len(frames)} frames, duration: {actual_duration:.2f}s, FPS: {actual_fps:.1f}")
            
            # Extract just the frame data for writing - FIXED: access 'frame' key
            frame_data = [frame_data['frame'] for frame_data in frames]  # CHANGED THIS LINE
            
            # Write video using FFmpeg with constant frame rate
            process = subprocess.Popen([
                'ffmpeg',
                '-y',  # Overwrite without asking
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-s', f'{width}x{height}',
                '-pix_fmt', 'bgr24',
                '-r', str(actual_fps),  # Use constant calculated FPS
                '-i', '-',
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-r', str(actual_fps),  # Output FPS (same as input)
                '-vsync', 'cfr',  # Constant frame rate (changed from vfr)
                output_path
            ], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            
            for frame in frame_data:
                process.stdin.write(frame.tobytes())
            
            process.stdin.close()
            
            # Wait for process to complete and check for errors
            _, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {stderr.decode()}")
            
            # Check if file was created successfully
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                logger.info(f"Successfully saved clip: {output_path} ({os.path.getsize(output_path)} bytes)")
                return output_path
            else:
                logger.error(f"Failed to save clip: {output_path} (file is empty or doesn't exist)")
                return None
            
        except Exception as e:
            logger.error(f"Error saving video clip: {e}")
            return None

class StreamManager:
    """Manages a single TCP stream and serves multiple clients"""
    
    def __init__(self, stream_id: str, host: str, port: int, motion_detection=False, output_directory="motion_clips", fps=30):
        self.stream_id = stream_id
        self.host = host
        self.port = port
        self.clients: Set[StreamClient] = set()
        self.clients_lock = threading.Lock()
        self.running = True
        self.cap = None  # Change from socket to OpenCV VideoCapture
        self.thread = None
        self.last_frame = None
        self.motion_detection = motion_detection
        self.motion_analyzer = None
        
        if motion_detection:
            self.motion_analyzer = MotionAnalyzer(output_directory, fps=fps)
        
    def start(self):
        """Start the stream manager thread"""
        self.thread = threading.Thread(target=self._stream_worker, daemon=True)
        self.thread.start()
        logger.info(f"[{self.stream_id}] Stream manager started (motion detection: {self.motion_detection})")
        
    def stop(self):
        """Stop the stream manager"""
        self.running = False
        # Disconnect all clients
        with self.clients_lock:
            for client in self.clients:
                client.connected = False
            self.clients.clear()
        
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
        
        logger.info(f"[{self.stream_id}] Stream manager stopped")
        
    def add_client(self) -> StreamClient:
        """Add a new client to this stream"""
        client = StreamClient()
        with self.clients_lock:
            self.clients.add(client)
        logger.info(f"[{self.stream_id}] Client added. Total clients: {len(self.clients)}")
        return client
        
    def remove_client(self, client: StreamClient):
        """Remove a client from this stream"""
        client.connected = False
        with self.clients_lock:
            self.clients.discard(client)
        logger.info(f"[{self.stream_id}] Client removed. Total clients: {len(self.clients)}")
        
    def get_client_count(self):
        """Get current number of connected clients"""
        with self.clients_lock:
            return len(self.clients)
    
    def get_motion_status(self):
        """Get current motion detection status"""
        if self.motion_analyzer:
            return self.motion_analyzer.motion_detected
        return False
        
    def _connect_tcp_stream(self):
        """Connect to TCP stream using OpenCV VideoCapture (like your working version)"""
        stream_url = f"tcp://{self.host}:{self.port}"
        try:
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                logger.error(f"[{self.stream_id}] Failed to connect to TCP stream at {stream_url}")
                return None
            
            # Set buffer size to minimize latency
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            logger.info(f"[{self.stream_id}] Connected to TCP stream at {stream_url}")
            return cap
        except Exception as e:
            logger.error(f"[{self.stream_id}] Failed to connect to TCP stream: {e}")
            return None

    def _read_frame(self):
        """Read a frame from the TCP stream"""
        if self.cap is None or not self.cap.isOpened():
            return None, None
        
        ret, frame = self.cap.read()
        if not ret:
            logger.warning(f"[{self.stream_id}] Failed to read frame from TCP stream")
            return None, None
        
        # Convert frame to bytes for streaming to clients
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_bytes = buffer.tobytes()
        
        return frame, frame_bytes

    def _distribute_frame(self, frame_bytes):
        """Distribute frame to all connected clients"""
        self.last_frame = frame_bytes  # Keep last frame for new clients
        
        # Distribute to clients
        with self.clients_lock:
            clients_to_remove = []
            
            for client in self.clients:
                try:
                    client.add_frame(frame_bytes)
                except Exception as e:
                    logger.error(f"[{self.stream_id}] Error distributing frame to client: {e}")
                    clients_to_remove.append(client)
        
            # Remove problematic clients
            for client in clients_to_remove:
                self.clients.discard(client)

    def _stream_worker(self):
        """Worker thread to continuously read frames from TCP stream"""
        reconnect_delay = 2
        
        while self.running:
            self.cap = self._connect_tcp_stream()
            
            if self.cap is None:
                logger.warning(f"[{self.stream_id}] Connection failed, retrying in {reconnect_delay} seconds...")
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, 30)  # Exponential backoff, max 30s
                continue
            
            reconnect_delay = 2  # Reset reconnect delay on successful connection
            logger.info(f"[{self.stream_id}] Starting stream distribution")
            
            # Main stream reading loop
            while self.running and self.cap.isOpened():
                frame, frame_bytes = self._read_frame()
                
                if frame is None or frame_bytes is None:
                    # Connection error, break to reconnect
                    break
                
                # Process motion detection if enabled
                if self.motion_detection and self.motion_analyzer:
                    try:
                        self.motion_analyzer.process_frame(frame, frame_bytes)
                    except Exception as e:
                        logger.error(f"[{self.stream_id}] Motion detection error: {e}")
                
                # Distribute frame to all clients
                self._distribute_frame(frame_bytes)
                
                # Small sleep to prevent overwhelming the system
                time.sleep(0.01)
            
            # Clean up
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None
            
            logger.info(f"[{self.stream_id}] Stream connection closed, reconnecting...")
            time.sleep(2)

def generate_h264_frames(stream_manager: StreamManager):
    """
    Generate H264 stream for HTTP streaming for a specific client
    """
    # Create a new client for this HTTP request
    client = stream_manager.add_client()
    
    try:
        logger.info(f"[{stream_manager.stream_id}] Starting H264 stream for client")
        
        # Send any buffered frame first (if available)
        if stream_manager.last_frame:
            yield stream_manager.last_frame
        
        # Stream new frames as they arrive
        for frame in client.get_frames():
            yield frame
            
    except GeneratorExit:
        logger.info(f"[{stream_manager.stream_id}] Client disconnected (generator exit)")
    except Exception as e:
        logger.error(f"[{stream_manager.stream_id}] H264 frame generation error: {e}")
    finally:
        # Always remove client when done
        stream_manager.remove_client(client)

# Flask routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, config=CONFIG)

@app.route('/h264_feed/<stream_id>')
def h264_feed(stream_id):
    """
    Alternative H264 feed - actually serves MJPEG for compatibility
    """
    return mjpg_feed(stream_id)  # Just use MJPEG for now
    
def h264_feed_old(stream_id):
    """
    Stream H264 data to client as MJPG for browser compatibility
    """
    if stream_id not in stream_managers:
        return "Stream not found", 404
    
    stream_manager = stream_managers[stream_id]
    
    def generate_mjpeg():
        """Generate MJPEG stream for browser compatibility"""
        client = stream_manager.add_client()
        
        try:
            logger.info(f"[{stream_manager.stream_id}] Starting MJPEG stream for client")
            
            # Send multipart header
            boundary = 'frame'
            headers = f'--{boundary}\r\nContent-Type: image/jpeg\r\n\r\n'
            
            # Send any buffered frame first
            if stream_manager.last_frame:
                yield headers.encode() + stream_manager.last_frame
            
            # Stream new frames as they arrive
            for frame_bytes in client.get_frames():
                multipart_frame = headers.encode() + frame_bytes
                yield multipart_frame
                
        except GeneratorExit:
            logger.info(f"[{stream_manager.stream_id}] Client disconnected (generator exit)")
        except Exception as e:
            logger.error(f"[{stream_manager.stream_id}] MJPEG frame generation error: {e}")
        finally:
            # Always remove client when done
            stream_manager.remove_client(client)
    
    return Response(
        generate_mjpeg(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/mp4_feed/<stream_id>')
def mp4_feed(stream_id):
    """
    Stream as fragmented MP4 for better browser support
    """
    if stream_id not in stream_managers:
        return "Stream not found", 404
    
    stream_manager = stream_managers[stream_id]
    
    def generate_mp4_fragments():
        """Generate MP4 fragments using FFmpeg"""
        client = stream_manager.add_client()
        
        try:
            logger.info(f"[{stream_manager.stream_id}] Starting MP4 fragment stream for client")
            
            # Start FFmpeg to convert JPEG frames to MP4 fragments
            process = subprocess.Popen([
                'ffmpeg',
                '-y',
                '-f', 'image2pipe',
                '-vcodec', 'mjpeg',
                '-r', '25',
                '-i', '-',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-f', 'mp4',
                '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
                '-'
            ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Send any buffered frame first
            if stream_manager.last_frame:
                process.stdin.write(stream_manager.last_frame)
            
            # Stream new frames to FFmpeg and get MP4 output
            for frame_bytes in client.get_frames():
                process.stdin.write(frame_bytes)
                
                # Read output from FFmpeg
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    yield chunk
                    
        except GeneratorExit:
            logger.info(f"[{stream_manager.stream_id}] Client disconnected (generator exit)")
            try:
                process.stdin.close()
                process.terminate()
            except:
                pass
        except Exception as e:
            logger.error(f"[{stream_manager.stream_id}] MP4 fragment generation error: {e}")
            try:
                process.stdin.close()
                process.terminate()
            except:
                pass
        finally:
            # Always remove client when done
            stream_manager.remove_client(client)
            try:
                process.stdin.close()
                process.terminate()
            except:
                pass
    
    return Response(
        generate_mp4_fragments(),
        mimetype='video/mp4',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )
    
@app.route('/mjpg_feed/<stream_id>')
def mjpg_feed(stream_id):
    """
    Stream as MJPEG - most compatible with browsers
    """
    if stream_id not in stream_managers:
        return "Stream not found", 404
    
    stream_manager = stream_managers[stream_id]
    
    def generate_mjpg():
        """Generate proper MJPEG stream with boundaries"""
        client = stream_manager.add_client()
        
        try:
            logger.info(f"[{stream_manager.stream_id}] Starting MJPEG stream for client")
            
            # Define multipart boundary
            boundary = 'frame'
            
            # Send initial content type header
            yield (f'Content-Type: multipart/x-mixed-replace; boundary={boundary}\r\n\r\n').encode()
            
            # Send any buffered frame first
            if stream_manager.last_frame:
                yield (f'--{boundary}\r\n'
                       f'Content-Type: image/jpeg\r\n'
                       f'Content-Length: {len(stream_manager.last_frame)}\r\n'
                       f'\r\n').encode() + stream_manager.last_frame + b'\r\n'
                yield b'--frame\r\n'
            
            # Stream new frames as they arrive
            for frame_bytes in client.get_frames():
                multipart_data = (f'Content-Type: image/jpeg\r\n'
                                 f'Content-Length: {len(frame_bytes)}\r\n'
                                 f'\r\n').encode() + frame_bytes + b'\r\n'
                yield multipart_data
                yield b'--frame\r\n'
                
        except GeneratorExit:
            logger.info(f"[{stream_manager.stream_id}] Client disconnected (generator exit)")
        except Exception as e:
            logger.error(f"[{stream_manager.stream_id}] MJPEG generation error: {e}")
        finally:
            # Always remove client when done
            stream_manager.remove_client(client)
    
    return Response(
        generate_mjpg(),
        mimetype='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, private',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Pragma': 'no-cache'
        }
    )
    
@app.route('/api/streams', methods=['GET'])
def list_streams():
    return {'streams': CONFIG['streams']}

@app.route('/api/streams/<stream_id>/clients', methods=['GET'])
def get_client_count(stream_id):
    """Get number of connected clients for a stream"""
    if stream_id not in stream_managers:
        return {'error': 'Stream not found'}, 404
    
    client_count = stream_managers[stream_id].get_client_count()
    return {'client_count': client_count}

@app.route('/api/streams/<stream_id>/motion', methods=['GET'])
def get_motion_status(stream_id):
    """Get motion detection status for a stream"""
    if stream_id not in stream_managers:
        return {'error': 'Stream not found'}, 404
    
    motion_detected = stream_managers[stream_id].get_motion_status()
    return {'motion_detected': motion_detected}

@app.route('/api/streams/add', methods=['POST'])
def api_add_stream():
    # Implementation for dynamic stream addition via API
    pass

@app.route('/api/streams/<stream_id>/remove', methods=['POST'])
def api_remove_stream(stream_id):
    if stream_id in stream_managers:
        stream_managers[stream_id].stop()
        stream_managers.pop(stream_id)
        if stream_id in CONFIG['streams']:
            CONFIG['streams'].pop(stream_id)
        return {'status': 'success', 'message': f'Stream {stream_id} removed'}
    else:
        return {'status': 'error', 'message': 'Stream not found'}, 404

def add_stream(stream_id, host, port, name=None, motion_detection=False, output_directory="motion_clips"):
    """
    Add a new stream dynamically
    """
    if stream_id in stream_managers:
        logger.warning(f"Stream {stream_id} already exists")
        return False
    
    # Update config
    CONFIG['streams'][stream_id] = {
        'host': host,
        'port': port,
        'name': name or stream_id,
        'active': True,
        'motion_detection': motion_detection,
        'output_directory': output_directory
    }
    
    # Create and start stream manager
    stream_manager = StreamManager(stream_id, host, port, motion_detection, output_directory)
    stream_managers[stream_id] = stream_manager
    stream_manager.start()
    
    logger.info(f"Added new stream: {stream_id} ({host}:{port}) with motion detection: {motion_detection}")
    return True

def remove_stream(stream_id):
    """
    Remove a stream
    """
    if stream_id in stream_managers:
        stream_managers[stream_id].stop()
        stream_managers.pop(stream_id)
        CONFIG['streams'].pop(stream_id, None)
        logger.info(f"Removed stream: {stream_id}")
        return True
    return False

# Initialize streams on startup
def initialize_streams():
    for stream_id, config in CONFIG['streams'].items():
        if config['active']:
            motion_detection = config.get('motion_detection', False)
            output_directory = config.get('output_directory', 'motion_clips')
            
            stream_manager = StreamManager(stream_id, config['host'], config['port'], 
                                         motion_detection, output_directory, fps=30)
            stream_managers[stream_id] = stream_manager
            stream_manager.start()
            logger.info(f"Initialized stream: {stream_id} (motion detection: {motion_detection})")

if __name__ == '__main__':
    initialize_streams()
    
    # Add more streams easily like this:
    # add_stream('stream2', '192.168.8.212', 42069, 'Backyard Camera', motion_detection=True)
    # add_stream('stream3', '192.168.8.213', 42069, 'Garage Camera', motion_detection=False)
    
    logger.info("Starting H264 Flask streaming server on http://0.0.0.0:42069")
    app.run(host='0.0.0.0', port=42069, threaded=True)
