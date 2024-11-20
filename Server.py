import socket
import threading
import json
import os
import shlex

class ServerUDP_TCP:
    def __init__(self, udp_port=3000, tcp_port=3001):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind(('0.0.0.0', udp_port))
        print(f"Server UDP listening on port {udp_port}")
        
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(('0.0.0.0', tcp_port))
        self.tcp_socket.listen(5)
        print(f"Server TCP listening on port {tcp_port}")

        self.registration_data = self.load_registrations()

    def load_registrations(self):
        if os.path.exists('registrations.json'):
            with open('registrations.json', 'r') as file:
                return json.load(file)
        return {}

    def save_registrations(self):
        with open('registrations.json', 'w') as file:
            json.dump(self.registration_data, file, indent=4)

    def handle_registration(self, rq, params, client_address):
        try:
            name = params[0]
            client_ip = params[1]
            client_udp_port = int(params[2])
            client_tcp_port = int(params[3])

            if name in self.registration_data:
                response = f"REGISTER-DENIED {rq} {name} is already registered."
                print(f"Registration denied for {name}. Already registered.")
            else:
                self.registration_data[name] = {
                    'ip': client_ip,
                    'udp_port': client_udp_port,
                    'tcp_port': client_tcp_port
                }
                self.save_registrations()
                response = f"REGISTERED {rq}"
                print(f"{name} registered successfully.")
            self.udp_socket.sendto(response.encode(), client_address)
        except (ValueError, IndexError) as e:
            print("Error: Invalid registration parameters.", e)
            self.udp_socket.sendto(f"REGISTER-DENIED {rq} Invalid parameters".encode(), client_address)

    def handle_deregistration(self, rq, params, client_address):
        name = params[0]
        if name in self.registration_data:
            del self.registration_data[name]
            self.save_registrations()
            response = f"DE-REGISTERED {rq} {name}"
            print(f"{name} de-registered successfully.")
        else:
            response = f"DE-REGISTER-DENIED {rq} {name} is not registered."
            print(f"De-registration denied for {name}. Not found.")
        self.udp_socket.sendto(response.encode(), client_address)

    def handle_udp_client(self, data, client_address):
        print(f"Received UDP message from {client_address}: {data.decode()}")
        message = data.decode()
        parts = message.split(maxsplit=2)
        if len(parts) < 2:
            self.udp_socket.sendto("Invalid command".encode(), client_address)
            return
        
        command, rq, *params = parts
        params = shlex.split(params[0]) if params else []

        if command == "REGISTER" and params:
            self.handle_registration(rq, params, client_address)
        elif command == "DE-REGISTER" and params:
            self.handle_deregistration(rq, params, client_address)
        else:
            response = "Invalid command"
            print(f"Invalid command received: {message}")
            self.udp_socket.sendto(response.encode(), client_address)

    def handle_tcp_client(self, client_socket):
        data = client_socket.recv(1024).decode()
        print(f"Received TCP message: {data}")
        response = "TCP response received"
        client_socket.send(response.encode())
        client_socket.close()

    def run(self):
        print("Server running...")
        udp_thread = threading.Thread(target=self.listen_udp)
        tcp_thread = threading.Thread(target=self.listen_tcp)
        udp_thread.start()
        tcp_thread.start()

    def listen_udp(self):
        while True:
            data, client_address = self.udp_socket.recvfrom(1024)
            threading.Thread(target=self.handle_udp_client, args=(data, client_address)).start()

    def listen_tcp(self):
        while True:
            client_socket, client_address = self.tcp_socket.accept()
            threading.Thread(target=self.handle_tcp_client, args=(client_socket,)).start()

if __name__ == "__main__":
    server = ServerUDP_TCP(udp_port=3000, tcp_port=3001)
    server.run()
