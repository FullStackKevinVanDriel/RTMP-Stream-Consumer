import asyncio
import struct
import logging
import os
import subprocess

logging.basicConfig(level=logging.DEBUG)

# Configure Video/Audio Sources; let FFMpeg automatically launch stream or use OBS Studio seperately
video_device = "1080P Pro Stream"
audio_device = "Microphone (1080P Pro Stream)"
launchStreamWithFFMPEG = False

# RTMP Server Settings
localhost = "127.0.0.1"
localport = 1935
APPLICATION = "live"
SERVERLINKANDPORT = f"rtmp://{localhost}:{localport}"
SERVERLINKANDPORTANDAPP = f"rtmp://{localhost}:{localport}/{APPLICATION}"


# RTMP Protocol Version
RTMP_VERSION = 3

# RTMP Handshake Constants
RTMP_HANDSHAKE_SIZE = 1536  # Standard RTMP handshake size

# RTMP Chunk Types
RTMP_CHUNK_TYPE_0 = 0  # 11-byte header
RTMP_CHUNK_TYPE_1 = 1  # 7-byte header
RTMP_CHUNK_TYPE_2 = 2  # 3-byte header
RTMP_CHUNK_TYPE_3 = 3  # 0-byte header (reuses previous)

# RTMP Message Types
RTMP_MSG_TYPE_COMMAND = 0x14  # AMF Command (connect, play, etc.)
RTMP_MSG_TYPE_AUDIO = 0x08  # Audio packet
RTMP_MSG_TYPE_VIDEO = 0x09  # Video packet
RTMP_MSG_TYPE_SET_CHUNK_SIZE = 0x01  # Set chunk size

# Default RTMP Chunk Size (modifiable by client)
DEFAULT_CHUNK_SIZE = 128

# Other Constants
AMF_STRING_HEADER_SIZE = 2  # AMF Strings have a 2-byte length header
AMF_NUMBER_SIZE = 8  # AMF Numbers (doubles) are 8 bytes
AMF_BOOLEAN_SIZE = 1  # AMF Booleans are 1 byte

# AMF Data Type Constants
AMF_TYPE_NUMBER = 0x00
AMF_TYPE_BOOLEAN = 0x01
AMF_TYPE_STRING = 0x02
AMF_TYPE_OBJECT = 0x03
AMF_TYPE_NULL = 0x05
AMF_TYPE_OBJECT_END = 0x09

# Other Constants
AMF_STRING_HEADER_SIZE = 2  # AMF Strings have a 2-byte length header
AMF_NUMBER_SIZE = 8  # AMF Numbers (doubles) are 8 bytes
AMF_BOOLEAN_SIZE = 1  # AMF Booleans are 1 byte
AMF_PROPERTY_NAME_SIZE = 2  # Property names have a 2-byte length prefix

# RTMP Message Types
RTMP_MSG_TYPE_COMMAND = 0x14  # AMF Command (connect, play, etc.)
RTMP_MSG_TYPE_AUDIO = 0x08  # Audio packet
RTMP_MSG_TYPE_VIDEO = 0x09  # Video packet
RTMP_MSG_TYPE_SET_CHUNK_SIZE = 0x01  # Set chunk size

# RTMP Payload Size Constants
RTMP_PAYLOAD_HEADER_11_BYTE = 11
RTMP_PAYLOAD_HEADER_7_BYTE = 7
RTMP_PAYLOAD_HEADER_3_BYTE = 3

# Define meaningful RTMP constants
CHUNK_STREAM_ID_2_BYTE = 0
CHUNK_STREAM_ID_3_BYTE = 1
CHUNK_FORMAT_FULL_HEADER = 0
CHUNK_FORMAT_TIMESTAMP_ONLY = 1
CHUNK_FORMAT_NO_STREAM_ID = 2
CHUNK_FORMAT_NO_HEADER = 3
MIN_CHUNK_SIZE = 1
MAX_CHUNK_SIZE = 65536
INVALID_BYTE = b"\xc3"  # Problematic byte in chunk splitting

VALID_RTMP_TYPES = {0x01, 0x08, 0x09, 0x14}


