import asyncio
import struct
import logging

logging.basicConfig(level=logging.DEBUG)

addresshost = "127.0.0.1"
addressport = 1935


class RTMPServer:
    def __init__(self, host=addresshost, port=addressport):
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

                # Read RTMP Message Header
                timestamp_bytes = await reader.read(3)
                timestamp = int.from_bytes(timestamp_bytes, "big")

                payload_size_bytes = await reader.read(3)
                payload_size = int.from_bytes(payload_size_bytes, "big")

                msg_type = await reader.read(1)
                stream_id_bytes = await reader.read(4)

                if not msg_type:
                    logging.warning("Invalid RTMP message: no type found.")
                    break

                logging.debug(
                    f"RTMP Message Type: {msg_type.hex()}, Payload Size: {payload_size}"
                )

                # Read Payload Data
                payload = await reader.read(payload_size)
                logging.debug(f"Received payload: {payload.hex()}")

                # Handle Different RTMP Messages
                if msg_type == b"\x14":  # AMF Command (connect, publish, play, etc.)
                    await self.handle_amf_command(payload, writer)
                elif msg_type == b"\x09":  # Video Data
                    await self.handle_video_packet(payload)
                elif msg_type == b"\x08":  # Audio Data
                    await self.handle_audio_packet(payload)
                else:
                    logging.warning(f"Unhandled RTMP message type: {msg_type.hex()}")

            except Exception as e:
                logging.error(f"Error handling client: {e}")
                break

    async def rtmp_handshake(self, reader, writer):
        """
        Implements RTMP Handshake: C0, C1, C2 exchange.
        """
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

    async def handle_amf_command(self, payload, writer):
        """
        Parses and handles AMF commands from clients.
        """
        try:
            logging.debug(f"AMF Command Payload: {payload.hex()}")
            command_name = self.decode_amf_string(payload)
            logging.info(f"AMF Command Received: {command_name}")

            if command_name == "connect":
                await self.handle_connect(writer)
            elif command_name == "createStream":
                await self.handle_create_stream(writer)
            elif command_name == "publish":
                await self.handle_publish(payload, writer)
            elif command_name == "play":
                await self.handle_play(payload, writer)
            else:
                logging.warning(f"Unknown AMF Command: {command_name}")

        except Exception as e:
            logging.error(f"Error parsing AMF command: {e}")

    async def handle_video_packet(self, payload):
        """
        Handles RTMP video data packets.
        """
        logging.info(f"Received Video Packet: {len(payload)} bytes")

    async def handle_audio_packet(self, payload):
        """
        Handles RTMP audio data packets.
        """
        logging.info(f"Received Audio Packet: {len(payload)} bytes")

    async def handle_connect(self, writer):
        """
        Responds to RTMP Connect requests.
        """
        response = (
            b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x06"
            b"\x00\x03\x00\x00\x00\x00\x00\x00"
        )
        writer.write(response)
        await writer.drain()
        logging.info("Sent RTMP connect response.")

    async def handle_create_stream(self, writer):
        """
        Responds to createStream request.
        """
        stream_id = 1  # Default to stream ID 1
        self.streams[stream_id] = None

        response = b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x05" + struct.pack(
            ">I", stream_id
        )
        writer.write(response)
        await writer.drain()
        logging.info(f"Stream {stream_id} created.")

    async def handle_publish(self, payload, writer):
        """
        Handles an RTMP publish request.
        """
        stream_key = self.decode_amf_string(payload[2:])
        logging.info(f"Publishing stream with key: {stream_key}")
        self.streams[1] = stream_key

        response = b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x05" + struct.pack(">I", 1)
        writer.write(response)
        await writer.drain()
        logging.info("Sent publish confirmation.")

    def decode_amf_string(self, data):
        """
        Decodes an AMF encoded string.
        """
        try:
            str_length = struct.unpack(">H", data[:2])[0]
            return data[2 : 2 + str_length].decode("utf-8")
        except (struct.error, UnicodeDecodeError) as e:
            logging.error(f"Failed to decode AMF string: {e}")
            return ""

    async def start(self):
        """
        Starts the RTMP server.
        """
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        logging.info(f"RTMP Server listening on {self.host}:{self.port}")

        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    rtmp_server = RTMPServer()
    asyncio.run(rtmp_server.start())
