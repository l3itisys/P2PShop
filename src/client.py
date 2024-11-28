import socket
import random
import logging
import time
import os
import signal
import sys
import threading
import json
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime
from message_handler import MessageHandler, MessageType, Message

@dataclass
class ItemForSale:
    name: str
    price: float
    reserved: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ActiveSearch:
    item_name: str
    max_price: float
    status: str = "pending"
    offers: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

class ClientUDP_TCP:
    def __init__(self):
        # Basic setup
        self._setup_logging()
        self.running = True
        self.registered = False

        # Thread-safe locks
        self.response_lock = threading.RLock()
        self.items_lock = threading.RLock()
        self.search_lock = threading.RLock()

        # Data storage
        self.items_for_sale: Dict[str, ItemForSale] = {}
        self.active_searches: Dict[str, ActiveSearch] = {}
        self.message_handler = MessageHandler()

        # Network setup
        self.server_ip = None
        self.server_udp_port = None
        self.server_tcp_port = None
        self.client_ip = None
        self.client_udp_port = None
        self.client_tcp_port = None
        self.name = None

        # Initialize client
        self.setup_client()

    def _setup_logging(self):
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'client.log')
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def setup_client(self):
        try:
            # Separate sockets for sending and listening
            self.client_udp_socket_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.client_udp_socket_send.settimeout(5)

            self.client_udp_socket_listen = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.client_udp_socket_listen.settimeout(1)  # For non-blocking listening

            self.server_ip = self.get_server_ip()
            self.server_udp_port = 3000
            self.server_tcp_port = 3001

            self.test_server_connection()

            # Bind the listening socket
            self.client_udp_socket_listen.bind(('', 0))
            self.client_ip = self.get_client_ip()
            self.client_udp_port = self.client_udp_socket_listen.getsockname()[1]
            self.client_tcp_port = self.get_tcp_port()
            self.name = self.get_user_details()

            self.message_handler = MessageHandler()
            self.items_for_sale: Dict[str, ItemForSale] = {}
            self.active_searches: Dict[str, SearchRequest] = {}
            self.response_lock = threading.Lock()
            self.items_lock = threading.Lock()

            self.listener_thread = threading.Thread(target=self.listen_for_messages)
            self.listener_thread.daemon = True
            self.listener_thread.start()

            self.load_items()
            logging.info(f"Client initialized - UDP port: {self.client_udp_port}, TCP port: {self.client_tcp_port}")

        except Exception as e:
            logging.error(f"Error initializing client: {e}")
            self.cleanup()
            raise

    def get_server_ip(self):
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
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((self.server_ip, 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logging.error(f"Error getting client IP: {e}")
            return '127.0.0.1'

    def get_tcp_port(self):
        while True:
            try:
                port = int(input("Enter client TCP port (1024-65535): ").strip())
                if 1024 <= port <= 65535:
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
        while True:
            first_name = input("Enter your first name: ").strip()
            last_name = input("Enter your last name: ").strip()
            if first_name and last_name:
                return f"{first_name} {last_name}"
            print("Both first and last names are required.")

    def save_items(self):
        try:
            items_file = os.path.join(os.path.dirname(__file__), f'items_{self.name}.json')
            with self.items_lock:
                items_data = {
                    name: {"price": item.price, "reserved": item.reserved}
                    for name, item in self.items_for_sale.items()
                }
            with open(items_file, 'w') as f:
                json.dump(items_data, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving items: {e}")

    def load_items(self):
        try:
            items_file = os.path.join(os.path.dirname(__file__), f'items_{self.name}.json')
            if os.path.exists(items_file):
                with open(items_file, 'r') as f:
                    items_data = json.load(f)
                with self.items_lock:
                    self.items_for_sale = {
                        name: ItemForSale(name=name, price=data["price"], reserved=data["reserved"])
                        for name, data in items_data.items()
                    }
        except Exception as e:
            logging.error(f"Error loading items: {e}")

    def register(self):
        try:
            if self.registered:
                print("Already registered!")
                return True

            rq = str(random.randint(1000, 9999))
            message = self.message_handler.create_message(
                MessageType.REGISTER,
                rq,
                name=self.name,
                ip=self.client_ip,
                udp_port=self.client_udp_port,
                tcp_port=self.client_tcp_port
            )

            response = self.send_udp_message(message)
            if response:
                msg = self.message_handler.parse_message(response)
                if msg and msg.command == MessageType.REGISTERED:
                    self.registered = True
                    print("Successfully registered!")
                    return True
                elif msg and msg.command == MessageType.REGISTER_DENIED:
                    if "already registered" in msg.params.get('reason', ''):
                        self.registered = True
                        print("Already registered! You can proceed with other commands.")
                        return True
                    else:
                        print(f"Registration denied: {msg.params.get('reason', 'Unknown reason')}")
                else:
                    print(f"Unexpected registration response: {response}")
            return self.registered

        except Exception as e:
            logging.error(f"Registration error: {e}")
            print(f"Error during registration: {e}")

    def deregister(self):
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
            self.save_items()
            logging.info(f"Added item for sale: {item_name} at price {price}")

        except Exception as e:
            logging.error(f"Error adding item: {e}")
            print(f"Error adding item: {e}")

    def list_items_for_sale(self):
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
        """Updated search implementation"""
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

            # Create active search record
            with self.search_lock:
                self.active_searches[rq] = ActiveSearch(
                    item_name=item_name,
                    max_price=max_price
                )

            # Send search request
            response = self.send_udp_message(message)
            if response:
                msg = self.message_handler.parse_message(response)
                if msg and msg.command == MessageType.SEARCH_ACK:
                    print(f"Search request for {item_name} acknowledged. Waiting for results...")
                    logging.info(f"Search request {rq} acknowledged by server")
                elif msg and msg.command == MessageType.ERROR:
                    print(f"Search error: {msg.params.get('message', 'Unknown error')}")
                    with self.search_lock:
                        if rq in self.active_searches:
                            del self.active_searches[rq]
                else:
                    print(f"Unexpected response: {response}")

        except Exception as e:
            logging.error(f"Error searching for item: {e}")
            print(f"Error during search: {e}")

    def handle_search_request(self, msg: Message):
        """Updated handler for incoming search requests (as seller)"""
        try:
            item_name = msg.params["item_name"]

            with self.items_lock:
                matching_items = []
                for name, item in self.items_for_sale.items():
                    if (item_name.lower() in name.lower() or
                        name.lower() in item_name.lower()) and not item.reserved:
                        matching_items.append((name, item))

                for name, item in matching_items:
                    offer_message = self.message_handler.create_message(
                        MessageType.OFFER,
                        msg.rq_number,
                        name=self.name,
                        item_name=name,
                        price=item.price
                    )
                    self.send_udp_message_no_response(offer_message)
                    logging.info(f"Sent offer for {name} at price {item.price}")

        except Exception as e:
            logging.error(f"Error handling search request: {e}")


    def handle_negotiate_request(self, msg: Message):
        """Updated handler for price negotiation requests"""
        try:
            item_name = msg.params["item_name"]
            max_price = msg.params["max_price"]

            with self.items_lock:
                if item_name not in self.items_for_sale:
                    logging.warning(f"Negotiation requested for non-existent item: {item_name}")
                    return

                item = self.items_for_sale[item_name]
                if item.reserved:
                    logging.warning(f"Negotiation requested for reserved item: {item_name}")
                    return

                print(f"\nNegotiation request received for '{item_name}'")
                print(f"Buyer's maximum price: ${max_price:.2f}")
                print(f"Your current price: ${item.price:.2f}")

                while True:
                    response = input("Accept buyer's price? (yes/no): ").lower()
                    if response in ['yes', 'no']:
                        break
                    print("Please answer 'yes' or 'no'")

                if response == 'yes':
                    # Accept the negotiated price
                    item.price = max_price
                    item.reserved = True
                    self.save_items()

                    accept_message = self.message_handler.create_message(
                        MessageType.ACCEPT,
                        msg.rq_number,
                        name=self.name,
                        item_name=item_name,
                        price=max_price
                    )
                    self.send_udp_message_no_response(accept_message)
                    logging.info(f"Accepted negotiation for {item_name} at {max_price}")
                    print(f"Item price updated and reserved at ${max_price:.2f}")
                else:
                    # Reject the negotiation
                    refuse_message = self.message_handler.create_message(
                        MessageType.REFUSE,
                        msg.rq_number,
                        item_name=item_name,
                        max_price=max_price
                    )
                    self.send_udp_message_no_response(refuse_message)
                    logging.info(f"Refused negotiation for {item_name} at {max_price}")
                    print("Negotiation refused")

        except Exception as e:
            logging.error(f"Error handling negotiate request: {e}")

    def handle_reserve_request(self, msg: Message):
        """Updated handler for item reservation"""
        try:
            item_name = msg.params["item_name"]
            price = msg.params["price"]

            with self.items_lock:
                if item_name not in self.items_for_sale:
                    logging.warning(f"Reserve request for non-existent item: {item_name}")
                    return

                item = self.items_for_sale[item_name]
                if item.reserved:
                    logging.warning(f"Reserve request for already reserved item: {item_name}")
                    return

                item.reserved = True
                item.price = price
                self.save_items()

                print(f"\nItem '{item_name}' has been reserved at price ${price:.2f}")
                logging.info(f"Item {item_name} reserved at price {price}")

        except Exception as e:
            logging.error(f"Error handling reserve request: {e}")

    def handle_found_notification(self, msg: Message):
        """Handle notifications about found items"""
        try:
            item_name = msg.params["item_name"]
            price = msg.params["price"]

            with self.search_lock:
                # Update active search status
                search_entry = next(
                    (search for search in self.active_searches.values()
                     if search.item_name == item_name),
                    None
                )
                if search_entry:
                    search_entry.status = "found"
                    search_entry.found_price = price

            print(f"\nItem found: {item_name} at price ${price:.2f}")
            print("You can proceed with the purchase through TCP connection.")
            logging.info(f"Found notification received for {item_name} at {price}")

        except Exception as e:
            logging.error(f"Error handling found notification: {e}")

    def handle_not_found_notification(self, msg: Message):
        """Handle notifications about items not found"""
        try:
            item_name = msg.params["item_name"]
            max_price = msg.params["max_price"]

            with self.search_lock:
                # Update active search status
                search_entry = next(
                    (search for search in self.active_searches.values()
                     if search.item_name == item_name),
                    None
                )
                if search_entry:
                    search_entry.status = "not_found"

            print(f"\nItem '{item_name}' not found at or below ${max_price:.2f}")
            logging.info(f"Not found notification received for {item_name}")

        except Exception as e:
            logging.error(f"Error handling not found notification: {e}")

    def handle_not_available_notification(self, msg: Message):
        """Handle notifications about unavailable items"""
        try:
            item_name = msg.params["item_name"]

            with self.search_lock:
                # Update active search status
                search_entry = next(
                    (search for search in self.active_searches.values()
                     if search.item_name == item_name),
                    None
                )
                if search_entry:
                    search_entry.status = "expired"

            print(f"\nItem '{item_name}' is not available from any seller")
            logging.info(f"Not available notification received for {item_name}")

        except Exception as e:
            logging.error(f"Error handling not available notification: {e}")

    def handle_incoming_message(self, msg: Message):
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
            else:
                logging.info(f"Unhandled message type: {msg.command}")
        except Exception as e:
            logging.error(f"Error handling incoming message: {e}")

    def listen_for_messages(self):
        self.client_udp_socket_listen.settimeout(1)
        while self.running:
            try:
                data, _ = self.client_udp_socket_listen.recvfrom(1024)
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

    def send_udp_message(self, message: str, max_retries=3, retry_delay=1):
        for attempt in range(max_retries):
            try:
                print(f"Sending message to server (attempt {attempt + 1}): {message}")
                logging.info(f"Sending UDP message (attempt {attempt + 1}): {message}")
                self.client_udp_socket_send.sendto(message.encode(), (self.server_ip, self.server_udp_port))
                print("Waiting for response from server...")
                response, _ = self.client_udp_socket_send.recvfrom(1024)
                response_text = response.decode()
                print(f"Received response from server: {response_text}")
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

    def send_udp_message_no_response(self, message: str):
        try:
            logging.info(f"Sending UDP message: {message}")
            self.client_udp_socket_send.sendto(message.encode(), (self.server_ip, self.server_udp_port))
        except Exception as e:
            logging.error(f"Error sending UDP message: {e}")

    def cleanup(self):
        try:
            self.running = False
            self.save_items()
            if hasattr(self, 'client_udp_socket_send'):
                try:
                    self.client_udp_socket_send.close()
                except:
                    pass
            if hasattr(self, 'client_udp_socket_listen'):
                try:
                    self.client_udp_socket_listen.close()
                except:
                    pass
            logging.info("Client cleaned up successfully")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def signal_handler(self, signum, frame):
        print("\nSignal received. Shutting down client...")
        self.cleanup()
        sys.exit(0)

    def print_help(self):
        print("\nAvailable commands:")
        print("  register    - Register with the server")
        print("  deregister - Deregister from the server")
        print("  sell       - Add an item to sell")
        print("  list       - List your items for sale")
        print("  search     - Search for an item to buy")
        print("  help       - Show this help message")
        print("  exit       - Exit the client")

def main():
    """Keep existing main function unchanged"""
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
