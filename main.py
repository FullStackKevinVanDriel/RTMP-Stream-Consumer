import cv2
import numpy as np
import ffmpeg
import subprocess
import threading
import time
import json
import socket
import sys

# Configure Video/Audio Sources
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
available_devices = {"video": [], "audio": []}


def setup_socket():
    global socket_server
    socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    socket_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    socket_server.bind((connection_address, connection_port))
    socket_server.listen(1)
    print(f"RTMP Server listening on port {connection_port}")


def list_dshow_devices():
    """List all DirectShow video and audio devices"""
    devices = {"video": [], "audio": []}

    cmd = "ffmpeg -list_devices true -f dshow -i dummy"
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

    lines = process.stderr.read().decode("utf-8").split("\n")
    current_type = None

    for line in lines:
        if "(video)" in line or "(audio)" in line:
            # Extract device name between quotes and type
            device_name = line.split('"')[1]
            device_type = "video" if "(video)" in line else "audio"
            devices[device_type].append(device_name)

    return devices


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


def display_window():
    global metadata_text, available_devices
    # List all DirectShow devices

    while running:
        img = np.zeros((700, 1000, 3), np.uint8)

        # Top section - Configuration
        y = 50
        config_text = [
            f"RTMP URL: {rtmp_url}",
            f"Selected Video: {video_device}",
            f"Selected Audio: {audio_device}",
            "----------------------------------------",
        ]
        for line in config_text:
            cv2.putText(
                img, line, (50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
            )
            y += 30

        # Middle section - Device Lists (two columns)
        y = 180
        # Video devices (left column)
        cv2.putText(
            img,
            "Available Video Devices:",
            (50, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        y += 30
        for device in available_devices["video"]:
            # Use yellow color if device matches selected
            color = (0, 255, 255) if device == video_device else (255, 255, 255)
            cv2.putText(
                img,
                f"- {device}",
                (70, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )
            y += 30

        # Audio devices (right column)
        y = 180
        cv2.putText(
            img,
            "Available Audio Devices:",
            (500, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        y += 30
        for device in available_devices["audio"]:
            # Use yellow color if device matches selected
            color = (0, 255, 255) if device == audio_device else (255, 255, 255)
            cv2.putText(
                img,
                f"- {device}",
                (520, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )
            y += 30

        # Vertical separator
        cv2.line(img, (475, 160), (475, 400), (255, 255, 255), 2)

        # Bottom section - Stream Metadata (two columns)
        # Headers at same y-position
        y = 420

        # Left column - Video header
        cv2.putText(
            img,
            "Video Stream Metadata:",
            (50, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        # Right column - Audio header
        cv2.putText(
            img,
            "Audio Stream Metadata:",
            (500, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )

        if metadata_text:
            sections = metadata_text.split("\n\n")
            y = 450  # Start both columns at same y

            # Video metadata (left column)
            if "Video Stream:" in metadata_text:
                for line in sections[1].split("\n")[1:]:
                    cv2.putText(
                        img,
                        line,
                        (70, y),  # Fixed left x-coordinate
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )
                    y += 30

            # Reset y for audio column
            y = 450
            # Audio metadata (right column)
            if "Audio Stream:" in metadata_text:
                for line in sections[2].split("\n")[1:]:
                    cv2.putText(
                        img,
                        line,
                        (520, y),  # Fixed right x-coordinate
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )
                    y += 30

        # Vertical separator for metadata section
        cv2.line(img, (475, 420), (475, 600), (255, 255, 255), 2)

        # Bottom - Quit message (moved up & changed to green)
        cv2.putText(
            img,
            "Press 'q' to stop",
            (50, 680),  # Moved up inside the window (previously 750)
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),  # Green color
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
    # Store devices first
    available_devices = list_dshow_devices()

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
