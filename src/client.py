import socket
import random
import logging
import time
import os
import signal
import sys
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime
from message_handler import MessageHandler, MessageType, Message

@dataclass
class ItemForSale:
    """Data class for items being sold"""
    name: str
    price: float
    reserved: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class SearchRequest:
    """Data class for tracking search requests"""
    item_name: str
    max_price: float
    status: str = "pending"
    offers: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

class ClientUDP_TCP:
    def __init__(self):
        self._setup_logging()
        self.running = True
        self.registered = False
        self.setup_client()

    def _setup_logging(self):
        """Initialize logging configuration"""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'client.log')
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def setup_client(self):
        """Initialize client configuration"""
        try:
            # Initialize UDP socket
            self.client_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.client_udp_socket.settimeout(5)

            # Get server details
            self.server_ip = self.get_server_ip()
            self.server_udp_port = 3000
            self.server_tcp_port = 3001

            # Test server connection
            self.test_server_connection()

            # Bind to any available port
            self.client_udp_socket.bind(('', 0))
            self.client_ip = self.get_client_ip()
            self.client_udp_port = self.client_udp_socket.getsockname()[1]
            self.client_tcp_port = self.get_tcp_port()
            self.name = self.get_user_details()

            # Initialize handlers and data structures
            self.message_handler = MessageHandler()
            self.items_for_sale: Dict[str, ItemForSale] = {}
            self.active_searches: Dict[str, SearchRequest] = {}
            self.response_lock = threading.Lock()
            self.items_lock = threading.Lock()

            # Start listener thread
            self.listener_thread = threading.Thread(target=self.listen_for_messages)
            self.listener_thread.daemon = True
            self.listener_thread.start()

            logging.info(f"Client initialized - UDP port: {self.client_udp_port}, TCP port: {self.client_tcp_port}")

        except Exception as e:
            logging.error(f"Error initializing client: {e}")
            self.cleanup()
            raise

    def get_server_ip(self):
        """Get server IP address from user input"""
        while True:
            try:
                server_ip = input("Enter server IP address (or 'localhost'): ").strip()
                if server_ip.lower() == 'localhost':
                    return '127.0.0.1'
                parts = server_ip.split('.')
                if len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts):
                    return server_ip
                print("Invalid IP address format. Please use format: xxx.xxx.xxx.xxx or 'localhost'")
            except ValueError:
                print("Invalid IP address. Please try again.")

    def test_server_connection(self):
        """Test connection to server"""
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        test_socket.settimeout(5)
        try:
            test_socket.sendto(b"test", (self.server_ip, self.server_udp_port))
            response, _ = test_socket.recvfrom(1024)
            if response.decode() == "ok":
                print(f"Successfully connected to server at {self.server_ip}")
            else:
                raise ConnectionError("Unexpected server response")
        except Exception as e:
            print(f"Warning: Unable to reach server at {self.server_ip}:{self.server_udp_port}")
            print(f"Error: {e}")
            proceed = input("Do you want to continue anyway? (yes/no): ").lower()
            if proceed != 'yes':
                raise ConnectionError("Unable to connect to server")
        finally:
            test_socket.close()

    def get_client_ip(self):
        """Get client IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.server_ip, 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logging.error(f"Error getting client IP: {e}")
            return '127.0.0.1'  # Fallback to localhost

    def get_tcp_port(self):
        """Get TCP port from user input"""
        while True:
            try:
                port = int(input("Enter client TCP port (1024-65535): ").strip())
                if 1024 <= port <= 65535:
                    # Test if port is available
                    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        test_socket.bind(('', port))
                        test_socket.close()
                        return port
                    except OSError:
                        print("Port is already in use. Please choose another port.")
                    finally:
                        test_socket.close()
                else:
                    print("Port must be between 1024 and 65535.")
            except ValueError:
                print("Please enter a valid port number.")
    def get_user_details(self):
        """Get user details from input"""
        while True:
            first_name = input("Enter your first name: ").strip()
            last_name = input("Enter your last name: ").strip()
            if first_name and last_name:
                return f"{first_name} {last_name}"
            print("Both first and last names are required.")

    def register(self):
        """Register client with the server"""
        try:
            if self.registered:
                print("Already registered!")
                return

            rq = str(random.randint(1000, 9999))
            message = self.message_handler.create_message(
                MessageType.REGISTER,
                rq,
                name=self.name,
                ip=self.client_ip,
                udp_port=self.client_udp_port,
                tcp_port=self.client_tcp_port
            )
            logging.info(f"Attempting registration with message: {message}")

            response = self.send_udp_message(message)
            if response:
                if response.startswith(MessageType.REGISTERED.value):
                    self.registered = True
                    print("Successfully registered!")
                elif response.startswith(MessageType.REGISTER_DENIED.value):
                    print(f"Registration denied: {response}")
                else:
                    print(f"Unexpected registration response: {response}")

        except Exception as e:
            logging.error(f"Registration error: {e}")
            print(f"Error during registration: {e}")

    def deregister(self):
        """Deregister client from the server"""
        try:
            if not self.registered:
                print("Not registered!")
                return

            confirm = input("Are you sure you want to deregister? (yes/no): ").lower()
            if confirm != "yes":
                print("Deregistration cancelled.")
                return

            rq = str(random.randint(1000, 9999))
            message = self.message_handler.create_message(
                MessageType.DE_REGISTER,
                rq,
                name=self.name
            )
            logging.info(f"Attempting deregistration with message: {message}")

            response = self.send_udp_message(message)
            if response and response.startswith(MessageType.DE_REGISTERED.value):
                self.registered = False
                print("Successfully deregistered!")
            else:
                print(f"Deregistration failed: {response}")

        except Exception as e:
            logging.error(f"Deregistration error: {e}")
            print(f"Error during deregistration: {e}")

    def add_item_for_sale(self):
        """Add an item for sale"""
        if not self.registered:
            print("You must register first!")
            return

        try:
            item_name = input("Enter item name: ").strip()
            while True:
                try:
                    price = float(input("Enter item price: ").strip())
                    if price > 0:
                        break
                    print("Price must be greater than 0")
                except ValueError:
                    print("Please enter a valid number")

            with self.items_lock:
                self.items_for_sale[item_name] = ItemForSale(
                    name=item_name,
                    price=price
                )
            print(f"Item '{item_name}' added successfully")
            logging.info(f"Added item for sale: {item_name} at price {price}")

        except Exception as e:
            logging.error(f"Error adding item: {e}")
            print(f"Error adding item: {e}")

    def list_items_for_sale(self):
        """List all items for sale"""
        with self.items_lock:
            if not self.items_for_sale:
                print("No items listed for sale")
                return

            print("\nYour items for sale:")
            print("--------------------")
            for item_name, item in self.items_for_sale.items():
                status = "Reserved" if item.reserved else "Available"
                print(f"Item: {item_name}")
                print(f"Price: ${item.price:.2f}")
                print(f"Status: {status}")
                print("--------------------")

    def search_for_item(self):
        """Search for an item to buy"""
        if not self.registered:
            print("You must register first!")
            return

        try:
            item_name = input("Enter item name to search for: ").strip()
            while True:
                try:
                    max_price = float(input("Enter maximum price: ").strip())
                    if max_price > 0:
                        break
                    print("Price must be greater than 0")
                except ValueError:
                    print("Please enter a valid number")

            rq = str(random.randint(1000, 9999))
            message = self.message_handler.create_message(
                MessageType.LOOKING_FOR,
                rq,
                name=self.name,
                item_name=item_name,
                max_price=max_price
            )

            self.active_searches[rq] = SearchRequest(
                item_name=item_name,
                max_price=max_price
            )

            response = self.send_udp_message(message)
            if response:
                logging.info(f"Search response received: {response}")
                self.handle_search_response(response)

        except Exception as e:
            logging.error(f"Error searching for item: {e}")
            print(f"Error searching for item: {e}")

    def handle_search_response(self, response: str):
        """Handle server's response to a search request"""
        try:
            msg = self.message_handler.parse_message(response)
            if not msg:
                return

            if msg.command == MessageType.ERROR:
                print(f"Search error: {msg.params.get('message', 'Unknown error')}")
            elif msg.command == MessageType.NOT_AVAILABLE:
                print(f"Item not available: {msg.params.get('item_name', 'Unknown item')}")
            elif msg.command == MessageType.NOT_FOUND:
                print(f"Item not found within your price range: {msg.params.get('item_name', 'Unknown item')}")
            elif msg.command == MessageType.FOUND:
                item_name = msg.params.get('item_name', 'Unknown item')
                price = msg.params.get('price', 0)
                print(f"Item found: {item_name} at price ${price}")

        except Exception as e:
            logging.error(f"Error handling search response: {e}")
            print("Error processing search response")

    def send_udp_message(self, message: str, max_retries=3, retry_delay=1):
        """Send UDP message to server with retry mechanism"""
        for attempt in range(max_retries):
            try:
                logging.info(f"Sending UDP message (attempt {attempt + 1}): {message}")
                self.client_udp_socket.sendto(message.encode(), (self.server_ip, self.server_udp_port))
                response, _ = self.client_udp_socket.recvfrom(1024)
                response_text = response.decode()
                logging.info(f"Server response: {response_text}")
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

    def listen_for_messages(self):
        """Listen for incoming messages from server"""
        self.client_udp_socket.settimeout(1)  # Short timeout to allow checking self.running
        while self.running:
            try:
                data, _ = self.client_udp_socket.recvfrom(1024)
                message = data.decode()
                logging.info(f"Received message: {message}")

                msg = self.message_handler.parse_message(message)
                if msg:
                    self.handle_incoming_message(msg)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"Error in message listener: {e}")

    def handle_incoming_message(self, msg: Message):
        """Handle incoming messages from server"""
        try:
            if msg.command == MessageType.SEARCH:
                self.handle_search_request(msg)
            elif msg.command == MessageType.NEGOTIATE:
                self.handle_negotiate_request(msg)
            elif msg.command == MessageType.RESERVE:
                self.handle_reserve_request(msg)
            elif msg.command == MessageType.FOUND:
                self.handle_found_notification(msg)
            elif msg.command == MessageType.NOT_FOUND:
                self.handle_not_found_notification(msg)
            elif msg.command == MessageType.NOT_AVAILABLE:
                self.handle_not_available_notification(msg)

        except Exception as e:
            logging.error(f"Error handling incoming message: {e}")

    def handle_search_request(self, msg: Message):
        """Handle search requests from server"""
        try:
            item_name = msg.params["item_name"]
            with self.items_lock:
                if item_name in self.items_for_sale and not self.items_for_sale[item_name].reserved:
                    offer_message = self.message_handler.create_message(
                        MessageType.OFFER,
                        msg.rq_number,
                        name=self.name,
                        item_name=item_name,
                        price=self.items_for_sale[item_name].price
                    )
                    self.send_udp_message(offer_message)
                    logging.info(f"Sent offer for {item_name}")
        except Exception as e:
            logging.error(f"Error handling search request: {e}")

    def handle_negotiate_request(self, msg: Message):
        """Handle negotiation requests from server"""
        try:
            item_name = msg.params["item_name"]
            max_price = msg.params["max_price"]

            print(f"\nNegotiation request received for {item_name}")
            print(f"Buyer's maximum price: ${max_price:.2f}")

            while True:
                response = input("Accept this price? (yes/no): ").lower()
                if response in ['yes', 'no']:
                    break
                print("Please answer 'yes' or 'no'")

            if response == 'yes':
                accept_message = self.message_handler.create_message(
                    MessageType.ACCEPT,
                    msg.rq_number,
                    name=self.name,
                    item_name=item_name,
                    price=max_price
                )
                self.send_udp_message(accept_message)

                # Mark item as reserved
                with self.items_lock:
                    if item_name in self.items_for_sale:
                        self.items_for_sale[item_name].reserved = True
                        self.items_for_sale[item_name].price = max_price
            else:
                refuse_message = self.message_handler.create_message(
                    MessageType.REFUSE,
                    msg.rq_number,
                    item_name=item_name,
                    max_price=max_price
                )
                self.send_udp_message(refuse_message)

        except Exception as e:
            logging.error(f"Error handling negotiate request: {e}")

    def handle_reserve_request(self, msg: Message):
        """Handle reserve requests from server"""
        try:
            item_name = msg.params["item_name"]
            price = msg.params["price"]

            with self.items_lock:
                if item_name in self.items_for_sale:
                    self.items_for_sale[item_name].reserved = True
                    print(f"\nItem '{item_name}' has been reserved at price ${price:.2f}")
                    logging.info(f"Item {item_name} reserved at price {price}")
        except Exception as e:
            logging.error(f"Error handling reserve request: {e}")

    def handle_found_notification(self, msg: Message):
        """Handle found notifications from server"""
        try:
            item_name = msg.params["item_name"]
            price = msg.params["price"]
            print(f"\nItem found: {item_name} at price ${price:.2f}")
            print("You can proceed with the purchase through TCP connection.")
        except Exception as e:
            logging.error(f"Error handling found notification: {e}")

    def handle_not_found_notification(self, msg: Message):
        """Handle not found notifications from server"""
        try:
            item_name = msg.params["item_name"]
            max_price = msg.params["max_price"]
            print(f"\nItem '{item_name}' not found at or below ${max_price:.2f}")
        except Exception as e:
            logging.error(f"Error handling not found notification: {e}")

    def handle_not_available_notification(self, msg: Message):
        """Handle not available notifications from server"""
        try:
            item_name = msg.params["item_name"]
            print(f"\nItem '{item_name}' is not available from any seller")
        except Exception as e:
            logging.error(f"Error handling not available notification: {e}")

    def cleanup(self):
        """Clean up client resources"""
        try:
            self.running = False
            if hasattr(self, 'client_udp_socket'):
                try:
                    self.client_udp_socket.close()
                except:
                    pass
            logging.info("Client cleaned up successfully")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        print("\nSignal received. Shutting down client...")
        self.cleanup()
        sys.exit(0)

    def print_help(self):
        """Print available commands"""
        print("\nAvailable commands:")
        print("  register    - Register with the server")
        print("  deregister - Deregister from the server")
        print("  sell       - Add an item to sell")
        print("  list       - List your items for sale")
        print("  search     - Search for an item to buy")
        print("  help       - Show this help message")
        print("  exit       - Exit the client")

def main():
    """Main entry point for client"""
    try:
        client = ClientUDP_TCP()
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
                elif action == "sell":
                    client.add_item_for_sale()
                elif action == "list":
                    client.list_items_for_sale()
                elif action == "search":
                    client.search_for_item()
                elif action == "help":
                    client.print_help()
                elif action == "exit":
                    print("Exiting client...")
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
            sys.exit(0)

if __name__ == "__main__":
    main()
