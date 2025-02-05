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
metadata_text = ""


def setup_socket():
    global socket_server
    socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_server.bind((connection_address, connection_port))
    socket_server.listen(1)
    print(f"RTMP Server listening on port {connection_port}")


def parse_stream_info(line):
    info = {}
    if "Video:" in line:
        # Extract video details
        parts = line.split(",")
        info["type"] = "Video"
        for part in parts:
            if "x" in part and any(c.isdigit() for c in part):  # Resolution
                info["resolution"] = part.strip()
            if "fps" in part:  # Frame rate
                info["fps"] = part.strip()
            if "yuv" in part.lower():  # Pixel format
                info["format"] = part.strip()
    elif "Audio:" in line:
        # Extract audio details
        parts = line.split(",")
        info["type"] = "Audio"
        for part in parts:
            if "Hz" in part:  # Sample rate
                info["sample_rate"] = part.strip()
            if "stereo" in part.lower() or "mono" in part.lower():  # Channels
                info["channels"] = part.strip()
            if "kb/s" in part:  # Bitrate
                info["bitrate"] = part.strip()
    return info


def read_metadata(process):
    global metadata_text
    stream_info = {"Video": [], "Audio": []}

    while True:
        output = process.stderr.readline().decode().strip()
        if not output:
            break
        if "Video:" in output or "Audio:" in output:
            info = parse_stream_info(output)
            if info:
                if info["type"] == "Video":
                    stream_info["Video"].append(info)
                else:
                    stream_info["Audio"].append(info)

                # Format metadata text for display
                metadata_text = "Stream Information:\n\n"
                if stream_info["Video"]:
                    metadata_text += "Video Stream:\n"
                    for v in stream_info["Video"]:
                        metadata_text += f"Resolution: {v.get('resolution', 'N/A')}\n"
                        metadata_text += f"Frame Rate: {v.get('fps', 'N/A')}\n"
                        metadata_text += f"Format: {v.get('format', 'N/A')}\n"

                if stream_info["Audio"]:
                    metadata_text += "\nAudio Stream:\n"
                    for a in stream_info["Audio"]:
                        metadata_text += f"Sample Rate: {a.get('sample_rate', 'N/A')}\n"
                        metadata_text += f"Channels: {a.get('channels', 'N/A')}\n"
                        metadata_text += f"Bitrate: {a.get('bitrate', 'N/A')}\n"

                print(metadata_text)


def display_window():
    global metadata_text
    while running:
        # Larger window for more content
        img = np.zeros((700, 1000, 3), np.uint8)

        # Display configuration info
        config_text = [
            f"Video Input: {video_device}",
            f"Audio Input: {audio_device}",
            f"RTMP URL: {rtmp_url}",
            "----------------------------------------",  # Separator
        ]

        # Draw config info at top
        y = 50
        for line in config_text:
            cv2.putText(
                img,
                line,
                (50, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )
            y += 30

        # Draw stream metadata below config
        y += 20  # Add space after separator
        if metadata_text:
            for line in metadata_text.split("\n"):
                cv2.putText(
                    img,
                    line,
                    (50, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                )
                y += 30
        else:
            cv2.putText(
                img,
                "Waiting for stream metadata...",
                (50, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

        # Keep quit message at bottom
        cv2.putText(
            img,
            "Press 'q' to stop",
            (50, 650),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
        )

        cv2.imshow("Stream Information", img)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            cleanup()
        time.sleep(0.1)


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
