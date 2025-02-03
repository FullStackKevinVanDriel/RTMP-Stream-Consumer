import cv2
import numpy as np
import ffmpeg
import subprocess
import time

# Define RTMP Source
rtmp_url = "rtmp://127.0.0.1:1935/live/webcam"

# Define Frame Size
width, height = 1280, 720

# Max time to wait for the stream (in seconds)
max_wait_time = 60
wait_interval = 1  # Time between checks

# Open RTMP stream using FFmpeg and KEEP IT OPEN for 60 seconds
start_time = time.time()

while time.time() - start_time < max_wait_time:
    try:
        print("🔄 Waiting for RTMP stream...")

        # Start FFmpeg process
        process = (
            ffmpeg
            .input(rtmp_url, f='flv', rtsp_transport='tcp', timeout=100)  # Keeps connection open
            .output('pipe:', format='rawvideo', pix_fmt='bgr24')
            .run_async(pipe_stdout=True, pipe_stderr=subprocess.DEVNULL)  # Suppresses errors but stays open
        )

        raw_frame = process.stdout.read(width * height * 3)  # Read one frame

        if not raw_frame:
            print("Stream attempted but no frame detected. Reopening listener in 1 second...")
            process.terminate()
            time.sleep(wait_interval)
            continue

        print("Stream detected! Attempting playback...")

        # Convert raw frame to NumPy array
        frame = np.frombuffer(raw_frame, np.uint8).reshape([height, width, 3])

        # Display the frame
        cv2.imshow("RTMP Stream", frame)

        # Main loop to keep playing frames
        while True:
            raw_frame = process.stdout.read(width * height * 3)
            if not raw_frame:
                print("Stream lost. Exiting...")
                break

            frame = np.frombuffer(raw_frame, np.uint8).reshape([height, width, 3])
            cv2.imshow("RTMP Stream", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):  # Quit if 'q' is pressed
                print("Stream manually stopped.")
                break

        process.terminate()
        break  # Exit the main loop when streaming stops

    except Exception as e:
        print(f"Error: {e}")
        process.terminate()
        break  # Exit the script on failure

# Cleanup
cv2.destroyAllWindows()
print("RTMP stream closed.")
