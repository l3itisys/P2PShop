import socket

class ClientUDP:
    def __init__(self, server_ip, server_port, udp_port, tcp_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.name = input("Enter your name: ").strip()  # Ensure name has no extra spaces
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def register(self):
        rq_number = "1"  # Request number
        # Construct the registration message with consistent quotes around the name
        register_message = f'REGISTER {rq_number} "{self.name}" {self.server_ip} {self.udp_port} {self.tcp_port}'
        print(f"Sending register message: {register_message}")
        self.sock.sendto(register_message.encode(), (self.server_ip, self.server_port))
        response, _ = self.sock.recvfrom(1024)
        print("Server response:", response.decode())

    def deregister(self):
        rq_number = "2"  # Request number
        # Construct the de-registration message with consistent quotes around the name
        deregister_message = f'DE-REGISTER {rq_number} "{self.name}"'
        print(f"Sending de-register message: {deregister_message}")
        self.sock.sendto(deregister_message.encode(), (self.server_ip, self.server_port))
        response, _ = self.sock.recvfrom(1024)
        print("Server response:", response.decode())

    def close(self):
        # Close the UDP socket
        self.sock.close()

# To run the client
if __name__ == "__main__":
    client = ClientUDP(server_ip="127.0.0.1", server_port=5000, udp_port="5001", tcp_port="5002")
    
    # Register the client
    client.register()

    # Ask user if they want to deregister
    choice = input("Do you want to de-register? (yes/no): ").strip().lower()
    
    if choice == 'yes':
        # De-register the client
        client.deregister()
    
    # Close the socket connection
    client.close()
