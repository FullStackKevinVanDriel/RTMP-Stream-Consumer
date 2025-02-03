import subprocess
import json

def get_stream_info(rtmp_url):
    # Run ffprobe to get stream information in JSON format
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=index,codec_type,codec_name,width,height,sample_rate,pix_fmt', '-of', 'json', rtmp_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return json.loads(result.stdout)

rtmp_url = "rtmp://127.0.0.1:1935/live/webcam"
stream_info = get_stream_info(rtmp_url)

# Display stream information
for stream in stream_info['streams']:
    print(f"Stream Index: {stream.get('index')}")
    print(f"Codec Type: {stream.get('codec_type')}")
    print(f"Codec Name: {stream.get('codec_name')}")
    if stream.get('codec_type') == 'video':
        print(f"Resolution: {stream.get('width')}x{stream.get('height')}")
        print(f"Pixel Format: {stream.get('pix_fmt')}")
    elif stream.get('codec_type') == 'audio':
        print(f"Sample Rate: {stream.get('sample_rate')}")
    print()
