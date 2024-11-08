import socket
import json

class ClientUDP_TCP:
    def __init__(self):
        # Set up client socket for UDP
        self.client_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_ip = input("Enter server IP address: ")
        self.server_udp_port = int(input("Enter server UDP port: "))
        self.server_tcp_port = int(input("Enter server TCP port: "))
        
        # UDP port for client to bind locally
        self.client_udp_socket.bind(('0.0.0.0', 0))  
        self.client_ip = self.get_client_ip()
        self.client_udp_port = self.client_udp_socket.getsockname()[1]
        self.client_tcp_port = int(input("Enter client TCP port: "))

        # Prompt for first and last name separately
        first_name = input("Enter your first name: ")
        last_name = input("Enter your last name: ")
        self.name = f"{first_name} {last_name}"  # Combine to form full name

    def get_client_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.server_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()

    def send_udp_message(self, message):
        self.client_udp_socket.sendto(message.encode(), (self.server_ip, self.server_udp_port))
        response, _ = self.client_udp_socket.recvfrom(1024)
        print("Server response:", response.decode())

    def send_tcp_message(self, message):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.connect((self.server_ip, self.server_tcp_port))
            tcp_socket.send(message.encode())
            response = tcp_socket.recv(1024).decode()
            print("Server TCP response:", response)

    def register(self):
        message = f'REGISTER "{self.name}" {self.client_ip} {self.client_udp_port} {self.client_tcp_port}'
        self.send_udp_message(message)

    def deregister(self):
        confirmation = input("Are you sure you want to deregister? (yes/no): ")
        if confirmation.lower() == "yes":
            message = f'DE-REGISTER "{self.name}"'
            self.send_udp_message(message)

    def send_tcp_request(self):
        message = input("Enter message to send via TCP: ")
        self.send_tcp_message(message)

    def close(self):
        self.client_udp_socket.close()

if __name__ == "__main__":
    client = ClientUDP_TCP()
    while True:
        action = input("Choose action: 'register', 'deregister', 'tcp', 'exit': ").strip().lower()
        if action == "register":
            client.register()
        elif action == "deregister":
            client.deregister()
        elif action == "tcp":
            client.send_tcp_request()
        elif action == "exit":
            print("Exiting client.")
            client.close()
            break
        else:
            print("Invalid action. Try again.")