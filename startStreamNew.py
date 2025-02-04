import subprocess
import time
import argparse

# Parse command-line arguments
parser = argparse.ArgumentParser(
    description="Start streaming from webcam to RTMP server."
)
parser.add_argument(
    "--rtmp_url",
    type=str,
    default="rtmp://127.0.0.1:1935/live/webcam",
    help="RTMP URL to stream to",
)
args = parser.parse_args()

# Define the RTMP Stream URL
rtmp_url = args.rtmp_url

# Define FFmpeg command to stream from webcam
ffmpeg_command = [
    "ffmpeg",
    "-f", "dshow",  # Use DirectShow for webcam input
    "-rtbufsize", "100M",  # Buffer size to prevent frame drops
    "-framerate", "30",  # Set framerate
    "-video_size", "1280x720",  # Set resolution
    "-i", "video=1080P Pro Stream",  # Set webcam device name (adjust if needed)
    "-f", "dshow",  # Use DirectShow for audio input
    "-i", "audio=Microphone (1080P Pro Stream)",  # Set audio device name (adjust if needed)
    "-c:v", "libx264",  # Use H.264 encoding for video
    "-preset", "veryfast",  # Optimize encoding speed
    "-b:v", "2000k",  # Set video bitrate
    "-maxrate", "2000k",
    "-bufsize", "4000k",
    "-pix_fmt", "yuv420p",
    "-g", "60",  # GOP size (Keyframe interval)
    "-keyint_min", "30",
    "-sc_threshold", "0",
    "-c:a", "aac",  # Use AAC encoding for audio
    "-b:a", "128k",  # Set audio bitrate
    "-ar", "44100",  # Set audio sample rate
    "-ac", "2",  # Set number of audio channels
    "-f", "flv",  # Output format for RTMP streaming
    rtmp_url,
]

print(f"Starting webcam stream to {rtmp_url}...")

# Launch FFmpeg as a background process
ffmpeg_process = subprocess.Popen(
    ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
)

# Give FFmpeg some time to initialize
time.sleep(3)

# Check if FFmpeg started successfully
if ffmpeg_process.poll() is None:
    print("Webcam stream successfully started. Wait for stream detection...")
else:
    print("Failed to start webcam stream. Check device settings.")
    stderr_output = ffmpeg_process.stderr.read().decode("utf-8")
    print(f"FFmpeg stderr: {stderr_output}")

# Stream will continue running in the background. Press Ctrl+C to stop.
try:
    while True:
        time.sleep(1)  # Keep the script running while streaming
except KeyboardInterrupt:
    print("Stopping webcam stream...")
    ffmpeg_process.terminate()
    print("Webcam stream stopped.")