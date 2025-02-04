import cv2
import numpy as np
import ffmpeg
import subprocess
import threading
import time
import json
import socket
import signal
import sys

# Define RTMP Source
connection_address = "127.0.0.1"
connection_port = 1935
connection_keys = "live/webcam"
rtmp_url = f"rtmp://{connection_address}:{connection_port}/{connection_keys}"

# Define Frame Size
width, height = 1280, 720

# Store metadata globally
metadata = {}


# Function to read metadata from FFmpeg's stderr without interfering with video.
def read_metadata(process):
    global metadata

    while True:
        output = process.stderr.readline().decode().strip()
        if not output:
            break

        # Look for metadata-related lines in stderr
        if "Stream" in output or "Metadata" in output or "Duration" in output:
            print("Metadata:", output)  # Print metadata updates
            metadata["latest"] = output  # Store latest metadata info


# Function to check if RTMP server is listening on port 1935 and ready to accept connections.
def is_rtmp_ready(host=connection_address, port=connection_port, timeout=1):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False


# Function to handle cleanup on exit
def cleanup():
    if process:
        process.terminate()
    if startstream_process:
        startstream_process.terminate()
    cv2.destroyAllWindows()
    print("RTMP stream closed.")


# Register cleanup function to be called on exit
def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Open RTMP stream using FFmpeg
start_time = time.time()
startstream_executed = False
startstream_process = None

while True:
    try:
        # Start FFmpeg process with logging
        process = (
            ffmpeg.input(rtmp_url, f="flv", timeout=100, rtbufsize="1024M")
            .output("pipe:", format="rawvideo", pix_fmt="bgr24")
            .global_args("-loglevel", "verbose")
            .run_async(pipe_stdout=subprocess.PIPE, pipe_stderr=subprocess.PIPE)
        )

        if is_rtmp_ready() and not startstream_executed:
            # Execute the startstream.py script
            subprocess.Popen(["python", "startstream.py", "--rtmp_url", rtmp_url])
            startstream_executed = True

        # Start metadata reader in a separate thread
        metadata_thread = threading.Thread(
            target=read_metadata, args=(process,), daemon=True
        )
        metadata_thread.start()

        raw_frame = process.stdout.read(width * height * 3)  # Read one frame

        if not raw_frame:
            # Go back around if the stream is not yet ready
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
        break  # Exit the script on failureq

# Cleanup
cleanup()
