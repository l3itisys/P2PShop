import socket
import random
import shlex

class ClientUDP_TCP:
    def __init__(self):
        self.client_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_udp_socket.settimeout(5)  # Set 5-second timeout
        self.server_ip = input("Enter server IP address: ")
        self.server_udp_port = 3000
        self.server_tcp_port = 3001

        self.client_udp_socket.bind(('0.0.0.0', 0))  
        self.client_ip = self.get_client_ip()
        self.client_udp_port = self.client_udp_socket.getsockname()[1]
        self.client_tcp_port = int(input("Enter client TCP port: "))  

        first_name = input("Enter your first name: ")
        last_name = input("Enter your last name: ")
        self.name = f"{first_name} {last_name}"

    def get_client_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.server_ip, 1))
            return s.getsockname()[0]
        finally:
            s.close()

    def send_udp_message(self, message):
        try:
            self.client_udp_socket.sendto(message.encode(), (self.server_ip, self.server_udp_port))
            response, _ = self.client_udp_socket.recvfrom(1024)
            print("Server response:", response.decode())
        except socket.timeout:
            print("No response from server within timeout period.")

    def send_tcp_message(self, message):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.connect((self.server_ip, self.server_tcp_port))
            tcp_socket.send(message.encode())
            response = tcp_socket.recv(1024).decode()
            print("Server TCP response:", response)

    def register(self):
        rq = random.randint(1000, 9999)
        message = f'REGISTER {rq} "{self.name}" {self.client_ip} {self.client_udp_port} {self.client_tcp_port}'
        self.send_udp_message(message)

    def deregister(self):
        rq = random.randint(1000, 9999)
        confirmation = input("Are you sure you want to deregister? (yes/no): ")
        if confirmation.lower() == "yes":
            message = f'DE-REGISTER {rq} "{self.name}"'
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