class RTMPServer:

    def __init__(self, host=localhost, port=localport):
        self.host = host
        self.port = port
        self.streams = {}
        self.chunk_size = DEFAULT_CHUNK_SIZE

    def launch_audiovideostream(self):
        # Define RTMP URL and device settings
        rtmp_url = f"rtmp://{localhost}:{localport}/{APPLICATION}"
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
        """Handles incoming RTMP clients."""
        logging.info("New client connected.")

        # Perform RTMP Handshake
        if not await self.rtmp_handshake(reader, writer):
            logging.error("Handshake failed. Closing connection.")
            writer.close()
            await writer.wait_closed()
            return

        # Variables to track previous chunk headers (for Formats 1, 2, 3)
        previous_timestamp = None
        previous_payload_size = None
        previous_msg_type = None
        previous_stream_id = None

        while True:
            try:
                print("reading data again...")
                # Read RTMP Basic Header (1 byte)
                basic_header = await reader.read(1)
                print("trying to analyze data")
                if not basic_header:
                    logging.info("Client disconnected.")
                    break
                print("data is read")
                chunk_format = (basic_header[0] & 0b11000000) >> 6
                chunk_stream_id = basic_header[0] & 0b00111111

                # Handle Extended Chunk Stream ID (if needed)
                if chunk_stream_id == CHUNK_STREAM_ID_2_BYTE:
                    extra_byte = await reader.read(1)
                    if not extra_byte:
                        logging.error("Failed to read extended chunk stream ID.")
                        break
                    chunk_stream_id = 64 + extra_byte[0]

                elif chunk_stream_id == CHUNK_STREAM_ID_3_BYTE:
                    extra_bytes = await reader.read(2)
                    if len(extra_bytes) < 2:
                        logging.error("Failed to read extended chunk stream ID.")
                        break
                    chunk_stream_id = 64 + extra_bytes[0] + (extra_bytes[1] << 8)

                logging.debug(
                    f"Chunk Format: {chunk_format}, Chunk Stream ID: {chunk_stream_id}"
                )

                # Read Message Header based on Chunk Format
                if chunk_format == CHUNK_FORMAT_FULL_HEADER:
                    message_header = await reader.read(11)
                    if len(message_header) < 11:
                        logging.error("Incomplete message header.")
                        break
                    timestamp = int.from_bytes(message_header[0:3], "big")
                    payload_size = int.from_bytes(message_header[3:6], "big")
                    msg_type = message_header[6]
                    stream_id = int.from_bytes(message_header[7:11], "little")

                elif chunk_format == CHUNK_FORMAT_TIMESTAMP_ONLY:
                    message_header = await reader.read(7)
                    if len(message_header) < 7:
                        logging.error("Incomplete message header.")
                        break
                    timestamp = int.from_bytes(message_header[0:3], "big")
                    payload_size = int.from_bytes(message_header[3:6], "big")
                    msg_type = message_header[6]
                    stream_id = previous_stream_id  # No stream ID in this format

                elif chunk_format == CHUNK_FORMAT_NO_STREAM_ID:
                    message_header = await reader.read(3)
                    if len(message_header) < 3:
                        logging.error("Incomplete message header.")
                        break
                    timestamp = int.from_bytes(message_header[0:3], "big")
                    payload_size = previous_payload_size
                    msg_type = previous_msg_type
                    stream_id = previous_stream_id

                elif chunk_format == CHUNK_FORMAT_NO_HEADER:
                    timestamp = previous_timestamp
                    payload_size = previous_payload_size
                    msg_type = previous_msg_type
                    stream_id = previous_stream_id

                # ✅ Drop Invalid RTMP Message Types
                VALID_RTMP_MSG_TYPES = {
                    RTMP_MSG_TYPE_COMMAND,
                    RTMP_MSG_TYPE_VIDEO,
                    RTMP_MSG_TYPE_AUDIO,
                    RTMP_MSG_TYPE_SET_CHUNK_SIZE,
                }

                if msg_type not in VALID_RTMP_MSG_TYPES:
                    logging.warning(
                        f"🚨 Dropping unknown RTMP message type: {hex(msg_type)}"
                    )
                    continue  # Skip bad packets

                # Validate Payload Size Before Continuing
                if payload_size is None or payload_size <= 0:
                    logging.error(f"Invalid payload size: {payload_size}. Skipping.")
                    continue

                # Store previous values for next chunks
                previous_timestamp = timestamp
                previous_payload_size = payload_size
                previous_msg_type = msg_type
                previous_stream_id = stream_id

                logging.debug(
                    f"RTMP Message Type: {hex(msg_type)}, Payload Size: {payload_size}, Stream ID: {stream_id}"
                )

                # Read Full Payload in Chunks
                payload = b""
                remaining_size = payload_size
                while remaining_size > 0:
                    chunk = await reader.read(min(self.chunk_size, remaining_size))
                    if not chunk:
                        logging.warning(
                            f"Incomplete payload received. Read {len(payload)} / {payload_size}"
                        )
                        break

                    # ✅ **Filter out problematic `\xc3` bytes to fix tcUrl**
                    if INVALID_BYTE in chunk:
                        logging.warning(
                            f"Removing invalid byte from chunk: {chunk.hex()}"
                        )
                        chunk = chunk.replace(INVALID_BYTE, b"")

                    payload += chunk
                    remaining_size -= len(chunk)

                # Verify Full Payload Read
                if len(payload) != payload_size:
                    logging.error(
                        f"RTMP packet size mismatch! Expected {payload_size}, received {len(payload)}"
                    )

                # Debugging: Print raw bytes before AMF decoding
                logging.debug(f"Received full RTMP payload (Hex): {payload.hex()}")

                # Handle RTMP Messages
                if msg_type == RTMP_MSG_TYPE_COMMAND:
                    await self.handle_amf_command(payload, writer)
                elif msg_type == RTMP_MSG_TYPE_VIDEO:
                    print("should process video packet")
                    await self.handle_video_packet(payload)
                elif msg_type == RTMP_MSG_TYPE_AUDIO:
                    print("should process audio package")
                    await self.handle_audio_packet(payload)
                elif msg_type == RTMP_MSG_TYPE_SET_CHUNK_SIZE:
                    if len(payload) >= 4:
                        new_chunk_size = struct.unpack(">I", payload[:4])[0]
                        if MIN_CHUNK_SIZE <= new_chunk_size <= MAX_CHUNK_SIZE:
                            logging.info(
                                f"Client requested chunk size: {new_chunk_size}"
                            )
                            self.chunk_size = new_chunk_size
                        else:
                            logging.warning(f"Invalid chunk size: {new_chunk_size}")
                    else:
                        logging.warning("Invalid Set Chunk Size message received.")
                else:
                    logging.warning(f"Unhandled RTMP message type: {hex(msg_type)}")

            except asyncio.IncompleteReadError:
                logging.warning("Client disconnected abruptly.")
                break
            except ConnectionResetError:
                logging.warning("Client connection forcibly closed.")
                break
            except Exception as e:
                logging.exception(f"Error handling client: {e}")
                break

    def generate_s1(self):
        """Generates a valid S1 packet with a random payload."""
        time = struct.pack(">I", 0)  # Zero timestamp
        zero = struct.pack(">I", 0)  # Zero
        payload = os.urandom(1528)  # Random payload
        return time + zero + payload

    async def rtmp_handshake(self, reader, writer):
        """Handles the RTMP handshake process correctly for OBS & FFmpeg."""

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

            # Generate S0 + S1 + S2
            s0 = b"\x03"  # RTMP version 3
            s1 = self.generate_s1()
            s2 = c1  # S2 must be an exact copy of C1

            # Send S0+S1+S2 in one go (fixes the double-write issue)
            writer.write(s0 + s1 + s2)
            await writer.drain()
            logging.info("✅ Sent S0+S1+S2")

            # Step 3: Receive C2 (1536 bytes)
            c2 = await reader.readexactly(1536)
            logging.info("✅ Received C2.")

            # Handshake complete
            logging.info("🚀 RTMP Handshake complete -- SUCCESS.")

            return True

        except Exception as e:
            logging.error(f"❌ RTMP Handshake failed: {e}")
            writer.close()

        except asyncio.TimeoutError:
            logging.error("Handshake error: Timeout while waiting for client response.")
        except Exception as e:
            logging.error(f"Error during RTMP handshake: {e}")
            writer.close()  # Close the connection after handshake error

    def decode_amf_command(self, payload):
        """Decodes an AMF command payload."""
        decoded_values = self.decode_amf_payload(payload)
        if not decoded_values:
            return None, None, None

        command_name = decoded_values[0] if len(decoded_values) > 0 else None
        transaction_id = decoded_values[1] if len(decoded_values) > 1 else None
        command_object = decoded_values[2] if len(decoded_values) > 2 else {}

        return command_name, transaction_id, command_object

    def decode_amf_string(self, payload, index):
        """
        Safely decodes an AMF string, ensuring proper length extraction and UTF-8 recovery.
        """
        if index + AMF_STRING_HEADER_SIZE > len(payload):
            logging.warning("AMF string out of range")
            return None, index

        # Extract string length (2 bytes)
        str_length = struct.unpack(
            ">H", payload[index : index + AMF_STRING_HEADER_SIZE]
        )[0]
        index += AMF_STRING_HEADER_SIZE

        if index + str_length > len(payload):  # Validate string presence
            logging.warning(
                f"AMF string truncated. Expected {str_length} bytes, but got {len(payload) - index}"
            )
            return None, index

        # Extract raw bytes before decoding
        raw_bytes = payload[index : index + str_length]
        index += str_length  # Move index forward

        # First try UTF-8 decoding
        try:
            property_value = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            logging.error(
                f"Invalid UTF-8 sequence in string at index {index - str_length}"
            )

            # Attempt to recover with Latin-1 re-encoding
            try:
                property_value = (
                    raw_bytes.decode("latin-1")
                    .encode("utf-8", errors="ignore")
                    .decode("utf-8")
                )
                logging.debug(
                    f"Recovered string using Latin-1 re-encoding: {property_value}"
                )
            except UnicodeDecodeError:
                logging.error("Failed to recover string with Latin-1 fallback.")
                property_value = ""

        return property_value, index

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

            logging.debug(
                f"Received command: {command_name}, transaction_id: {transaction_id}"
            )

            print(f"Command received: '{command_name}', type: {type(command_name)}")

            if isinstance(command_name, bytes):
                command_name = command_name.decode("utf-8")

            command_name = command_name.strip()

            if command_name:
                logging.info(f"AMF Command Received: {command_name}")

                if command_name == "connect":
                    await self.handle_connect(transaction_id, command_object, writer)
                    # print("should connect")
                if command_name == "publish":
                    print("should publish")
                    await self.handle_publish_response(writer, transaction_id, "test")
                elif command_name == "createStream":
                    print("should create stream")
                    await self.handle_create_stream(transaction_id, writer, payload)
                elif command_name == "FCPublish":
                    print("should publish")
                    print("payload: ", payload)
                    print("command_object", command_object)
                    await self.handle_FCPublish(
                        [command_name, transaction_id, command_object, "webcam"], writer
                    )
                elif command_name == "releaseStream":
                    print("should release stream")
                    await self.handle_release_stream(writer, payload)
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

    async def handle_release_stream(self, writer, amf_payload):
        try:
            if len(amf_payload) > 1 and isinstance(amf_payload[1], (int, float)):
                transaction_id = amf_payload[1]
            else:
                transaction_id = 1.0  # Default to 1.0 if extraction fails

            logging.info(
                f"✅ Handling releaseStream request, transaction_id: {transaction_id}"
            )

            # Build AMF response for releaseStream
            response = (
                self.encode_amf0_string("_result")
                + self.encode_amf0_number(transaction_id)
                + b"\x05"  # AMF NULL
            )

            header = (
                b"\x02"  # Chunk Basic Header
                + b"\x00\x00\x00"  # Timestamp
                + struct.pack(">I", len(response))[
                    -3:
                ]  # Correct 3-byte length encoding
                + b"\x14"  # Message Type ID (AMF Command)
                + b"\x00\x00\x00\x00"  # Message Stream ID
            )

            writer.write(header + response)
            await self.drain_and_sleep(writer)
            logging.info("✅ Sent `_result` for releaseStream.")

        except Exception as e:
            logging.error(f"❌ Error handling releaseStream: {e}")
            writer.close()
            await writer.wait_closed()  # Ensure the writer is properly closed

    async def handle_create_stream(self, transaction_id, writer, amf_payload):
        try:
            # Extract the transaction ID safely
            if len(amf_payload) > 1 and isinstance(amf_payload[1], (int, float)):
                transaction_id = amf_payload[1]
            else:
                transaction_id = 1.0  # Default to 1.0 if extraction fails

            logging.info(
                f"✅ Handling createStream request, transaction_id: {transaction_id}"
            )

            stream_id = 1  # Assign stream ID

            # Build AMF response
            response = (
                self.encode_amf0_string("_result")
                + self.encode_amf0_number(transaction_id)
                + b"\x05"  # AMF NULL
                + self.encode_amf0_number(stream_id)
            )

            header = (
                b"\x02"  # Chunk Basic Header
                + b"\x00\x00\x00"
                + struct.pack(">I", len(response))[1:4]
                + b"\x14"  # Message Type ID for Command Message
                + b"\x00\x00\x00\x00"
            )

            writer.write(header + response)
            await self.drain_and_sleep(writer)
            logging.info(f"✅ Sent `_result` for createStream, Stream ID: {stream_id}.")

        except Exception as e:
            logging.error(f"❌ Error handling createStream: {e}")
            writer.close()

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
                index += 1  # Move past AMF type byte
                property_name = "unknown"

                logging.debug(f"Decoding AMF type: {amf_type} at index: {index - 1}")

                if amf_type == AMF_TYPE_STRING:  # AMF string
                    property_value, index = self.decode_amf_string(payload, index)
                    decoded_values.append(property_value)

                elif amf_type == AMF_TYPE_NUMBER:  # AMF number
                    if index + AMF_NUMBER_SIZE > len(payload):
                        logging.warning("AMF number out of range")
                    else:
                        amf_number = struct.unpack(
                            ">d", payload[index : index + AMF_NUMBER_SIZE]
                        )[0]
                        decoded_values.append(amf_number)
                        index += AMF_NUMBER_SIZE

                elif amf_type == AMF_TYPE_BOOLEAN:  # AMF boolean
                    if index + AMF_BOOLEAN_SIZE > len(payload):
                        logging.warning("AMF boolean out of range")
                    else:
                        amf_boolean = bool(payload[index])
                        decoded_values.append(amf_boolean)
                        index += AMF_BOOLEAN_SIZE

                elif amf_type == AMF_TYPE_OBJECT:  # AMF object
                    amf_object, new_index = self.decode_amf_object(payload, index)
                    decoded_values.append(amf_object)
                    index = new_index

                elif amf_type == AMF_TYPE_NULL:  # AMF null
                    decoded_values.append(None)

                elif amf_type == AMF_TYPE_OBJECT_END:  # Object end marker
                    logging.debug("AMF Object End Marker detected.")
                    break

                else:
                    logging.warning(
                        f"Unhandled AMF type: {hex(amf_type)} at index {index}"
                    )

            except (struct.error, UnicodeDecodeError, IndexError) as e:
                logging.error(f"Failed to decode AMF data at index {index}: {e}")
                logging.debug(f"Data causing error: {payload[index:].hex()}")
                break

        return decoded_values

    def decode_amf_object(self, payload, start_index):
        """
        Decodes an AMF0 object from an RTMP message payload.
        Returns a dictionary of key-value pairs.
        """
        amf_object = {}
        index = start_index

        while index < len(payload):
            try:
                if index + AMF_STRING_HEADER_SIZE > len(payload):
                    logging.warning("AMF object truncated (no name length).")
                    break

                # Extract property name length
                str_length = struct.unpack(
                    ">H", payload[index : index + AMF_STRING_HEADER_SIZE]
                )[0]
                index += AMF_STRING_HEADER_SIZE

                if index + str_length > len(payload):
                    logging.warning(f"Property name length {str_length} out of range.")
                    break

                # Decode property name safely
                property_name = payload[index : index + str_length].decode(
                    "utf-8", errors="ignore"
                )
                index += str_length
                logging.debug(f"Decoded property name: {property_name}")

                if index >= len(payload):
                    logging.warning("AMF truncated before reading type.")
                    break

                # Extract AMF type
                amf_type = payload[index]
                index += 1
                logging.debug(f"Property type: {hex(amf_type)}")

                # Handle different AMF types
                if amf_type == AMF_TYPE_STRING:  # String
                    property_value, index = self.decode_amf_string(payload, index)

                    # Special case: `tcUrl` requires validation
                    if property_name == "tcUrl":
                        logging.debug(f"Extracted raw tcUrl: {property_value}")

                        expected_length = len(
                            f"rtmp://{localhost}:{localport}/{APPLICATION}"
                        )

                        # **🔴 DETECT TRUNCATION AND FIX AUTOMATICALLY**
                        if len(property_value) != expected_length:
                            logging.error(
                                f"tcUrl incorrect length! Expected {expected_length}, got {len(property_value)}"
                            )

                            # If `tcUrl` is missing `/live`, manually correct it
                            if not property_value.endswith("/live"):
                                property_value = (
                                    f"rtmp://{localhost}:{localport}/{APPLICATION}"
                                )
                                logging.warning(f"tcUrl corrected to: {property_value}")

                        logging.debug(f"Final decoded tcUrl: {property_value}")

                elif amf_type == AMF_TYPE_NUMBER:  # Number (Double)
                    if index + AMF_NUMBER_SIZE > len(payload):
                        logging.warning(
                            f"AMF number property '{property_name}' out of range."
                        )
                        break
                    property_value = struct.unpack(
                        ">d", payload[index : index + AMF_NUMBER_SIZE]
                    )[0]
                    index += AMF_NUMBER_SIZE

                elif amf_type == AMF_TYPE_BOOLEAN:  # Boolean
                    if index >= len(payload):
                        logging.warning(
                            f"AMF boolean property '{property_name}' out of range."
                        )
                        break
                    property_value = bool(payload[index])
                    index += 1

                elif amf_type == AMF_TYPE_OBJECT:  # Nested AMF Object
                    property_value, index = self.decode_amf_object(payload, index)

                elif amf_type == AMF_TYPE_NULL:  # Null
                    property_value = None

                elif amf_type == AMF_TYPE_OBJECT_END:  # Object end marker
                    logging.debug(f"AMF Object End detected at index {index}")
                    break

                else:
                    logging.warning(f"Unhandled AMF type: {hex(amf_type)}")
                    break

                # Store extracted value
                amf_object[property_name] = property_value
                logging.debug(f"Updated AMF object: {amf_object}")

            except (struct.error, UnicodeDecodeError, IndexError) as e:
                logging.error(f"Failed to decode AMF object at index {index}: {e}")
                break

        return amf_object, index

    def encode_amf0_string(self, value: str) -> bytes:
        """Encodes an AMF0 string."""
        encoded = value.encode("utf-8")
        return b"\x02" + struct.pack(">H", len(encoded)) + encoded

    def encode_amf0_number(self, value: float) -> bytes:
        """Encodes an AMF0 number (double precision float)."""
        return b"\x00" + struct.pack(">d", float(value))  # 8-byte IEEE 754 double

    def encode_amf0_null(self) -> bytes:
        """Encodes an AMF0 null value."""
        return b"\x05"

    def encode_amf0_object(self, properties: dict) -> bytes:
        """Encodes an AMF0 object properly."""
        obj = b"\x03"  # AMF0 Object marker
        for key, value in properties.items():
            obj += struct.pack(">H", len(key)) + key.encode("utf-8")
            if isinstance(value, str):
                obj += self.encode_amf0_string(value)[1:]  # Skip type byte
            elif isinstance(value, (int, float)):
                obj += self.encode_amf0_number(value)
        obj += b"\x00\x00\x09"  # AMF0 Object End Marker
        return obj

    def encode_amf0_result(self, transaction_id, tc_url):
        """
        Constructs an AMF0 `_result` response for RTMP 'connect' with correct structure.
        """
        return (
            self.encode_amf0_string("_result")  # Command Name
            + self.encode_amf0_number(transaction_id)  # Transaction ID
            + b"\x05"  # AMF0 NULL (Correct placement)
            + self.encode_amf0_object(
                {
                    "fmsVer": "FMS/3,5,3,888",
                    "capabilities": 31.0,
                    "level": "status",
                    "code": "NetConnection.Connect.Success",
                    "description": "Connection succeeded.",
                    "tcUrl": tc_url,
                    "objectEncoding": 0.0,  # **NEW FIELD (Prevents FFmpeg Malformed Error)**
                }
            )
        )

    def build_result_packet(self, transaction_id, tc_url):
        """
        Constructs the full RTMP `_result` response packet.
        """
        amf_payload = self.encode_amf0_result(transaction_id, tc_url)

        connect_header = (
            b"\x02"  # Chunk Basic Header (Format 0, CSID 2)
            + b"\x00\x00\x00"
            + struct.pack(">I", len(amf_payload))[1:4]  # Correct payload length
            + b"\x14"  # Message Type ID (0x14 = Command Message)
            + b"\x00\x00\x00\x00"  # Stream ID (Always 0 for Connect)
        )

        return connect_header + amf_payload

    def set_chunk_size(self, size):
        """Encodes and returns an RTMP Set Chunk Size message in the correct format for FFmpeg."""

        # 1️⃣ RTMP Chunk Basic Header (1 byte)
        basic_header = b"\x02"  # Format 0, Chunk Stream ID 2 (CSID = 2)

        # 2️⃣ RTMP Message Header (7 bytes)
        timestamp = b"\x00\x00\x00"  # Always 0 for control messages
        message_length = b"\x00\x00\x04"  # Payload is always 4 bytes for Set Chunk Size
        message_type = b"\x01"  # RTMP Message Type ID for Set Chunk Size
        message_stream_id = b"\x00\x00\x00\x00"  # Always 0 for Set Chunk Size

        # 3️⃣ RTMP Payload (4 bytes) → The actual chunk size
        chunk_size_payload = struct.pack(">I", size)  # 4-byte Big Endian encoding

        # Combine all parts into a single RTMP packet
        set_chunk_size_packet = (
            basic_header
            + timestamp
            + message_length
            + message_type
            + message_stream_id
            + chunk_size_payload
        )

        # Debugging: Print the hex dump to verify structure before sending
        print(
            f"🔍 Debug Set Chunk Size: {set_chunk_size_packet.hex()} (Length: {len(set_chunk_size_packet)})"
        )

        return set_chunk_size_packet

    def window_ack_size(self, size):
        """Encodes and returns an RTMP Window Acknowledgment Size message in the correct format for FFmpeg."""

        # 1️⃣ RTMP Chunk Basic Header (1 byte)
        basic_header = b"\x02"  # Format 0, Chunk Stream ID 2 (CSID = 2)

        # 2️⃣ RTMP Message Header (7 bytes)
        timestamp = b"\x00\x00\x00"  # Always 0 for control messages
        message_length = b"\x00\x00\x04"  # Payload is always 4 bytes
        message_type = b"\x05"  # RTMP Message Type ID for Window Acknowledgment Size
        message_stream_id = b"\x00\x00\x00\x00"  # Always 0 for this message type

        # 3️⃣ RTMP Payload (4 bytes) → The acknowledgment window size
        ack_size_payload = struct.pack(">I", size)  # 4-byte Big Endian encoding

        # Combine all parts into a single RTMP packet
        window_ack_packet = (
            basic_header
            + timestamp
            + message_length
            + message_type
            + message_stream_id
            + ack_size_payload
        )

        # Debugging: Print the hex dump to verify structure before sending
        print(
            f"🔍 Debug Window Acknowledgment Size: {window_ack_packet.hex()} (Length: {len(window_ack_packet)})"
        )

        return window_ack_packet

    def set_peer_bandwidth(self, size, limit_type=2):
        """Encodes and returns an RTMP Set Peer Bandwidth message in the correct format for FFmpeg."""

        # 1️⃣ RTMP Chunk Basic Header (1 byte)
        basic_header = b"\x02"  # Format 0, Chunk Stream ID 2 (CSID = 2)

        # 2️⃣ RTMP Message Header (7 bytes)
        timestamp = b"\x00\x00\x00"  # Always 0 for control messages
        message_length = b"\x00\x00\x05"  # Payload is always 5 bytes
        message_type = b"\x06"  # RTMP Message Type ID for Set Peer Bandwidth
        message_stream_id = b"\x00\x00\x00\x00"  # Always 0 for control messages

        # 3️⃣ RTMP Payload (4-byte Window Size + 1-byte Limit Type)
        bandwidth_payload = struct.pack(">I", size) + struct.pack(">B", limit_type)

        # Combine all parts into a single RTMP packet
        set_peer_bandwidth_packet = (
            basic_header
            + timestamp
            + message_length
            + message_type
            + message_stream_id
            + bandwidth_payload
        )

        # Debugging: Print the hex dump to verify structure before sending
        print(
            f"🔍 Debug Set Peer Bandwidth: {set_peer_bandwidth_packet.hex()} (Length: {len(set_peer_bandwidth_packet)})"
        )

        return set_peer_bandwidth_packet

    def encode_amf0_boolean(self, value):
        """Encodes an AMF0 boolean."""
        return b"\x01" + struct.pack(">B", 1 if value else 0)

    def encode_amf0_object(self, properties: dict) -> bytes:
        """
        Encodes an AMF0 object with correct key-value pairs.
        """
        obj = b"\x03"  # AMF0 Object Start
        for key, value in properties.items():
            obj += struct.pack(">H", len(key)) + key.encode("utf-8")  # Key name
            if isinstance(value, str):
                obj += self.encode_amf0_string(value)  # Use correct string encoding
            elif isinstance(value, (int, float)):
                obj += self.encode_amf0_number(value)
        obj += b"\x00\x00\x09"  # **Proper Object End Marker**
        return obj

    def encode_amf0_onstatus_publish(self):
        """Encodes an AMF0 'onStatus' response for 'NetStream.Publish.Start'."""
        properties = {
            "level": "status",
            "code": "NetStream.Publish.Start",
            "description": "Publishing stream started",
        }
        return (
            self.encode_amf0_string("onStatus")
            + self.encode_amf0_number(0)  # Transaction ID (0 for server messages)
            + self.encode_amf0_object(properties)
        )

    async def send_publish_start(self, writer):
        """Sends the 'NetStream.Publish.Start' onStatus message to FFmpeg."""
        status_payload = self.encode_amf0_onstatus_publish()

        status_header = (
            b"\x02"  # Chunk Basic Header (Format 0, CSID 2)
            + b"\x00\x00\x00"  # Timestamp (0)
            + struct.pack(">I", len(status_payload))[1:4]  # Payload Size
            + b"\x14"  # Message Type ID (Command Message)
            + b"\x00\x00\x00\x01"  # Stream ID
        )

        full_status = status_header + status_payload
        writer.write(full_status)
        await writer.drain()
        logging.info("✅ Sent NetStream.Publish.Start.")

    def stream_begin(self, stream_id=3):
        """Encodes and returns an RTMP Stream Begin (0x04) message in the correct format for FFmpeg."""

        # return stream_begin_packet
        return (
            b"\x02"  # Chunk Basic Header (Format 0, CSID 2)
            + b"\x00\x00\x00"  # Timestamp (0)
            + b"\x00\x06"  # Payload size = 6 bytes
            + b"\x04"  # Message Type ID = User Control Message
            + b"\x00\x00\x00\x00"  # Always 0 for control messages
            + struct.pack(">HI", 0, stream_id)  # Event Type (0) + Stream ID
        )

    def encode_amf0_onstatus(self):
        """Encodes the RTMP `onStatus` event using AMF0 format."""

        return (
            b"\x02"
            + struct.pack(">H", len("onStatus"))
            + b"onStatus"  # AMF0 String: `onStatus`
            + b"\x00\x00\x00\x00"  # AMF0 Number: Transaction ID = 0.0
            + b"\x03"  # AMF0 Object (Start)
            + b"\x02"
            + struct.pack(">H", len("level"))
            + b"level"
            + b"\x02"
            + struct.pack(">H", len("status"))
            + b"status"
            + b"\x02"
            + struct.pack(">H", len("code"))
            + b"code"
            + b"\x02"
            + struct.pack(">H", len("NetConnection.Connect.Success"))
            + b"NetConnection.Connect.Success"
            + b"\x02"
            + struct.pack(">H", len("description"))
            + b"description"
            + b"\x02"
            + struct.pack(">H", len("Connection established successfully."))
            + b"Connection established successfully."
            + b"\x00\x00\x09"  # AMF0 Object End
        )

    def send_onstatus(self):
        """Encodes and returns an RTMP `onStatus` Invoke message to confirm a successful connection."""

        # Encode AMF0 Payload
        status_payload = self.encode_amf0_onstatus()

        # 1️⃣ RTMP Chunk Basic Header (1 byte)
        basic_header = b"\x02"  # Format 0, Chunk Stream ID 2 (CSID = 2)

        # 2️⃣ RTMP Message Header (7 bytes)
        timestamp = b"\x00\x00\x00"  # Always 0 for control messages
        message_length = struct.pack(">I", len(status_payload))[
            1:4
        ]  # Payload size (3 bytes)
        message_type = b"\x14"  # RTMP Message Type ID for Invoke (`onStatus`)
        message_stream_id = b"\x00\x00\x00\x00"  # Always 0 for control messages

        # Combine all parts into a single RTMP packet
        onstatus_packet = (
            basic_header
            + timestamp
            + message_length
            + message_type
            + message_stream_id
            + status_payload
        )

        # Debugging: Print the hex dump to verify structure before sending
        print(
            f"🔍 Debug `onStatus`: {onstatus_packet.hex()} (Length: {len(onstatus_packet)})"
        )

        return onstatus_packet

    def send_setdataframe(self, writer):
        """Sends @setDataFrame to establish metadata for the stream."""
        payload = (
            self.encode_amf0_string("@setDataFrame")
            + self.encode_amf0_string("onMetaData")
            + self.encode_amf0_object({"encoder": "Lavf61.9.106", "filesize": 0})
        )

        header = (
            b"\x02"  # Chunk Basic Header
            + b"\x00\x00\x00"
            + struct.pack(">I", len(payload))[1:4]
            + b"\x12"  # Message Type ID (0x12 = Data Message)
            + b"\x00\x00\x00\x01"  # Stream ID
        )

        return header + payload

    def send_onbwdone(self, writer):
        """Sends the RTMP `onBWDone` event, required for FFmpeg to proceed to publish."""

        # ✅ Construct the AMF0 `onBWDone` payload
        bw_done_payload = (
            self.encode_amf0_string("onBWDone")  # AMF0 String "onBWDone"
            + self.encode_amf0_number(
                0
            )  # Transaction ID (always 0 for system messages)
            + b"\x05"  # AMF0 NULL (Required!)
        )

        # ✅ Construct the RTMP Header for `onBWDone`
        bw_done_header = (
            b"\x02"  # Chunk Basic Header (Format 0, CSID 2)
            + b"\x00\x00\x00"  # Timestamp (0)
            + struct.pack(">I", len(bw_done_payload))[1:4]  # Payload Size (3 bytes)
            + b"\x14"  # Message Type ID (0x14 = Command Message)
            + b"\x00\x00\x00\x00"  # Message Stream ID (always 0 for control messages)
        )

        full_bw_done = bw_done_header + bw_done_payload

        logging.debug(f"RTMP onBWDone Response Hex: {full_bw_done.hex()}")
        return full_bw_done

    async def drain_and_sleep(self, writer):
        await writer.drain()
        await asyncio.sleep(0.1)

    def send_release_stream(self, transaction_id, app_name):
        release_stream_payload = (
            self.encode_amf0_string("releaseStream")
            + self.encode_amf0_number(transaction_id + 1)
            + b"\x05"  # AMF0 NULL
            + self.encode_amf0_string(app_name)  # Stream Name
        )
        release_stream_header = (
            b"\x02"
            + b"\x00\x00\x00"
            + struct.pack(">I", len(release_stream_payload))[1:4]
            + b"\x14"
            + b"\x00\x00\x00\x00"
        )
        return release_stream_header + release_stream_payload

    async def handle_connect(self, transaction_id, command_object, writer):
        try:
            # Prevent duplicate connect commands
            if hasattr(self, "client_connected") and self.client_connected:
                logging.warning("Duplicate `connect` command received, ignoring.")
                return

            self.client_connected = True  # Mark session as active
            logging.info(f"Handling RTMP connect, transaction_id: {transaction_id}")

            # # Extract App Name and Stream URL
            # app_name = command_object.get("app", "live")
            # tc_url = command_object.get(
            #     "tcUrl", f"rtmp://{self.host}:{self.port}/{app_name}"
            # )
            # logging.info(f"App: {app_name}, tcUrl: {tc_url}")

            # # ✅ Step 1: Send Set Chunk Size (4096)
            # writer.write(self.set_chunk_size(4096))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent Set Chunk Size (4096).")

            # # ✅ Step 2: Send Window Acknowledgment Size
            # writer.write(self.window_ack_size(2500000))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent Window Acknowledgment Size.")

            # # ✅ Step 3: Send Set Peer Bandwidth
            # writer.write(self.set_peer_bandwidth(2500000))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent Set Peer Bandwidth.")

            # # ✅ Step 4: Send `_result` for NetConnection.Connect.Success
            # writer.write(self.build_result_packet(transaction_id, tc_url))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent NetConnection.Connect.Success.")

            # # ✅ Step 6: Send Stream Begin (0x04)
            # writer.write(self.stream_begin(1))  # Stream ID 1
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent Stream Begin (0x04).")

            # # ✅ Step 7: Send NetStream.Publish.Start
            # await self.send_publish_start(writer)

            # # ✅ Step 8: Send `onBWDone`
            # writer.write(self.send_onbwdone(writer))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent onBWDone.")

            #  # ✅ Step 8.5: Send Set Chunk Size (128)
            # writer.write(self.set_chunk_size(128))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent Set Chunk Size (128).")

            # # ✅ Step 9: Send `releaseStream` (Needed for FFmpeg)
            # release_stream_payload = (
            #     self.encode_amf0_string("releaseStream")
            #     + self.encode_amf0_number(transaction_id + 1)
            #     + b"\x05"  # AMF0 NULL
            #     + self.encode_amf0_string(app_name)  # Stream Name
            # )
            # release_stream_header = (
            #     b"\x02"
            #     + b"\x00\x00\x00"
            #     + struct.pack(">I", len(release_stream_payload))[1:4]
            #     + b"\x14"
            #     + b"\x00\x00\x00\x00"
            # )
            # writer.write(release_stream_header + release_stream_payload)
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent releaseStream.")

            # # ✅ Step 10: Send @setDataFrame (Metadata)
            # writer.write(self.send_setdataframe(writer))
            # await self.drain_and_sleep(writer)
            # logging.info("✅ Sent @setDataFrame (Metadata).")

            # # ✅ Step 11: Wait for `createStream` from FFmpeg
            # logging.info("🔄 Waiting for createStream command...")

            # self.client_connected = True
            # logging.info(f"Handling RTMP connect, transaction_id: {transaction_id}")

            # ✅ Extract App Name and tcUrl
            app_name = command_object.get("app", "live")
            tc_url = command_object.get(
                f"tcUrl", f"rtmp://{self.host}:{self.port}/{app_name}"
            )

            # ✅ Step 1: Send Set Chunk Size (4096)
            writer.write(self.set_chunk_size(4096))
            await self.drain_and_sleep(writer)

            # ✅ Step 2: Send Window Acknowledgment Size
            writer.write(self.window_ack_size(2500000))
            await self.drain_and_sleep(writer)

            # ✅ Step 3: Send Set Peer Bandwidth
            writer.write(self.set_peer_bandwidth(2500000))
            await self.drain_and_sleep(writer)

            # ✅ Step 4: Send `_result` for NetConnection.Connect.Success
            writer.write(self.build_result_packet(transaction_id, tc_url))
            await self.drain_and_sleep(writer)

            # ✅ Step 5: Send `onStatus`
            writer.write(self.send_onstatus())
            await self.drain_and_sleep(writer)

            # ✅ Step 6: Send onBWDone BEFORE Set Chunk Size 128
            writer.write(self.send_onbwdone(writer))
            await self.drain_and_sleep(writer)

            # ✅ Step 7: Send Set Chunk Size (128)
            writer.write(self.set_chunk_size(128))
            await self.drain_and_sleep(writer)

            # ✅ Step 8: Send Stream Begin 0 BEFORE releaseStream
            writer.write(self.stream_begin(0))
            await self.drain_and_sleep(writer)

            # ✅ Step 9: Send releaseStream('webcam')
            writer.write(self.send_release_stream(transaction_id, app_name))
            await self.drain_and_sleep(writer)

            # ✅ Step 11: Send @setDataFrame Metadata
            writer.write(self.send_setdataframe(writer))
            await self.drain_and_sleep(writer)

            # ✅ Step 12: Wait for `createStream`
            logging.info("Waiting for createStream command...")

        except Exception as e:
            logging.error(f"❌ Error handling RTMP connect: {e}")
            writer.close()

    async def handle_FCPublish(self, decoded_values, writer):
        """
        Handles RTMP 'publish' requests properly.
        """
        try:
            if len(decoded_values) < 3:
                logging.error("Invalid publish command format.")
                return

            transaction_id = decoded_values[1] if len(decoded_values) > 1 else 0.0
            stream_key = (
                decoded_values[3] if len(decoded_values) > 3 else "default"
            )  # ✅ Extract correct index

            print("decoded values: ", decoded_values)
            logging.info(f"📡 Publishing stream: key={stream_key}")

            # ✅ Store stream info
            self.streams[stream_key] = {"status": "publishing"}

            # ✅ Validate Stream Key (Ensure it's not None)
            if not stream_key or stream_key == "None":
                logging.error("❌ Stream key is None! Possible AMF decoding issue.")
                return

            # ✅ Send NetStream.Publish.Start response
            response_body = (
                self.encode_amf0_string("onStatus")
                + self.encode_amf0_number(transaction_id)
                + b"\x05"  # AMF0 NULL (Required!)
                + self.encode_amf0_object(
                    {
                        "level": "status",
                        "code": "NetStream.Publish.Start",
                        "description": f"Publishing stream started for key {stream_key}.",
                    }
                )
            )

            response_header = (
                b"\x02"  # Chunk Basic Header (Format 0, CSID 2)
                + b"\x00\x00\x00"  # Timestamp
                + struct.pack(">I", len(response_body))[1:4]  # Payload size
                + b"\x14"  # Message Type ID (Command Message)
                + struct.pack("<I", 1)  # Little-endian Stream ID
            )

            response = response_header + response_body
            writer.write(response)
            await self.drain_and_sleep(writer)

            # ✅ Step 5: Send `onStatus` event
            writer.write(self.send_onstatus())
            await self.drain_and_sleep(writer)
            logging.info("✅ Sent onStatus.")

            logging.info(f"✅ Stream '{stream_key}' successfully published.")

        except Exception as e:
            logging.error(f"❌ Error handling publish request: {e}")

    async def handle_publish_response(self, writer, transaction_id, stream_key):
        """Handles `publish` command from the client."""
        logging.info(f"✅ Handling publish request for stream: {stream_key}")

        # Acknowledge the publish command
        response = (
            self.encode_amf0_string("onStatus")
            + self.encode_amf0_number(transaction_id)
            + b"\x05"  # AMF0 NULL
            + self.encode_amf0_object(
                {
                    "level": "status",
                    "code": "NetStream.Publish.Start",
                    "description": f"Stream {stream_key} is now published.",
                }
            )
        )

        header = (
            b"\x02"
            + b"\x00\x00\x00"
            + struct.pack(">I", len(response))[1:4]
            + b"\x14"
            + b"\x00\x00\x00\x01"  # Stream ID
        )

        writer.write(header + response)
        await self.drain_and_sleep(writer)
        logging.info(f"✅ Sent NetStream.Publish.Start for {stream_key}.")

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

    async def start(self):
        """Starts the RTMP server."""
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        # ✅ FIX: Loop through `server.sockets` correctly
        # for sock in server.sockets:
        #     sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Disable Nagle's algorithm

        logging.info(f"RTMP Server listening on {self.host}:{self.port}")

        # Launch the audio/video stream
        if launchStreamWithFFMPEG == True:
            self.launch_audiovideostream()

        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    rtmp_server = RTMPServer()
    asyncio.run(rtmp_server.start())
