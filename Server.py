import socket

class ServerUDP:
    def __init__(self, udp_port=5000, max_clients=10):
        self.udp_port = udp_port
        self.max_clients = max_clients
        self.clients = {}  # Dictionary to store registered clients with their details
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', udp_port))
        print(f"Server started at UDP port {self.udp_port}.")

    def handle_registration(self, data, address):
        # Parse the registration message
        message_parts = data.split(maxsplit=2)
        rq_number = message_parts[1]
        
        # Extract the name and remaining client info
        name_and_ports = message_parts[2].split('"')
        if len(name_and_ports) < 2:
            self.sock.sendto(f"REGISTER-DENIED {rq_number} Malformed registration".encode(), address)
            return
        
        name = name_and_ports[1].strip()
        client_info = name_and_ports[2].strip().split()

        if len(client_info) < 3:
            self.sock.sendto(f"REGISTER-DENIED {rq_number} Malformed registration".encode(), address)
            return

        client_ip = client_info[0]
        udp_socket = client_info[1]
        tcp_socket = client_info[2]

        if name in self.clients:
            self.sock.sendto(f"REGISTER-DENIED {rq_number} Name already in use".encode(), address)
        elif len(self.clients) >= self.max_clients:
            self.sock.sendto(f"REGISTER-DENIED {rq_number} Server full".encode(), address)
        else:
            self.clients[name] = {'ip': client_ip, 'udp_socket': udp_socket, 'tcp_socket': tcp_socket}
            self.sock.sendto(f"REGISTERED {rq_number}".encode(), address)
            print(f"Client '{name}' registered successfully.")

    def handle_deregistration(self, data, address):
        # Debug print to show all clients before de-registration attempt
        print("Current registered clients:", self.clients)

        # Parse the de-registration message (DE-REGISTER RQ# "Name")
        parts = data.split(maxsplit=2)
        rq_number = parts[1]
        name_with_quotes = parts[2]
        
        # Remove quotes and extra whitespace from the name
        name = name_with_quotes.strip('"').strip()
        
        if name in self.clients:
            del self.clients[name]
            print(f"Client '{name}' de-registered successfully.")
            self.sock.sendto(f"DE-REGISTERED {rq_number}".encode(), address)
        else:
            print(f"De-registration failed: '{name}' not found in clients list.")
            self.sock.sendto(f"DE-REGISTER-DENIED {rq_number} Name not found".encode(), address)

    def run(self):
        while True:
            data, address = self.sock.recvfrom(1024)
            data = data.decode()
            if data.startswith("REGISTER"):
                self.handle_registration(data, address)
            elif data.startswith("DE-REGISTER"):
                self.handle_deregistration(data, address)

# To run the server
if __name__ == "__main__":
    server = ServerUDP()
    server.run()
