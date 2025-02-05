# RTMP Webcam Streaming & Server

This repository contains two scripts:  
1. **Webcam Streaming Script** – Uses FFmpeg to stream a webcam feed with audio.  
2. **RTMP Server Script** – A minimal server that listens for incoming RTMP streams and handles the handshake process.  

## 🚀 Webcam Streaming Script (Using FFmpeg)
This script launches a webcam stream with audio and provides configuration options for video and audio device selection.

### **Features**
- Lists available video and audio devices upon launch.
- Highlights the configured devices in **yellow** if they match the system's available devices.
- Streams video via **FFmpeg**.
- Responds to the `q` key to stop the stream.
- Displays **metadata** showing video and audio stream information.

### **Usage**
1. Modify the **configuration settings** at the top of the script to select the correct **video** and **audio** devices.
2. Run the script:
   ```sh
   python webcam_stream.py
