import socket
import random
import logging
import time
import os
import signal
import sys
from message_handler import MessageHandler

class ClientUDP_TCP:
    def __init__(self):
        # Set up logging first
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'client.log')

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        try:
            # Socket initialization
            self.client_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.client_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.client_udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass

            self.client_udp_socket.settimeout(5)  # 5 second timeout

            # Get server details
            self.server_ip = self.get_server_ip()
            self.server_udp_port = 3000
            self.server_tcp_port = 3001

            # Test server connection
            self.test_server_connection()

            # Bind to random port
            self.client_udp_socket.bind(('', 0))
            self.client_ip = self.get_client_ip()
            self.client_udp_port = self.client_udp_socket.getsockname()[1]

            # Get TCP port
            self.client_tcp_port = self.get_tcp_port()

            # Get user details
            self.name = self.get_user_details()

            self.message_handler = MessageHandler()
            self.pending_requests = {}
            self.running = True

            logging.info(f"Client initialized - UDP port: {self.client_udp_port}, "
                        f"TCP port: {self.client_tcp_port}")

        except Exception as e:
            logging.error(f"Error initializing client: {e}")
            raise

    def get_server_ip(self):
        """Get and validate server IP address"""
        while True:
            try:
                server_ip = input("Enter server IP address (or 'localhost'): ").strip()
                if server_ip.lower() == 'localhost':
                    return '127.0.0.1'
                # Validate IP address format
                parts = server_ip.split('.')
                if len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts):
                    return server_ip
                print("Invalid IP address format. Please use format: xxx.xxx.xxx.xxx or 'localhost'")
            except ValueError:
                print("Invalid IP address. Please try again.")

    def test_server_connection(self):
        """Test connection to server"""
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_socket.settimeout(2)
        try:
            test_socket.sendto(b"test", (self.server_ip, self.server_udp_port))
            response, _ = test_socket.recvfrom(1024)
            print(f"Successfully connected to server at {self.server_ip}")
        except Exception as e:
            print(f"Warning: Unable to reach server at {self.server_ip}:{self.server_udp_port}")
            print(f"Error: {e}")
            proceed = input("Do you want to continue anyway? (yes/no): ").lower()
            if proceed != 'yes':
                raise ConnectionError("Unable to connect to server")
        finally:
            test_socket.close()

    def get_client_ip(self):
        """Get the client's local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.server_ip, 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logging.error(f"Error getting client IP: {e}")
            raise

    def get_tcp_port(self):
        """Get and validate TCP port"""
        while True:
            try:
                port_input = input("Enter client TCP port (1024-65535): ").strip()
                port = int(port_input)
                if 1024 <= port <= 65535:
                    return port
                print("Port must be between 1024 and 65535.")
            except ValueError:
                print("Please enter a valid port number.")

    def get_user_details(self):
        """Get and validate user details"""
        while True:
            first_name = input("Enter your first name: ").strip()
            last_name = input("Enter your last name: ").strip()
            if first_name and last_name:
                return f"{first_name} {last_name}"
            print("Both first and last names are required.")

    def cleanup(self):
        """Clean up client resources"""
        self.running = False
        try:
            if hasattr(self, 'client_udp_socket'):
                self.client_udp_socket.close()
            logging.info("Client cleaned up successfully")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        print("\nSignal received. Shutting down client...")
        self.cleanup()
        sys.exit(0)

    def send_udp_message(self, message):
        """Send UDP message to server with retry logic"""
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                logging.info(f"Sending UDP message (attempt {attempt + 1}): {message}")
                self.client_udp_socket.sendto(message.encode(),
                                            (self.server_ip, self.server_udp_port))
                response, _ = self.client_udp_socket.recvfrom(1024)
                response_text = response.decode()
                logging.info(f"Server response: {response_text}")
                print("Server response:", response_text)
                return response_text
            except socket.timeout:
                if attempt < max_retries - 1:
                    logging.warning(f"Timeout, retrying in {retry_delay} seconds...")
                    print(f"No response, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error("Server not responding after multiple attempts")
                    print("Server not responding after multiple attempts")
            except Exception as e:
                logging.error(f"Error sending UDP message: {e}")
                print(f"Error sending message: {e}")
                break
        return None

    def register(self):
        """Send registration request to server"""
        try:
            rq = str(random.randint(1000, 9999))
            message = f'REGISTER {rq} "{self.name}" {self.client_ip} {self.client_udp_port} {self.client_tcp_port}'
            self.pending_requests[rq] = {
                "type": "REGISTER",
                "timestamp": time.time()
            }
            logging.info(f"Attempting registration with message: {message}")
            return self.send_udp_message(message)
        except Exception as e:
            logging.error(f"Registration error: {e}")
            print(f"Error during registration: {e}")

    def deregister(self):
        """Send deregistration request to server"""
        try:
            confirmation = input("Are you sure you want to deregister? (yes/no): ").lower()
            if confirmation == "yes":
                rq = str(random.randint(1000, 9999))
                message = f'DE-REGISTER {rq} "{self.name}"'
                self.pending_requests[rq] = {
                    "type": "DE-REGISTER",
                    "timestamp": time.time()
                }
                logging.info(f"Attempting deregistration with message: {message}")
                return self.send_udp_message(message)
            else:
                logging.info("Deregistration cancelled by user")
                print("Deregistration cancelled.")
        except Exception as e:
            logging.error(f"Deregistration error: {e}")
            print(f"Error during deregistration: {e}")

    def send_tcp_message(self, message):
        """Send TCP message to server"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                tcp_socket.connect((self.server_ip, self.server_tcp_port))
                logging.info(f"Sending TCP message: {message}")
                tcp_socket.send(message.encode())
                response = tcp_socket.recv(1024).decode()
                logging.info(f"Server TCP response: {response}")
                print("Server TCP response:", response)
                return response
        except Exception as e:
            logging.error(f"Error sending TCP message: {e}")
            print(f"Error sending TCP message: {e}")

    def send_tcp_request(self):
        """Handle TCP message input and sending"""
        message = input("Enter message to send via TCP: ")
        return self.send_tcp_message(message)

    def print_help(self):
        """Print available commands"""
        print("\nAvailable commands:")
        print("  register    - Register with the server")
        print("  deregister - Deregister from the server")
        print("  tcp        - Send a TCP message")
        print("  help       - Show this help message")
        print("  exit       - Exit the client")

def main():
    try:
        client = ClientUDP_TCP()

        # Set up signal handlers
        signal.signal(signal.SIGINT, client.signal_handler)
        signal.signal(signal.SIGTERM, client.signal_handler)

        client.print_help()

        while client.running:
            try:
                action = input("\nEnter command (or 'help' for commands): ").strip().lower()

                if action == "register":
                    client.register()
                elif action == "deregister":
                    client.deregister()
                elif action == "tcp":
                    client.send_tcp_request()
                elif action == "help":
                    client.print_help()
                elif action == "exit":
                    print("Exiting client.")
                    client.cleanup()
                    break
                else:
                    print("Invalid command. Type 'help' for available commands.")

            except Exception as e:
                logging.error(f"Error processing action {action}: {e}")
                print(f"Error: {e}")

    except KeyboardInterrupt:
        print("\nClient shutdown requested...")
    except Exception as e:
        print(f"Client error: {e}")
        logging.error(f"Client error: {e}")
    finally:
        if 'client' in locals():
            client.cleanup()

if __name__ == "__main__":
    main()
