import asyncio
import struct
import logging
import os
import time
import subprocess

logging.basicConfig(level=logging.DEBUG)

# Configure Video/Audio Sources; let FFMpeg automatically launch stream or use OBS Studio seperately
video_device = "1080P Pro Stream"
audio_device = "Microphone (1080P Pro Stream)"
launchStreamWithFFMPEG = False

# RTMP Server Settings
localhost = "127.0.0.1"
localport = 1935
EXPECTED_STREAM_KEY = "liv"  # Replace "test" with your desired key


class RTMPServer:

    def __init__(self, host=localhost, port=localport):
        self.host = host
        self.port = port
        self.streams = {}
        self.chunk_size = 128

    def launch_audiovideostream(self):
        # Define RTMP URL and device settings
        rtmp_url = f"rtmp://{localhost}:{localport}/live"
        width, height = 1280, 720

        # Construct the FFmpeg command
        ffmpeg_command = [
            "ffmpeg",
            "-f",
            "dshow",
            "-rtbufsize",
            "100M",
            "-framerate",
            "30",
            "-video_size",
            f"{width}x{height}",
            "-i",
            f"video={video_device}",
            "-f",
            "dshow",
            "-i",
            f"audio={audio_device}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            "2000k",
            "-maxrate",
            "2000k",
            "-bufsize",
            "4000k",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "60",
            "-keyint_min",
            "30",
            "-sc_threshold",
            "0",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-f",
            "flv",
            rtmp_url,
        ]

        # Print and launch the FFmpeg process
        print(f"Starting webcam stream to {rtmp_url}...")

        process = subprocess.Popen(
            ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8,
        )

    async def handle_client(self, reader, writer):
        logging.info("New client connected.")

        # Step 1: Perform RTMP Handshake
        await self.rtmp_handshake(reader, writer)

        # Step 2: Process RTMP messages continuously
        while True:
            try:
                # Read RTMP Chunk Basic Header (1 byte)
                basic_header = await reader.read(1)
                print("New data just came in")
                if not basic_header:
                    logging.info("Client disconnected.")
                    break

                chunk_format = (basic_header[0] & 0b11000000) >> 6
                chunk_stream_id = basic_header[0] & 0b00111111

                if chunk_stream_id == 0:
                    # 2-byte chunk stream ID
                    chunk_stream_id = 64 + (await reader.read(1))[0]
                elif chunk_stream_id == 1:
                    # 3-byte chunk stream ID
                    chunk_stream_id = (
                        64 + (await reader.read(1))[0] + (await reader.read(1))[0] * 256
                    )

                logging.debug(
                    f"Chunk Format: {chunk_format}, Chunk Stream ID: {chunk_stream_id}"
                )

                # Read the message header based on the format
                if chunk_format == 0:
                    # 11-byte header
                    message_header = await reader.read(11)
                    if not message_header:
                        logging.error("Message header not received.")
                        break
                    timestamp = int.from_bytes(message_header[0:3], "big")
                    payload_size = int.from_bytes(message_header[3:6], "big")
                    msg_type = message_header[6:7]
                    stream_id = int.from_bytes(message_header[7:11], "little")
                elif chunk_format == 1:
                    # 7-byte header
                    message_header = await reader.read(7)
                    if not message_header:
                        logging.error("Message header not received.")
                        break
                    timestamp = int.from_bytes(message_header[0:3], "big")
                    payload_size = int.from_bytes(message_header[3:6], "big")
                    msg_type = message_header[6:7]
                    stream_id = None  # Stream ID is not present in this format
                elif chunk_format == 2:
                    # 3-byte header
                    message_header = await reader.read(3)
                    if not message_header:
                        logging.error("Message header not received.")
                        break
                    timestamp = int.from_bytes(message_header[0:3], "big")
                    payload_size = None  # Payload size is not present in this format
                    msg_type = None  # Message type is not present in this format
                    stream_id = None  # Stream ID is not present in this format
                elif chunk_format == 3:
                    # 0-byte header (no header)
                    timestamp = None
                    payload_size = None
                    msg_type = None
                    stream_id = None

                logging.debug(
                    f"RTMP Message Type: {msg_type.hex() if msg_type else 'N/A'}, Payload Size: {payload_size}, Stream ID: {stream_id}"
                )

                # Read Payload Data
                if payload_size:
                    payload = b""
                    while len(payload) < payload_size:
                        chunk = await reader.read(
                            min(self.chunk_size, payload_size - len(payload))
                        )
                        if not chunk:
                            logging.warning("Payload missing.")
                            break
                        payload += chunk

                    logging.debug(f"Received payload: {payload.hex()}")

                    # Handle Different RTMP Messages
                    if (
                        msg_type == b"\x14"
                    ):  # AMF Command (connect, publish, play, etc.)
                        await self.handle_amf_command(payload, writer)
                    elif msg_type == b"\x09":  # Video Data
                        await self.handle_video_packet(payload)
                    elif msg_type == b"\x08":  # Audio Data
                        await self.handle_audio_packet(payload)
                    elif msg_type == b"\x01":  # Unknown message type
                        # Handle RTMP message type 01 (Set Chunk Size)
                        if len(payload) >= 4:
                            chunk_size = struct.unpack(">I", payload[:4])[0]
                            self.chunk_size = chunk_size
                            logging.debug(f"Set Chunk Size to: {chunk_size}")
                        else:
                            logging.warning("Invalid Set Chunk Size message received.")
                    else:
                        logging.warning(
                            f"Unhandled RTMP message type: {msg_type.hex() if msg_type else 'N/A'}"
                        )

            except Exception as e:
                logging.error(f"Error handling client: {e}")
                break

    def generate_s1(self):
        """Generates a valid S1 packet with a random payload"""
        time = struct.pack(">I", 0)  # Zero timestamp
        zero = struct.pack(">I", 0)  # Zero
        payload = os.urandom(1528)  # Random payload
        return time + zero + payload

    async def rtmp_handshake(self, reader, writer):
        """Handles the RTMP handshake process correctly for OBS & FFmpeg."""
        RTMP_HANDSHAKE_SIZE = 1536
        try:
            logging.info("Waiting for C0...")

            # Step 1: Read C0 (1 byte)
            c0 = await reader.readexactly(1)
            if c0 != b"\x03":  # RTMP version 3 expected
                logging.error("Invalid RTMP version: %s", c0)
                return

            logging.info("Received C0 (RTMP version: %s)", c0.hex())

            # Step 2: Read C1 (1536 bytes)
            c1 = await reader.readexactly(1536)
            logging.info("Received C1 (1536 bytes)")

            # Send S0 + S1
            # Step 2: Send S0+S1+S2
            s0 = b"\x03"  # RTMP version 3
            s1 = self.generate_s1()
            s2 = c1  # S2 is just echoing back C1
            writer.write(s0 + s1 + s2)
            await writer.drain()
            logging.info("Sent S0+S1+S2")

            # Receive C2
            c2 = await reader.readexactly(1536)
            logging.info("Received C2.")

            # Send S2
            writer.write(s1)  # S2 is a copy of S1
            await writer.drain()
            logging.info("Sent S2.")

            logging.info("RTMP Handshake complete -- SUCCESS.")

            return True  # Handshake success

        except asyncio.TimeoutError:
            logging.error("Handshake error: Timeout while waiting for client response.")
        except Exception as e:
            logging.error(f"Error during RTMP handshake: {e}")
            writer.close()  # Close the connection after handshake error

    async def handle_video_packet(self, payload):
        """
        Handles RTMP video packets.
        """
        if len(payload) < 1:
            logging.warning("Received empty video packet.")
            return

        frame_type = (payload[0] & 0xF0) >> 4  # First 4 bits = frame type
        codec_id = payload[0] & 0x0F  # Last 4 bits = codec ID

        frame_types = {
            1: "Keyframe",
            2: "Inter frame",
            3: "Disposable",
            4: "Generated",
            5: "Command",
        }
        codec_types = {7: "H.264", 2: "Sorenson H.263", 4: "VP6"}

        frame_type_str = frame_types.get(frame_type, "Unknown")
        codec_str = codec_types.get(codec_id, f"Unknown ({codec_id})")

        logging.info(f"Received Video Packet: {len(payload)} bytes")
        logging.info(f"Frame Type: {frame_type_str}, Codec: {codec_str}")

        # Example: Extract AVC sequence header (if applicable)
        if codec_id == 7 and len(payload) > 1:
            avc_packet_type = payload[1]
            if avc_packet_type == 0:
                logging.info("AVC Sequence Header detected.")

    async def handle_audio_packet(self, payload):
        """
        Handles RTMP audio packets.
        """
        if len(payload) < 1:
            logging.warning("Received empty audio packet.")
            return

        sound_format = (payload[0] & 0xF0) >> 4  # First 4 bits = Sound format
        sound_rate = (payload[0] & 0x0C) >> 2  # Bits 2-3 = Sampling rate
        sound_size = (
            payload[0] & 0x02
        ) >> 1  # Bit 1 = Sample size (0: 8-bit, 1: 16-bit)
        sound_type = payload[0] & 0x01  # Bit 0 = Mono (0) or Stereo (1)

        sound_formats = {10: "AAC", 0: "Linear PCM", 1: "ADPCM", 2: "MP3", 11: "Speex"}
        sample_rates = {0: "5.5 kHz", 1: "11 kHz", 2: "22 kHz", 3: "44 kHz"}

        sound_format_str = sound_formats.get(sound_format, f"Unknown ({sound_format})")
        sample_rate_str = sample_rates.get(sound_rate, "Unknown")

        logging.info(f"Received Audio Packet: {len(payload)} bytes")
        logging.info(
            f"Format: {sound_format_str}, Sample Rate: {sample_rate_str}, "
            f"Size: {'16-bit' if sound_size else '8-bit'}, Channels: {'Stereo' if sound_type else 'Mono'}"
        )

        # Example: Detect AAC sequence header
        if sound_format == 10 and len(payload) > 1:
            aac_packet_type = payload[1]
            if aac_packet_type == 0:
                logging.info("AAC Sequence Header detected.")

    def decode_amf_command(self, payload):
        """Decodes an AMF command payload."""
        decoded_values = self.decode_amf_payload(payload)
        if not decoded_values:
            return None, None, None

        command_name = decoded_values[0] if len(decoded_values) > 0 else None
        transaction_id = decoded_values[1] if len(decoded_values) > 1 else None
        command_object = decoded_values[2] if len(decoded_values) > 2 else {}

        return command_name, transaction_id, command_object

    async def handle_amf_command(self, payload, writer):
        """
        Parses and handles AMF commands from clients.
        """
        try:
            logging.debug(f"AMF Command Payload: {payload.hex()}")

            # Decode AMF
            command_name, transaction_id, command_object = self.decode_amf_command(
                payload
            )
            if command_name:
                logging.info(f"AMF Command Received: {command_name}")

                if command_name == "connect":
                    await self.handle_connect(transaction_id, command_object, writer)
                elif command_name == "createStream":
                    await self.handle_create_stream(writer)
                elif command_name == "publish":
                    await self.handle_publish(
                        [command_name, transaction_id, command_object], writer
                    )
                elif command_name == "play":
                    await self.handle_play(
                        [command_name, transaction_id, command_object], writer
                    )
                else:
                    logging.warning(f"Unknown AMF Command: {command_name}")
            else:
                logging.warning("No valid AMF command found in payload.")

        except Exception as e:
            logging.error(f"Error parsing AMF command: {e}")

    async def handle_create_stream(self, transaction_id, writer):
        """
        Responds to RTMP createStream request properly.
        """
        stream_id = 1  # Default to stream ID 1
        self.streams[stream_id] = None

        response = (
            b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x05"  # RTMP Header
            + struct.pack(">I", stream_id)  # Stream ID
        )
        writer.write(response)
        await writer.drain()
        logging.info(f"Stream {stream_id} created.")

    async def handle_publish(self, decoded_values, writer):
        """
        Handles RTMP 'publish' requests properly.
        """
        try:
            if len(decoded_values) < 3:
                logging.error("Invalid publish command format.")
                return

            # Extract the application and stream key
            app_name = decoded_values[1] if len(decoded_values) > 1 else "default"
            stream_key = decoded_values[2]  # Third element is the actual stream key

            logging.info(f"Publishing stream: app={app_name}, key={stream_key}")

            self.streams[stream_key] = {"app": app_name}  # Store stream info

            # Respond to the client with NetStream.Publish.Start
            response = (
                b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x06"  # RTMP Header
                b"\x00\x03\x00\x00\x00\x00\x00\x00"  # Message Body (Success Response)
            )
            writer.write(response)
            await writer.drain()

            logging.info(
                f"Stream {stream_key} started successfully under app {app_name}."
            )

        except Exception as e:
            logging.error(f"Error handling publish request: {e}")

    def decode_amf_payload(self, payload):
        """
        Decodes multiple AMF encoded values from the payload.
        Handles AMF strings, numbers, booleans, and objects properly.
        """
        decoded_values = []
        index = 0

        while index < len(payload):
            try:
                if index >= len(payload):  # Prevent out-of-bounds access
                    logging.warning("AMF payload out of range before reading type")
                    break

                amf_type = payload[index]
                index += 1

                logging.debug(f"Decoding AMF type: {amf_type} at index: {index-1}")

                if amf_type == 0x02:  # AMF string
                    if index + 2 > len(payload):
                        logging.warning("AMF string out of range")
                        break
                    str_length = struct.unpack(">H", payload[index : index + 2])[0]
                    index += 2
                    if index + str_length > len(payload):
                        logging.warning("AMF string out of range")
                        break
                    amf_string = payload[index : index + str_length].decode(
                        "utf-8", errors="ignore"
                    )
                    decoded_values.append(amf_string)
                    index += str_length

                elif amf_type == 0x00:  # AMF number
                    if index + 8 > len(payload):
                        logging.warning("AMF number out of range")
                        break
                    amf_number = struct.unpack(">d", payload[index : index + 8])[0]
                    decoded_values.append(amf_number)
                    index += 8

                elif amf_type == 0x01:  # AMF boolean
                    if index >= len(payload):
                        logging.warning("AMF boolean out of range")
                        break
                    amf_boolean = bool(payload[index])
                    decoded_values.append(amf_boolean)
                    index += 1

                elif amf_type == 0x03:  # AMF object
                    amf_object, new_index = self.decode_amf_object(payload, index)
                    decoded_values.append(amf_object)
                    index = new_index

                elif amf_type == 0x05:  # AMF null
                    decoded_values.append(None)

                elif amf_type == 0x09:  # Object end marker
                    break

                else:
                    logging.warning(f"Unhandled AMF type: {amf_type}")
                    break

            except (struct.error, UnicodeDecodeError, IndexError) as e:
                logging.error(f"Failed to decode AMF data at index {index}: {e}")
                logging.debug(f"Data causing error: {payload[index:].hex()}")
                break

        return decoded_values

    def decode_amf_object(self, payload, start_index):
        """
        Safely decodes an AMF object, handling edge cases properly.
        """
        amf_object = {}
        index = start_index

        while index < len(payload):
            try:
                # Detect Object End Marker (0x09)
                if payload[index] == 0x09:
                    logging.debug("AMF Object End Marker detected.")
                    index += 1
                    break

                # Ensure enough data for property name length (2 bytes)
                if index + 2 > len(payload):
                    logging.warning(
                        "AMF object property name length out of range (truncated object)"
                    )
                    logging.debug(f"Remaining payload: {payload[index:].hex()}")
                    break

                str_length = struct.unpack(">H", payload[index : index + 2])[0]
                index += 2

                # Ensure string length does not exceed available data
                if index + str_length > len(payload):
                    logging.warning("AMF object property name length out of range")
                    logging.debug(f"Remaining payload: {payload[index:].hex()}")
                    break

                property_name = payload[index : index + str_length].decode(
                    "utf-8", errors="ignore"
                )
                index += str_length

                logging.debug(f"Decoded property name: {property_name}")

                # Ensure at least 1 byte left for type information
                if index >= len(payload):
                    logging.warning("AMF object truncated before reading type.")
                    break

                amf_type = payload[index]
                index += 1

                logging.debug(f"Property type: {amf_type}")

                # Read property value based on its type
                if amf_type == 0x02:  # AMF string
                    if index + 2 > len(payload):
                        logging.warning(
                            f"AMF string property '{property_name}' out of range"
                        )
                        break
                    str_length = struct.unpack(">H", payload[index : index + 2])[0]
                    index += 2
                    if index + str_length > len(payload):
                        logging.warning(f"AMF string '{property_name}' out of range")
                        break
                    property_value = payload[index : index + str_length].decode(
                        "utf-8", errors="ignore"
                    )
                    index += str_length

                elif amf_type == 0x00:  # AMF number
                    if index + 8 > len(payload):
                        logging.warning(
                            f"AMF number property '{property_name}' out of range"
                        )
                        break
                    property_value = struct.unpack(">d", payload[index : index + 8])[0]
                    index += 8

                elif amf_type == 0x01:  # AMF boolean
                    if index >= len(payload):
                        logging.warning(
                            f"AMF boolean property '{property_name}' out of range"
                        )
                        break
                    property_value = bool(payload[index])
                    index += 1

                elif amf_type == 0x03:  # Nested AMF object
                    property_value, index = self.decode_amf_object(payload, index)

                elif amf_type == 0x05:  # AMF null
                    property_value = None

                elif amf_type == 0x09:  # Object end marker
                    logging.debug(f"AMF Object End detected at index {index}")
                    break

                else:
                    logging.warning(f"Unhandled AMF type in object: {amf_type}")
                    break

                amf_object[property_name] = property_value
                print("amf_object", amf_object)

            except (struct.error, UnicodeDecodeError, IndexError) as e:
                logging.error(f"Failed to decode AMF object at index {index}: {e}")
                logging.debug(f"Data causing error: {payload[index:].hex()}")
                break

        return amf_object, index

    async def handle_connect(self, transaction_id, command_object, writer):
        """
        Responds to RTMP 'connect' requests with the correct response format.
        """
        try:
            # Extract the application (e.g., "live") and tcUrl (e.g., "rtmp://127.0.0.1:1935/live/test")
            app_name = command_object.get("app", "default")
            tc_url = command_object.get("tcUrl", "rtmp://127.0.0.1:1935/")

            # Extract the stream key from the tcUrl (last part of the URL)
            stream_key = tc_url.split("/")[-1]

            logging.info(
                f"Client connected to application: {app_name}, stream key: {stream_key}"
            )

            # Validate the stream key
            if stream_key != EXPECTED_STREAM_KEY:
                logging.error(
                    f"Invalid stream key: {stream_key}. Expected: {EXPECTED_STREAM_KEY}"
                )
                writer.close()  # Close connection if the stream key is invalid
                return

            # Construct the response_body
            response_body = (
                b"\x02"
                + struct.pack(">H", len("_result"))
                + b"_result"
                + b"\x00"
                + struct.pack(">d", transaction_id)
                + b"\x03"
                + b"\x00\x06"
                + b"fmsVer"
                + b"\x02"
                + struct.pack(">H", len("FMS/3,5,3,888"))
                + b"FMS/3,5,3,888"
                + b"\x00\x0B"
                + b"capabilities"
                + b"\x00"
                + struct.pack(">d", 31.0)
                + b"\x00\x05"
                + b"tcUrl"
                + b"\x02"
                + struct.pack(">H", len(tc_url))
                + tc_url.encode("utf-8")
                + b"\x00\x00\x09"
                + b"\x03"
                + b"\x00\x05"
                + b"level"
                + b"\x02"
                + struct.pack(">H", len("status"))
                + b"status"
                + b"\x00\x04"
                + b"code"
                + b"\x02"
                + struct.pack(">H", len("NetConnection.Connect.Success"))
                + b"NetConnection.Connect.Success"
                + b"\x00\x0B"
                + b"description"
                + b"\x02"
                + struct.pack(">H", len("Connection succeeded."))
                + b"Connection succeeded."
                + b"\x00\x0E"
                + b"objectEncoding"
                + b"\x00"
                + struct.pack(">d", 3.0)
                + b"\x00\x00\x09"
            )

            # Construct the RTMP header
            response_header = (
                b"\x02"
                + b"\x00\x00\x00"
                + struct.pack(">I", len(response_body))[1:4]
                + b"\x14"
                + b"\x00\x00\x00\x00"
            )

            response = response_header + response_body
            logging.info(f"Sending RTMP response: {response.hex()}")

            # Send the response
            writer.write(response)
            await writer.drain()
            logging.info("Sent RTMP connect response.")

            # Send the createStream response
            # await self.handle_create_stream(transaction_id, writer)

            # Keep connection open for OBS to process
            # await asyncio.sleep(2)

        except Exception as e:
            logging.error(f"Error handling RTMP connect: {e}")
            writer.close()

    async def start(self):
        """Starts the RTMP server."""
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"RTMP Server listening on {self.host}:{self.port}")

        # Launch the audio/video stream
        if launchStreamWithFFMPEG == True:
            self.launch_audiovideostream()

        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    rtmp_server = RTMPServer()
    asyncio.run(rtmp_server.start())
