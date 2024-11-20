import socket
import threading
import json
import os
import logging
import time
import signal
import sys
from message_handler import MessageHandler

class ServerUDP_TCP:
    def __init__(self, udp_port=3000, tcp_port=3001):
        # Set up logging first
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'server.log')

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = False
        self.setup_sockets()

    def setup_sockets(self):
        """Initialize server sockets with proper error handling"""
        # Close any existing sockets first
        self.cleanup()

        try:
            # UDP Socket setup
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass

            self.udp_socket.bind(('', self.udp_port))
            print(f"Server UDP listening on port {self.udp_port}")

            # TCP Socket setup
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            try:
                self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass

            self.tcp_socket.bind(('', self.tcp_port))
            self.tcp_socket.listen(5)
            print(f"Server TCP listening on port {self.tcp_port}")

        except Exception as e:
            logging.error(f"Failed to initialize server: {e}")
            self.cleanup()
            raise

        self.running = True
        self.message_handler = MessageHandler()
        self.registration_data = self.load_registrations()
        self.pending_requests = {}

        logging.info(f"Server started - UDP port: {self.udp_port}, TCP port: {self.tcp_port}")

    def load_registrations(self):
        try:
            registration_file = os.path.join(os.path.dirname(__file__), 'registrations.json')
            if os.path.exists(registration_file):
                with open(registration_file, 'r') as file:
                    return json.load(file)
            return {}
        except Exception as e:
            logging.error(f"Error loading registrations: {e}")
            return {}

    def save_registrations(self):
        try:
            registration_file = os.path.join(os.path.dirname(__file__), 'registrations.json')
            with open(registration_file, 'w') as file:
                json.dump(self.registration_data, file, indent=4)
            logging.info("Registrations saved successfully")
        except Exception as e:
            logging.error(f"Error saving registrations: {e}")

    def cleanup(self):
        """Clean up server resources"""
        self.running = False

        # Close UDP socket
        if hasattr(self, 'udp_socket'):
            try:
                self.udp_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.udp_socket.close()
            except:
                pass

        # Close TCP socket
        if hasattr(self, 'tcp_socket'):
            try:
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.tcp_socket.close()
            except:
                pass

        logging.info("Server cleaned up")

    def handle_registration(self, rq, params, client_address):
        try:
            name = params["name"]
            if name in self.registration_data:
                response = self.message_handler.create_response(
                    "REGISTER-DENIED", rq, f"{name} is already registered"
                )
                logging.warning(f"Registration denied for {name}. Already registered.")
            else:
                self.registration_data[name] = {
                    'ip': params["ip"],
                    'udp_port': params["udp_port"],
                    'tcp_port': params["tcp_port"]
                }
                self.save_registrations()
                response = self.message_handler.create_response("REGISTERED", rq)
                logging.info(f"{name} registered successfully")

            self.udp_socket.sendto(response.encode(), client_address)
        except Exception as e:
            logging.error(f"Registration error: {e}")
            error_response = self.message_handler.create_response(
                "REGISTER-DENIED", rq, "Internal error"
            )
            self.udp_socket.sendto(error_response.encode(), client_address)

    def handle_deregistration(self, rq, params, client_address):
        try:
            name = params["name"]
            if name in self.registration_data:
                del self.registration_data[name]
                self.save_registrations()
                response = self.message_handler.create_response(
                    "DE-REGISTERED", rq, name
                )
                logging.info(f"{name} de-registered successfully")
            else:
                response = self.message_handler.create_response(
                    "DE-REGISTER-DENIED", rq, f"{name} is not registered"
                )
                logging.warning(f"De-registration denied for {name}. Not found.")

            self.udp_socket.sendto(response.encode(), client_address)
        except Exception as e:
            logging.error(f"De-registration error: {e}")
            error_response = self.message_handler.create_response(
                "DE-REGISTER-DENIED", rq, "Internal error"
            )
            self.udp_socket.sendto(error_response.encode(), client_address)

    def handle_udp_client(self, data, client_address):
        try:
            message = data.decode()
            logging.info(f"Received UDP message from {client_address}: {message}")

            # Handle test message
            if message == "test":
                self.udp_socket.sendto(b"ok", client_address)
                return

            parsed_msg = self.message_handler.parse_message(message)
            if not parsed_msg:
                response = "Invalid message format"
                self.udp_socket.sendto(response.encode(), client_address)
                return

            if parsed_msg.command == "REGISTER":
                self.handle_registration(parsed_msg.rq_number, parsed_msg.params, client_address)
            elif parsed_msg.command == "DE-REGISTER":
                self.handle_deregistration(parsed_msg.rq_number, parsed_msg.params, client_address)
            else:
                response = f"Unknown command: {parsed_msg.command}"
                self.udp_socket.sendto(response.encode(), client_address)
        except Exception as e:
            logging.error(f"Error handling UDP client: {e}")
            try:
                error_response = "Internal server error"
                self.udp_socket.sendto(error_response.encode(), client_address)
            except:
                pass

    def handle_tcp_client(self, client_socket):
        try:
            data = client_socket.recv(1024).decode()
            logging.info(f"Received TCP message: {data}")
            response = "TCP response received"
            client_socket.send(response.encode())
        except Exception as e:
            logging.error(f"TCP client handling error: {e}")
        finally:
            client_socket.close()

    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        print("\nSignal received. Shutting down server...")
        self.cleanup()
        sys.exit(0)

    def listen_udp(self):
        while self.running:
            try:
                data, client_address = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_client,
                               args=(data, client_address)).start()
            except Exception as e:
                if self.running:  # Only log if not shutting down
                    logging.error(f"UDP listening error: {e}")

    def listen_tcp(self):
        while self.running:
            try:
                client_socket, client_address = self.tcp_socket.accept()
                threading.Thread(target=self.handle_tcp_client,
                               args=(client_socket,)).start()
            except Exception as e:
                if self.running:  # Only log if not shutting down
                    logging.error(f"TCP listening error: {e}")

    def run(self):
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print("Server running... (Press Ctrl+C to stop)")
        logging.info("Server running...")

        try:
            udp_thread = threading.Thread(target=self.listen_udp)
            tcp_thread = threading.Thread(target=self.listen_tcp)
            udp_thread.daemon = True
            tcp_thread.daemon = True
            udp_thread.start()
            tcp_thread.start()

            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nShutdown requested...")
        except Exception as e:
            logging.error(f"Server error: {e}")
        finally:
            self.cleanup()

def main():
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            server = ServerUDP_TCP(udp_port=3000, tcp_port=3001)
            server.run()
            break
        except OSError as e:
            if attempt < max_retries - 1:
                print(f"Failed to start server (attempt {attempt + 1}/{max_retries}). "
                      f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Failed to start server after multiple attempts. "
                      "Please check if ports are in use.")
                sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
