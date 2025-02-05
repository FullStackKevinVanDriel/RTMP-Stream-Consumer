# RTMP Webcam Streaming & Server

This repository provides two functionalities, each handled by a separate script:
1. **Main Streaming Script** (`main.py`) – Uses FFmpeg to stream a webcam feed with audio.
2. **RTMP Server** (`RTMPServer.py`) – A minimal server that listens for incoming RTMP streams and handles the handshake process.

## 🚀 Main Streaming Script (`main.py`)
This script launches a **webcam stream with audio** and provides configurable options for selecting video and audio devices.

### **Features**
- Lists available video and audio devices upon launch.
- Highlights the configured devices in **yellow** if they match available system devices.
- Streams video via **FFmpeg**.
- Responds to the `q` key to stop the stream.
- Displays **metadata** with video and audio stream information.

### **Usage**
1. Modify the **configuration settings** at the top of `main.py` to select the correct **video** and **audio** devices.
2. Run the script:
   ```sh
   python main.py
3. Modify the **configuration settings** at the top of `RTMPServer.py` to select the correct **video** and **audio** devices, and whether to launch FFMpeg automatically
4.Run the script:
   ```sh
   python RTMPServer.py
