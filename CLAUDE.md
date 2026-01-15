# RTMP-Stream-Consumer

RTMP webcam streaming and server implementation using Python and FFmpeg.

## Key Commands

```bash
# Run webcam streaming
python main.py

# Run RTMP server
python RTMPServer.py
```

## Important Files

- `main.py` - Webcam streaming script (configure devices/RTMP URL at top)
- `RTMPServer.py` - RTMP server implementation
- `.vscode/` - VS Code configuration

## Features

- Lists available video/audio devices
- Streams webcam via FFmpeg
- RTMP server with handshake support
- Optional auto-launch FFmpeg on connection

## Configuration

Edit settings at top of each script:
- Video/audio device selection
- RTMP URL for streaming
- Auto-launch FFmpeg option

## Dependencies

- Python 3
- FFmpeg (must be installed and in PATH)
