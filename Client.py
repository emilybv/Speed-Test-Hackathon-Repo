class Client:
    def __init__(self):
        self.state = "STARTUP"
        self.server_address = None
        self.udp_port = None
        self.tcp_port = None
        self.file_size = None
        self.num_tcp_connections = None
        self.num_udp_connections = None

    def startup(self):
        """ Get user input for file size and number of TCP and UDP connections."""
        self.file_size = int(input("Enter file size (in bytes): "))
        self.num_tcp_connections = int(input("Enter number of TCP connections: "))
        self.num_udp_connections = int(input("Enter number of UDP connections: "))
        self.state = "LOOKING_FOR_SERVER"
