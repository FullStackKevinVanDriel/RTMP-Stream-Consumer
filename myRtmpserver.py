import asyncio
import struct
import logging

logging.basicConfig(level=logging.DEBUG)


class RTMPServer:
    def __init__(self, host="127.0.0.1", port=1935):
        self.host = host
        self.port = port
        self.streams = {}

    async def handle_client(self, reader, writer):
        logging.info("New client connected.")

        # Step 1: Perform RTMP Handshake
        await self.rtmp_handshake(reader, writer)

        # Step 2: Process RTMP messages
        while True:
            try:
                # Read RTMP Chunk Basic Header (1 byte)
                basic_header = await reader.read(1)
                if not basic_header:
                    logging.info("Client disconnected.")
                    break

                chunk_format = (basic_header[0] & 0b11000000) >> 6
                chunk_stream_id = basic_header[0] & 0b00111111

                logging.debug(
                    f"Chunk Format: {chunk_format}, Chunk Stream ID: {chunk_stream_id}"
                )

                # Read RTMP Message Header (timestamp, message length, message type, stream ID)
                timestamp_bytes = await reader.read(3)
                timestamp = int.from_bytes(timestamp_bytes, "big")

                payload_size_bytes = await reader.read(3)
                payload_size = int.from_bytes(payload_size_bytes, "big")

                msg_type = await reader.read(1)
                stream_id_bytes = await reader.read(4)
                stream_id = int.from_bytes(stream_id_bytes, "little")

                if not msg_type:
                    logging.warning("Invalid RTMP message: no type found.")
                    break

                logging.debug(
                    f"RTMP Message Type: {msg_type.hex()}, Payload Size: {payload_size}, Stream ID: {stream_id}"
                )

                # Read Payload Data
                payload = await reader.read(payload_size)
                if not payload:
                    logging.warning("Payload missing.")
                    break

                logging.debug(f"Received payload: {payload.hex()}")

                # Handle Different RTMP Messages
                if msg_type == b"\x14":  # AMF Command (connect, publish, play, etc.)
                    await self.handle_amf_command(payload, writer)
                elif msg_type == b"\x09":  # Video Data
                    await self.handle_video_packet(payload)
                elif msg_type == b"\x08":  # Audio Data
                    await self.handle_audio_packet(payload)
                elif msg_type == b"\x01":  # Unkonwn message type
                    # Handle RTMP message type 01 (Set Chunk Size)
                    if len(payload) >= 4:
                        chunk_size = struct.unpack(">I", payload[:4])[0]
                        self.chunk_size = chunk_size
                        logging.debug(f"Set Chunk Size to: {chunk_size}")
                    else:
                        logging.warning("Invalid Set Chunk Size message received.")
                else:
                    logging.warning(f"Unhandled RTMP message type: {msg_type.hex()}")

            except Exception as e:
                logging.error(f"Error handling client: {e}")
                break

    async def rtmp_handshake(self, reader, writer):
        """Implements RTMP Handshake: C0, C1, C2 exchange."""
        try:
            c0_c1 = await reader.read(1537)  # C0 (1 byte) + C1 (1536 bytes)
            if not c0_c1:
                logging.error("Handshake failed: no data received.")
                return

            logging.info("Received C0 + C1 handshake from client.")

            # C0 should be 0x03 for RTMP version
            if c0_c1[0] != 3:
                logging.error("Invalid RTMP version.")
                return

            # Respond with S0 + S1 + S2
            s0_s1_s2 = bytes([3]) + c0_c1[1:1537] + c0_c1[1:1537]  # Echo C1 as S2
            writer.write(s0_s1_s2)
            await writer.drain()
            logging.info("Sent S0 + S1 + S2 handshake response.")

            # Receive C2 from client
            c2 = await reader.read(1536)
            if not c2:
                logging.error("Failed to receive C2 from client.")
                return

            logging.info("Handshake completed.")
        except Exception as e:
            logging.error(f"Handshake error: {e}")

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
        # Implement your AMF decoding logic here
        # This is a placeholder implementation
        command_name = "connect"
        transaction_id = 1
        command_object = {}
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
            decoded_values = self.decode_amf_payload(payload)
            if decoded_values:
                command_name = decoded_values[0]
                logging.info(f"AMF Command Received: {command_name}")

                if command_name == "connect":
                    await self.handle_connect(transaction_id, command_object, writer)
                elif command_name == "createStream":
                    await self.handle_create_stream(writer)
                elif command_name == "publish":
                    await self.handle_publish(decoded_values, writer)
                elif command_name == "play":
                    await self.handle_play(decoded_values, writer)
                else:
                    logging.warning(f"Unknown AMF Command: {command_name}")
            else:
                logging.warning("No valid AMF command found in payload.")

        except Exception as e:
            logging.error(f"Error parsing AMF command: {e}")

    async def handle_create_stream(self, writer):
        """
        Responds to RTMP createStream request properly.
        """
        stream_id = 1  # Default to stream ID 1
        self.streams[stream_id] = None

        response = b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x05" + struct.pack(
            ">I", stream_id
        )
        writer.write(response)
        await writer.drain()
        logging.info(f"Stream {stream_id} created.")

    async def handle_publish(self, decoded_values, writer):
        """
        Handles RTMP 'publish' request properly.
        """
        try:
            if len(decoded_values) < 3:
                logging.error("Invalid publish command format.")
                return

            stream_key = decoded_values[2]  # Third element is stream key
            logging.info(f"Publishing stream with key: {stream_key}")

            self.streams[1] = stream_key  # Store stream key for this session

            # Respond to the client with NetStream.Publish.Start
            response = (
                b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x06"  # RTMP Header
                b"\x00\x03\x00\x00\x00\x00\x00\x00"  # Message Body (Success Response)
            )
            writer.write(response)
            await writer.drain()

            logging.info(f"Stream {stream_key} started successfully.")

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
        Decodes an AMF object safely.
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

            except (struct.error, UnicodeDecodeError, IndexError) as e:
                logging.error(f"Failed to decode AMF object at index {index}: {e}")
                logging.debug(f"Data causing error: {payload[index:].hex()}")
                break

        return amf_object, index

    async def handle_connect(self, transaction_id, command_object, writer):
        """Responds to RTMP Connect requests."""
        try:
            # Create the response body
            response_body = (
                b"\x02"  # AMF0 String
                + struct.pack(">H", len("_result"))
                + b"_result"  # '_result'
                + b"\x00\x3f\xf0\x00\x00\x00\x00\x00\x00"  # Transaction ID 1 (double)
                + b"\x03"  # AMF0 Object
                + b"\x00\x03"
                + b"fms"
                + b"\x02"
                + struct.pack(">H", len("FMS/3,0,1,123"))
                + b"FMS/3,0,1,123"  # 'fms' : 'FMS/3,0,1,123'
                + b"\x00\x04"
                + b"capabilities"
                + b"\x00\x40\x00\x00\x00\x00\x00\x00\x00"  # 'capabilities' : 0.0 (double)
                + b"\x00\x00\x09"  # End of object
                + b"\x03"  # AMF0 Object
                + b"\x00\x04"
                + b"level"
                + b"\x02"
                + struct.pack(">H", len("status"))
                + b"status"  # 'level' : 'status'
                + b"\x00\x07"
                + b"code"
                + b"\x02"
                + struct.pack(">H", len("NetConnection.Connect.Success"))
                + b"NetConnection.Connect.Success"  # 'code' : 'NetConnection.Connect.Success'
                + b"\x00\x06"
                + b"description"
                + b"\x02"
                + struct.pack(">H", len("Connection succeeded."))
                + b"Connection succeeded."  # 'description' : 'Connection succeeded.'
                + b"\x00\x04"
                + b"objectEncoding"
                + b"\x00\x40\x00\x00\x00\x00\x00\x00\x00"  # 'objectEncoding' : 0.0 (double)
                + b"\x00\x00\x09"  # End of object
            )

            # Create the response header
            response_header = (
                b"\x02\x00\x00\x00\x00\x00\x00\x00\x00"  # Chunk Stream ID and Timestamp
                + struct.pack(">I", len(response_body))  # Message Length
                + b"\x14"  # Message Type ID (AMF Command)
                + b"\x00\x00\x00\x00"  # Message Stream ID
            )

            # Combine header and body
            response = response_header + response_body

            writer.write(response)
            await writer.drain()
            logging.info("Sent RTMP connect response.")
        except Exception as e:
            logging.error(f"Failed to handle connect: {e}")

    async def start(self):
        """Starts the RTMP server."""
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"RTMP Server listening on {self.host}:{self.port}")

        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    rtmp_server = RTMPServer()
    asyncio.run(rtmp_server.start())
