import socket
import struct
import threading
import time
import select

# Constants
UDP_BROADCAST_PORT = 54321

# Create a threading event to signal when to stop the thread
STOP_EVENT = threading.Event()

# ANSI color codes
class Colors:
    OKPINK = '\033[38;5;206m'  # Soft Pink
    OKLAVENDER = '\033[38;5;183m'  # Lavender
    OKPEACH = '\033[38;5;216m'  # Peach
    OKCYAN = '\033[96m'
    LIGHTBLUE = '\033[38;5;152m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class Client:
    MAGIC_COOKIE = 0xabcddcba
    MESSAGE_TYPE_OFFER = 0x2
    MESSAGE_TYPE_REQUEST = 0x3
    MESSAGE_TYPE_PAYLOAD = 0x4
    PACKET_SIZE = 1024

    def __init__(self):
        """
        Initializes the client
        """
        self.udp_broadcast_port = UDP_BROADCAST_PORT
        self.udp_socket = None

    def start(self):
        """
        The function is main entry point for the client.
        It listens for offers, takes user input for the number of connections and file size,
        and starts threads to handle both TCP and UDP transfers
        :return: none
        """
        while not STOP_EVENT.is_set():
            self.setup_udp_socket()  # set up the udp socket
            print(f"{Colors.OKPEACH}[Client] Client started, listening for offer requests...{Colors.ENDC}")
            try:
                # lister for offers from the server
                server_ip, server_tcp_port, udp_port = self.listen_for_offers()
            except Exception as e:
                print(f"{Colors.FAIL}[Client] Error listening for offers: {e}{Colors.ENDC}")
                return

            print(f"{Colors.OKPEACH}[Client] Received offer from {server_ip}{Colors.ENDC}")

            try:
                num_tcp_connections = int(input(f"{Colors.OKLAVENDER}Enter the number of TCP connections: {Colors.ENDC}").strip())
                num_udp_connections = int(input(f"{Colors.OKLAVENDER}Enter the number of UDP connections: {Colors.ENDC}").strip())
                file_size = int(input(f"{Colors.OKLAVENDER}Enter the file size: {Colors.ENDC}").strip())
            except ValueError:
                print(f"{Colors.OKPINK}[Client] Invalid input. Please enter valid integers for connections and file size.{Colors.ENDC}")
                continue

            threads = []  # store the threads
            # start the tcp connection
            for i in range(num_tcp_connections):
                thread = threading.Thread(target=self.handle_tcp_connection, args=(server_ip, server_tcp_port, file_size, i + 1))
                threads.append(thread)
                thread.start()

            # start the udp connection
            for i in range(num_udp_connections):
                thread = threading.Thread(target=self.handle_udp_connection, args=(server_ip, udp_port, file_size, i + 1))
                threads.append(thread)
                thread.start()

            # wait for all threads
            for thread in threads:
                thread.join()

            print(f"{Colors.OKCYAN}[Client] All transfers complete.{Colors.ENDC}")

    def setup_udp_socket(self):
        """
        Sets up the UDP socket to receive broadcasts on the specified port
        :return: none
        """
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(('', self.udp_broadcast_port))
        except Exception as e:
            print(f"{Colors.FAIL}[Client] Failed to set up UDP socket: {e}{Colors.ENDC}")
            raise

    def listen_for_offers(self):
        """
        Listens for incoming offer messages on the UDP socket, extracts the server's IP,
        TCP port, and UDP port from the packets.
        :return:
         server_ip : ip address of the server
         tcp_port: tcp port for communication
         udp_port: udp port for communication
        """
        while not STOP_EVENT.is_set():
            # use select to wait for readable sockets
            ready_sockets, _, _ = select.select([self.udp_socket], [], [], None)
            for sock in ready_sockets:  # loop over the ready sockets
                try:
                    data, addr = sock.recvfrom(1024)  # receive the incoming data and get address
                    # unpack the received data
                    magic_cookie, msg_type, udp_port, tcp_port = struct.unpack('!IBHH', data)
                    # check if it's matches
                    if magic_cookie == self.MAGIC_COOKIE and msg_type == self.MESSAGE_TYPE_OFFER:
                        return addr[0], tcp_port, udp_port
                except struct.error:  # if data is not structured as expected
                    print(f"{Colors.WARNING}[Client] Invalid offer packet received.{Colors.ENDC}")
                except Exception as e:  # any other exceptions
                    print(f"{Colors.FAIL}[Client] Error processing offer: {e}{Colors.ENDC}")
        raise Exception("No offers received.")  # if no valid offer

    def handle_tcp_connection(self, server_ip, server_tcp_port, file_size, connection_number):
        """
        Establishes a TCP connection with the server, sends the file size, and receives the file data in chunks.
        :param server_ip: ip address of the server
        :param server_tcp_port: tcp port of the server
        :param file_size: size of the file
        :param connection_number: number of the currect connection
        :return: none
        """
        try:
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_socket.connect((server_ip, server_tcp_port))
            tcp_socket.sendall(f"{file_size}\n".encode())  # send the file size to the server
        except Exception as e:
            print(f"{Colors.FAIL}[Client] Error establishing TCP connection #{connection_number}: {e}{Colors.ENDC}")
            return

        # start the timer
        start_time = time.perf_counter()
        received_data = 0  # track the amount of received data
        try:
            # receive data in chunks from the server until the entire file is transferred
            while received_data < file_size:
                chunk = tcp_socket.recv(self.PACKET_SIZE)
                if not chunk:
                    break
                received_data += len(chunk)
        except Exception as e:
            print(f"{Colors.FAIL}[Client] Error during TCP data transfer #{connection_number}: {e}{Colors.ENDC}")
        finally:
            # if transmission complete
            end_time = time.perf_counter()
            total_time = end_time - start_time
            total_time = max(total_time, 1e-6)  # Avoid zero or negative timing
            # calculate the transfer sped
            speed = received_data * 8 / total_time if total_time > 0 else 0
            print(f"{Colors.LIGHTBLUE}[Client] TCP transfer #{connection_number} finished, total time: {total_time:.4f} seconds, total speed: {speed:.2f} bits/second{Colors.ENDC}")
            tcp_socket.close()

    def handle_udp_connection(self, server_ip, udp_port, file_size, connection_number):
        """
        Establishes a UDP connection with the server, sends a file transfer request, and receives data in segments.
        :param server_ip: ip address of the server
        :param udp_port: udp port of the server
        :param file_size:size of the file
        :param connection_number: number of the current connection
        :return: none
        """
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # create the request message
            request_message = struct.pack('!IBQ', self.MAGIC_COOKIE, self.MESSAGE_TYPE_REQUEST, file_size)
            udp_socket.sendto(request_message, (server_ip, udp_port))  # send request with udp
        except Exception as e:
            print(f"{Colors.FAIL}[Client] Error sending UDP request #{connection_number}: {e}{Colors.ENDC}")
            udp_socket.close()
            return

        # start the timer
        start_time = time.time()
        received_data = 0  # track the amount of received data
        expected_segments = None

        # set timeout to udp socket in order prevent from blocking indefinitely
        udp_socket.settimeout(1)
        try:
            # receive data from the server in segment
            while True:
                ready_sockets, _, _ = select.select([udp_socket], [], [], 1)
                if not ready_sockets:
                    break

                for sock in ready_sockets:
                    data, _ = sock.recvfrom(2048)  # receive data from the socket
                    if len(data) < struct.calcsize('!IBQQ'):
                        continue

                    # unpack the udp packet
                    magic_cookie, msg_type, total_segments, current_segment = struct.unpack('!IBQQ', data[:21])
                    if magic_cookie != self.MAGIC_COOKIE or msg_type != self.MESSAGE_TYPE_PAYLOAD:
                        continue

                    if expected_segments is None:
                        expected_segments = total_segments

                    received_data += len(data[21:])
        except socket.timeout:  # handle timeout
            print(f"{Colors.WARNING}[Client] UDP connection #{connection_number} timed out.{Colors.ENDC}")
        except Exception as e:  # handle any other errors
            print(f"{Colors.FAIL}[Client] Error during UDP data transfer #{connection_number}: {e}{Colors.ENDC}")
        finally:
            end_time = time.time()
            total_time = end_time - start_time
            # calculate the percentage of the received file
            percentage_received = (received_data / file_size) * 100 if file_size else 0
            # calculate the transfet speed
            speed = received_data * 8 / total_time if total_time > 0 else 0
            print(f"{Colors.LIGHTBLUE}[Client] UDP transfer #{connection_number} finished, total time: {total_time:.4f} seconds, total speed: {speed:.2f} bits/second, percentage of packets received successfully: {percentage_received:.2f}%{Colors.ENDC}")
            udp_socket.close()

if __name__ == "__main__":
    try:
        client = Client()
        client.start()
    except KeyboardInterrupt:
        print(f"{Colors.WARNING}\nShutting down client...{Colors.ENDC}")
        STOP_EVENT.set()
    except Exception as e:
        print(f"{Colors.FAIL}Fatal error: {e}{Colors.ENDC}")
