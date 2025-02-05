import cv2
import numpy as np
import ffmpeg
import subprocess
import threading
import time
import json
import socket
import sys

# Define Video/Audio Sources
video_device = "1080P Pro Stream"
audio_device = "Microphone (1080P Pro Stream)"

# Define RTMP Source
connection_address = "127.0.0.1"
connection_port = 1935
connection_keys = "live/live"
rtmp_url = f"rtmp://{connection_address}:{connection_port}/{connection_keys}"

# Define Frame Size
width, height = 1280, 720
frame_size = width * height * 3  # Size of a single frame in bytes

# Global variables
process = None
socket_server = None
running = True


def setup_socket():
    global socket_server
    socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_server.bind((connection_address, connection_port))
    socket_server.listen(1)
    print(f"RTMP Server listening on port {connection_port}")


def read_metadata(process):
    while True:
        output = process.stderr.readline().decode().strip()
        if not output:
            break
        if "Video:" in output or "Audio:" in output:
            print(output)


def cleanup():
    global process, socket_server, running
    running = False
    if process:
        process.terminate()
        process.wait()
    if socket_server:
        socket_server.close()
    print("RTMP stream closed.")
    sys.exit(0)


def display_window():
    img = np.zeros((200, 400, 3), np.uint8)
    cv2.putText(
        img,
        "Press 'q' to stop",
        (50, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (255, 255, 255),
        2,
    )
    cv2.imshow("Control Window", img)
    while running:
        if cv2.waitKey(1) & 0xFF == ord("q"):
            cleanup()
        time.sleep(0.1)


def run_stream():
    global process
    try:
        while running:
            try:
                process.stdout.read(frame_size)
            except ValueError as e:
                print(f"Frame error: {e}")
                continue
    except Exception as e:
        print(f"Stream error: {e}")


try:
    # Initialize socket server
    setup_socket()

    print(f"Starting webcam stream to {rtmp_url}...")
    ffmpeg_command = f'ffmpeg -f dshow -rtbufsize 100M -framerate 30 -video_size {width}x{height} -i video="{video_device}" -f dshow -i audio="{audio_device}" -c:v libx264 -preset veryfast -b:v 2000k -maxrate 2000k -bufsize 4000k -pix_fmt yuv420p -g 60 -keyint_min 30 -sc_threshold 0 -c:a aac -b:a 128k -ar 44100 -ac 2 -f flv {rtmp_url}'

    process = subprocess.Popen(
        ffmpeg_command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**8,
    )

    # Create and start all threads
    metadata_thread = threading.Thread(
        target=read_metadata, args=(process,), daemon=True
    )
    stream_thread = threading.Thread(target=run_stream, daemon=True)
    window_thread = threading.Thread(target=display_window, daemon=True)

    metadata_thread.start()
    stream_thread.start()
    window_thread.start()

    # Wait for threads
    metadata_thread.join()
    stream_thread.join()
    window_thread.join()

except Exception as e:
    print(f"Error: {e}")
    if process:
        stderr_output = process.stderr.read().decode("utf-8")
        print(f"FFmpeg stderr: {stderr_output}")
finally:
    cv2.destroyAllWindows()
