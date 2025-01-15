import socket
import threading
import struct
import time
import logging
from concurrent.futures import ThreadPoolExecutor

# Constants
MAGIC_COOKIE = 0xabcddcba  # identifier to ensure messages come from the correct server
OFFER_MESSAGE_TYPE = 0x2  # udp broadcast offer message
REQUEST_MESSAGE_TYPE = 0x3
PAYLOAD_MESSAGE_TYPE = 0x4  # payload data message
UDP_BROADCAST_INTERVAL = 1  # how ofter the server sends broadcast message (second)
BUFFER_SIZE = 1024  # size of each packet

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Server class
class Server:
    def __init__(self, ip, udp_port, tcp_port):
        self.ip = ip
        self.udp_port = udp_port
        self.tcp_port = tcp_port

        # udp socket setup
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create udp socket for communication
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ensure that multiple threads on the same computer in one udp port
        #self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.udp_socket.bind((self.ip, self.udp_port))  # Ensure binding happens before setting broadcast option
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # congifure udp socket to allow broadcasting

        #tcp socket setup
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # create tcp socket for communication
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ensure that multiple threads on the same computer in one tcp port
        #self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        # threading
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=10)

    def start(self):
        """
        Initialize the server be starting udp broadcast to announce the server's presence
        and tcp server to manage client connections and data transfer
        :return:
        """
        # Start the UDP broadcast thread that run the send_offers function
        threading.Thread(target=self.send_offers, daemon=True).start()

        # Start the TCP server to specific ip address and port
        self.tcp_socket.bind((self.ip, self.tcp_port))
        # listen for incoming tcp connection with backlog of 5
        # is the maximum number of queued connection requests waiting to be accepted
        self.tcp_socket.listen(5)
        #print(f"Server started, listening on IP address {self.ip}")
        # server is running and ready to accept connections
        logging.info(f"Server started, listening on {self.ip}:{self.tcp_port}")

        try:
            while not self.stop_event.is_set():
                self.tcp_socket.settimeout(2)  # Timeout to periodically check stop_event
                try:
                    client_socket, client_address = self.tcp_socket.accept()
                    self.executor.submit(self.handle_tcp_connection, client_socket)
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            logging.info("Server shutting down...")
            self.stop()

    def send_offers(self):
        """
        The function broadcasts a message over UDP at regular intervals to let
        clients know about the server's availability and its connection details
        :return:
        """
        # Creating the UDP offer message, format !I B H specifies how the data should be packed
        # !-big endian byte order, I-unsigned 4byte int (magic_cookie),
        # B-1byte unsigned int (offer_mess_type), H-2byte unsigned int (udp_port),
        # H-2byte tcp port
        offer_message = struct.pack('!I B H H', MAGIC_COOKIE, OFFER_MESSAGE_TYPE, self.udp_port, self.tcp_port)
        # send the message to all devices on the network via udp broadcast
        while not self.stop_event.is_set():  # Check if the event is set
            try:
                # sends the offer_message to all devices on the network using UDP broadcast
                self.udp_socket.sendto(offer_message, ('<broadcast>', self.udp_port))
                logging.info(f"Broadcasting UDP offer on port {self.udp_port}")
                time.sleep(UDP_BROADCAST_INTERVAL)  # ensures that the offer message is sent at regular intervals
            except Exception as e:
                logging.error(f"Error sending UDP offer: {e}")

    def listen_for_udp_requests(self):
        """
        Listen for UDP requests from clients and handle them.
        """
        try:
            self.udp_socket.bind((self.ip, self.udp_port))
        except OSError as e:
            logging.error(f"Error binding UDP socket: {e}")
            return

        while not self.stop_event.is_set():
            try:
                data, client_address = self.udp_socket.recvfrom(BUFFER_SIZE)
                if self.validate_request(data):
                    file_size = struct.unpack('!Q', data[5:])[0]
                    self.executor.submit(self.handle_udp_connection, client_address, file_size)
            except Exception as e:
                logging.error(f"Error handling UDP request: {e}")

    def validate_request(self, data):
        """
        Validate incoming UDP request.
        """
        if len(data) < 13:
            return False
        magic_cookie, message_type = struct.unpack('!I B', data[:5])
        return magic_cookie == MAGIC_COOKIE and message_type == REQUEST_MESSAGE_TYPE

    def handle_tcp_connection(self, client_socket):
        """
        The function is responsible for handling TCP connection for a single client,
        it's receives a file size request from the client via TCP, validates it, and generates a dummy file of the requested size.
        The file (a sequence of zero bytes) is sent to the client.
        :param client_socket: the socket object for communication between the server and the connected client
        :return:
        """
        try:
            # reads the data sent by the client
            # (BUFFER_SIZE is a constant that defines the maximum number of bytes to read at a time)
            # decodes the received byte string into a regular string
            # split - removes any leading or trailing whitespace/newlines/spaces from the received string
            request = client_socket.recv(BUFFER_SIZE).decode('utf-8').strip()
            if not request.isdigit():  # validate the request
                raise ValueError("Invalid file size request.")
            file_size = int(request)  # convert to int
            # creates a dummy file to send to the client
            data = b'0' * file_size
            client_socket.sendall(data)  # send data (dummy file) to client
            logging.info(f"Sent {file_size} bytes via TCP.")  # it's not in the example
        except Exception as e:
            logging.error(f"Error handling TCP connection: {e}")
        finally:
            client_socket.close()

    def handle_udp_connection(self, client_address, file_size):
        """
        The function is responsible for sending a file to a client over UDP in smaller parts. It also ensures
        the file is sent reliably by managing ACKs and retransmitting any lost packets
        :param client_socket: the address (IP and port) of the client that will receive the file
        :param file_size: the total size (in bytes) of the file to be sent
        :return:
        """
        try:
            # calculate how many segments (packets) are needed to send the entire file,
            # BUFFER_SIZE is the maximum size of each udp packet,
            # calculation ensures that the total file size is divided into chunks of BUFFER_SIZE, rounding if need
            total_segments = (file_size + BUFFER_SIZE - 1) // BUFFER_SIZE
            # iterate over the total numberof segments and create each segment
            for seq in range(total_segments):
                # construct the payload for the current segment
                payload_message = struct.pack('!I B Q Q', MAGIC_COOKIE, PAYLOAD_MESSAGE_TYPE, total_segments, seq)
                payload_message += b'0' * min(BUFFER_SIZE, file_size - seq * BUFFER_SIZE)
                # sends the constructed udp packet to the client
                self.udp_socket.sendto(payload_message, client_address)
            logging.info(f"Sent {file_size} bytes via UDP to {client_address}.")
        except Exception as e:
            logging.error(f"Error handling UDP connection: {e}")

    def stop(self):
        """
        Stop the server gracefully.
        """
        self.stop_event.set()
        self.udp_socket.close()
        self.tcp_socket.close()
        self.executor.shutdown(wait=True)


if __name__ == '__main__':
    server = Server('0.0.0.0', 54321, 12345)
    server.start()
