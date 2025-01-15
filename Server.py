import socket
import struct
import time
import threading
import select
import os

BUFFER_SIZE = 1024
TCP_PORT_SERVER = 12345
UDP_BROADCAST_PORT = 54321
MAGIC_COOKIE = 0xabcddcba
OFFER_MESSAGE_TYPE = 0x2
REQUEST_MESSAGE_TYPE = 0x3
PAYLOAD_MESSAGE_TYPE = 0x4
STOP_EVENT = threading.Event()  # Create a threading event to signal when to stop the thread


# ANSI color codes
class Colors:
    OKPINK = '\033[38;5;206m'  # Soft Pink
    OKLAVENDER = '\033[38;5;183m'  # Lavender
    OKPEACH = '\033[38;5;216m'  # Peach
    OKCYAN = '\033[96m'
    LIGHTBLUE = '\033[38;5;111m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class Server:
    def __init__(self):
        self.tcp_port = None
        self.udp_port = None
        self.tcp_socket = None
        self.udp_socket = None
        self.initialize_sockets()

    def initialize_sockets(self):
        # UDP socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)  # Allows the socket to reuse the same ip and port
        self.udp_socket.bind((socket.gethostbyname(socket.gethostname()), 0))  # Bind to any available port
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST,1)  # Allow the socket send broadcast messages
        self.udp_port = self.udp_socket.getsockname()[1]

        # TCP socket
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Define a TCP socket
        self.tcp_socket.bind(("", 0))  # Bind to any available port
        self.tcp_port = self.tcp_socket.getsockname()[1]
        self.tcp_socket.listen(1000)

        server_ip = socket.gethostbyname(socket.gethostname())
        print(
            f"{Colors.OKPEACH}[Server] Listening on IP {server_ip}, UDP port {self.udp_port}, and TCP port {self.tcp_port}{Colors.ENDC}")

    def start(self):

        # Start a thread that broadcasts offer messages
        threading.Thread(target=self.send_offers, daemon=True).start()

        # Monitor UDP and TCP sockets for incoming speed test requests from the client
        self.monitor_sockets()

    def monitor_sockets(self):
        sockets_to_monitor = [self.udp_socket, self.tcp_socket]
        while not STOP_EVENT.is_set():  # Keep the main thread running until the server is explicitly stopped
            ready_sockets, _, _ = select.select(sockets_to_monitor, [], [],
                                                1)  # Select returns a list of sockets that are ready for reading

            for sock in ready_sockets:

                # Handle UDP socket
                if sock == self.udp_socket:
                    data, client_address = self.udp_socket.recvfrom(
                        BUFFER_SIZE)  # Extract message and client address from the UDP socket
                    try:
                        # Check that the received message is at least as long as the expected structure
                        if len(data) < struct.calcsize('!IBQ'):
                            continue
                        magic_cookie, msg_type, file_size = struct.unpack('!IBQ', data)  # Parse the message
                        if magic_cookie == MAGIC_COOKIE and msg_type == REQUEST_MESSAGE_TYPE:  # Validate the message
                            # Start a thread that handles the UDP request
                            threading.Thread(target=self.handle_udp_request, args=(client_address, file_size),
                                             daemon=True).start()
                    except Exception as e:
                        print(f"{Colors.FAIL}[Server] Error in UDP handler: {e}{Colors.ENDC}")
                # Handle TCP socket
                elif sock == self.tcp_socket:
                    client_socket, client_address = self.tcp_socket.accept()  # Accept an incoming TCP connection
                    print(
                        f"{Colors.OKLAVENDER}[Server] TCP Connection accepted from {client_address}{Colors.ENDC}")  # Handle the TCP connection in a thread
                    threading.Thread(target=self.handle_TCP_client_connection, args=(client_socket,),
                                     daemon=True).start()

    def handle_udp_request(self, client_address, file_size):
        total_segments = (file_size + BUFFER_SIZE - 1) // BUFFER_SIZE  # Total segments required for the data transfer
        print(f"{Colors.LIGHTBLUE}[Server] Sending UDP data to {client_address}{Colors.ENDC}")
        for segment in range(total_segments):
            try:
                payload = struct.pack('!IBQQ', MAGIC_COOKIE, PAYLOAD_MESSAGE_TYPE, total_segments,
                                      segment)  # Create the packet
                payload += os.urandom(
                    min(BUFFER_SIZE, file_size - segment * BUFFER_SIZE))  # Generate random bytes as payload
                self.udp_socket.sendto(payload, client_address)  # Send the data to the client
                time.sleep(0.01)  # Simulate delay between packets
            except Exception as e:
                print(f"{Colors.FAIL}[Server] Error while sending UDP payload: {e}{Colors.ENDC}")

    def handle_TCP_client_connection(self, client_socket):
        try:
            # Receive the requested file size
            file_size_data = client_socket.recv(BUFFER_SIZE).decode().strip()
            file_size = int(file_size_data)
            print(f"{Colors.OKLAVENDER}[Server] TCP request for {file_size} bytes{Colors.ENDC}")

            # Generate and send the data by simulating the file transfer
            data = os.urandom(file_size)  # Generate random bytes as the file
            client_socket.sendall(data)
            print(f"{Colors.OKLAVENDER}[Server] TCP data transfer complete{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.FAIL}[Server] Error handling client: {e}{Colors.ENDC}")
        finally:
            client_socket.close()

    def send_offers(self):
        # The offer message for the client which consists of UDP and TCP port number for subsequent connections
        offer_msg = struct.pack('!IBHH', MAGIC_COOKIE, OFFER_MESSAGE_TYPE, self.udp_port, self.tcp_port)
        try:
            # Check for user interruptions and use stop_event to signal the thread to exit the loop gracefully
            while not STOP_EVENT.is_set():
                self.udp_socket.sendto(offer_msg, ('255.255.255.255', UDP_BROADCAST_PORT))  # Send the offer message
                print(
                    f"{Colors.OKPEACH}[Server] Sent offer message on UDP port {UDP_BROADCAST_PORT}{Colors.ENDC}")
                time.sleep(1)  # wait 1 second between broadcasts
        except Exception as e:
            print(f"{Colors.FAIL}An error occurred in the broadcast thread: {e}{Colors.ENDC}")


if __name__ == "__main__":
    try:
        server = Server()
        server.start()
    except KeyboardInterrupt:
        print(f"{Colors.WARNING}Shutting down server...{Colors.ENDC}")
        STOP_EVENT.set()
    except Exception as e:
        print(f"{Colors.FAIL}Fatal error: {e}{Colors.ENDC}")
