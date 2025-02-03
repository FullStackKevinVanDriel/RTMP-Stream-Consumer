import cv2
import numpy as np
import ffmpeg
import subprocess
import threading
import time
import json
import socket

# Define RTMP Source
rtmp_url = "rtmp://127.0.0.1:1935/live/webcam"

# Define Frame Size
width, height = 1280, 720

# Store metadata globally
metadata = {}


def read_metadata(process):
    """Reads metadata from FFmpeg's stderr without interfering with video."""
    global metadata
    print("Waiting to read metadata from stream")

    while True:
        output = process.stderr.readline().decode().strip()
        if not output:
            break

        # Look for metadata-related lines in stderr
        if "Stream" in output or "Metadata" in output or "Duration" in output:
            print("Metadata:", output)  # Print metadata updates
            metadata["latest"] = output  # Store latest metadata info


# Function to check if RTMP server is listening on port 1935
def is_rtmp_ready(host="127.0.0.1", port=1935, timeout=1):
    """Check if the RTMP server is ready to accept connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False


# Open RTMP stream using FFmpeg
start_time = time.time()
startstream_executed = False

while True:
    try:
        # Start FFmpeg process with logging
        process = (
            ffmpeg.input(rtmp_url, f="flv", timeout=100, rtbufsize="1024M")
            .output("pipe:", format="rawvideo", pix_fmt="bgr24")
            .global_args("-loglevel", "verbose", "-threads", "auto")  # Auto-threading
            .run_async(pipe_stdout=subprocess.PIPE, pipe_stderr=subprocess.PIPE)
        )

        if is_rtmp_ready():
            print("Listening for stream on port 1935")
            if not startstream_executed:
                # Execute the startstream.py script
                subprocess.Popen(["python", "startstream.py"])
                startstream_executed = True

        # Start metadata reader in a separate thread
        metadata_thread = threading.Thread(
            target=read_metadata, args=(process,), daemon=True
        )
        metadata_thread.start()

        raw_frame = process.stdout.read(width * height * 3)  # Read one frame

        if not raw_frame:
            print("Stream attempted but no frame detected. Retrying in 1 second...")
            process.terminate()
            time.sleep(1)
            continue

        print("Stream detected! Attempting playback...")

        # Convert raw frame to NumPy array
        frame = np.frombuffer(raw_frame, np.uint8).reshape([height, width, 3])

        # Display the frame
        cv2.imshow("RTMP Stream", frame)

        print("Playback started!")
        # Main loop to keep playing frames
        while True:
            raw_frame = process.stdout.read(width * height * 3)
            if not raw_frame:
                print("Stream lost. Exiting...")
                break

            frame = np.frombuffer(raw_frame, np.uint8).reshape([height, width, 3])
            cv2.imshow("RTMP Stream", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):  # Quit if 'q' is pressed
                print("Stream manually stopped.")
                break

        process.terminate()
        break  # Exit the main loop when streaming stops

    except Exception as e:
        print(f"Error: {e}")
        if process:
            stderr_output = process.stderr.read().decode("utf-8")
            print(f"FFmpeg stderr: {stderr_output}")
            process.terminate()
        break  # Exit the script on failure

# Cleanup
cv2.destroyAllWindows()
print("RTMP stream closed.")
