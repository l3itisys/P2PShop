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
    rq_number: str = ""
    found_price: Optional[float] = None

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
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        console.setFormatter(formatter)
        logging.getLogger('').addHandler(console)

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
            self.active_searches: Dict[str, ActiveSearch] = {}
            self.response_lock = threading.Lock()
            self.items_lock = threading.Lock()

            self.listener_thread = threading.Thread(target=self.listen_for_messages)
            self.listener_thread.daemon = True
            self.listener_thread.start()

            self.setup_tcp_server()

            self.load_items()
            logging.info(f"Client initialized - UDP port: {self.client_udp_port}, TCP port: {self.client_tcp_port}")

        except Exception as e:
            logging.error(f"Error initializing client: {e}")
            self.cleanup()
            raise

    def get_server_ip(self):
        while True:
            server_ip = input("Enter server IP address (or 'localhost'): ").strip()
            if server_ip.lower() == 'localhost':
                return '127.0.0.1'
            else:
                return server_ip

    def test_server_connection(self):
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_socket.settimeout(2)
            test_socket.sendto(b"test", (self.server_ip, 3000))
            response, _ = test_socket.recvfrom(1024)
            if response.decode() == "ok":
                print(f"Successfully connected to server at {self.server_ip}")
            else:
                print(f"Failed to receive proper response from server at {self.server_ip}")
                sys.exit(1)
        except Exception as e:
            print(f"Failed to connect to server at {self.server_ip}: {e}")
            sys.exit(1)
        finally:
            test_socket.close()

    def get_client_ip(self):
        return socket.gethostbyname(socket.gethostname())

    def get_tcp_port(self):
        while True:
            try:
                port = int(input("Enter client TCP port (1024-65535): ").strip())
                if 1024 <= port <= 65535:
                    return port
                else:
                    print("Port must be between 1024 and 65535.")
            except ValueError:
                print("Invalid port number. Please enter a valid integer.")

    def get_user_details(self):
        first_name = input("Enter your first name: ").strip()
        last_name = input("Enter your last name: ").strip()
        return f"{first_name} {last_name}"

    def setup_tcp_server(self):
        try:
            self.tcp_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_server_socket.bind(('', self.client_tcp_port))
            self.tcp_server_socket.listen(5)
            self.tcp_server_socket.settimeout(1)
            threading.Thread(target=self.accept_tcp_connections, daemon=True).start()
            logging.info(f"TCP server listening on port {self.client_tcp_port}")
        except Exception as e:
            logging.error(f"Error setting up TCP server: {e}")
            print(f"Error setting up TCP server: {e}")

    def accept_tcp_connections(self):
        while self.running:
            try:
                client_socket, client_address = self.tcp_server_socket.accept()
                threading.Thread(target=self.handle_tcp_client, args=(client_socket, client_address), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"Error accepting TCP connection: {e}")

    def handle_tcp_client(self, client_socket: socket.socket, client_address: tuple):
        try:
            # Handle TCP connection from server
            data = client_socket.recv(1024).decode()
            msg = self.message_handler.parse_message(data)
            if msg and msg.command == MessageType.INFORM_REQ:
                # Send INFORM_RES with required information
                name = self.name
                cc_number = input("Enter your credit card number: ").strip()
                cc_exp_date = input("Enter your credit card expiration date (MM/YY): ").strip()
                address = input("Enter your address: ").strip()
                inform_res = self.message_handler.create_message(
                    MessageType.INFORM_RES,
                    msg.rq_number,
                    name=name,
                    cc_number=cc_number,
                    cc_exp_date=cc_exp_date,
                    address=address
                )
                client_socket.sendall(inform_res.encode())
                logging.info("Sent INFORM_RES to server")
                # Wait for transaction result
                response = client_socket.recv(1024).decode()
                msg = self.message_handler.parse_message(response)
                if msg and msg.command == MessageType.TRANSACTION_SUCCESS:
                    print("Transaction successful!")
                elif msg and msg.command == MessageType.TRANSACTION_FAILED:
                    print(f"Transaction failed: {msg.params['reason']}")
                elif msg and msg.command == MessageType.SHIPPING_INFO:
                    # As seller, receive buyer's shipping info
                    print(f"Ship item to {msg.params['name']} at address: {msg.params['address']}")
                client_socket.close()
            else:
                logging.error(f"Unexpected TCP message: {data}")
                client_socket.close()
        except Exception as e:
            logging.error(f"Error handling TCP client: {e}")
            client_socket.close()

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
                    reason = msg.params.get('reason', '')
                    print(f"Registration denied: {reason}")
                else:
                    print(f"Unexpected registration response: {response}")
            return self.registered

        except Exception as e:
            logging.error(f"Registration error: {e}")
            print(f"Error during registration: {e}")

    def deregister(self):
        try:
            if not self.registered:
                print("You are not registered.")
                return False

            rq = str(random.randint(1000, 9999))
            message = self.message_handler.create_message(
                MessageType.DE_REGISTER,
                rq,
                name=self.name
            )

            response = self.send_udp_message(message)
            if response:
                msg = self.message_handler.parse_message(response)
                if msg and msg.command == MessageType.DE_REGISTERED:
                    self.registered = False
                    print("Successfully de-registered!")
                    return True
                else:
                    print(f"Unexpected de-registration response: {response}")
            return not self.registered

        except Exception as e:
            logging.error(f"De-registration error: {e}")
            print(f"Error during de-registration: {e}")

    def add_item_for_sale(self):
        try:
            if not self.registered:
                print("You must register first!")
                return

            item_name = input("Enter item name: ").strip()
            price = float(input("Enter item price: ").strip())

            with self.items_lock:
                if item_name in self.items_for_sale:
                    print("Item already exists in your inventory.")
                    return
                self.items_for_sale[item_name] = ItemForSale(name=item_name, price=price)
                self.save_items()
                print(f"Item '{item_name}' added successfully")
                logging.info(f"Added item for sale: {item_name} at price {price}")

        except Exception as e:
            logging.error(f"Error adding item for sale: {e}")
            print(f"Error: {e}")

    def list_items_for_sale(self):
        try:
            with self.items_lock:
                if not self.items_for_sale:
                    print("You have no items for sale.")
                    return
                print("\nYour items for sale:")
                print("-" * 20)
                for item in self.items_for_sale.values():
                    print(f"Item: {item.name}")
                    print(f"Price: ${item.price:.2f}")
                    status = "Reserved" if item.reserved else "Available"
                    print(f"Status: {status}")
                    print("-" * 20)
        except Exception as e:
            logging.error(f"Error listing items: {e}")
            print(f"Error: {e}")

    def search_for_item(self):
        try:
            if not self.registered:
                print("You must register first!")
                return

            item_name = input("Enter item name to search for: ").strip()
            item_description = ""  # Adjust if needed
            max_price = float(input("Enter maximum price: ").strip())

            rq = str(random.randint(1000, 9999))
            message = self.message_handler.create_message(
                MessageType.LOOKING_FOR,
                rq,
                name=self.name,
                item_name=item_name,
                item_description=item_description,
                max_price=max_price
            )

            response = self.send_udp_message(message)
            if response:
                msg = self.message_handler.parse_message(response)
                if msg and msg.command == MessageType.SEARCH_ACK:
                    print(f"Search request for {item_name} acknowledged. Waiting for results...")
                    logging.info(f"Search request {rq} acknowledged by server")
                    # Add to active searches
                    with self.search_lock:
                        self.active_searches[rq] = ActiveSearch(
                            item_name=item_name,
                            max_price=max_price,
                            rq_number=rq
                        )
                else:
                    print(f"Unexpected search response: {response}")

        except Exception as e:
            logging.error(f"Error searching for item: {e}")
            print(f"Error: {e}")

    def send_udp_message(self, message: str) -> Optional[str]:
        try:
            for attempt in range(3):
                logging.info(f"Sending message to server (attempt {attempt + 1}): {message}")
                self.client_udp_socket_send.sendto(message.encode(), (self.server_ip, self.server_udp_port))
                logging.info(f"Sending UDP message (attempt {attempt + 1}): {message}")
                try:
                    self.client_udp_socket_send.settimeout(5)
                    response, _ = self.client_udp_socket_send.recvfrom(1024)
                    response = response.decode()
                    logging.info(f"Server response: {response}")
                    return response
                except socket.timeout:
                    logging.warning(f"No response from server on attempt {attempt + 1}")
                    continue
            print("Failed to receive response from server.")
            return None
        except Exception as e:
            logging.error(f"Error sending UDP message: {e}")
            return None

    def send_udp_message_no_response(self, message: str):
        try:
            self.client_udp_socket_send.sendto(message.encode(), (self.server_ip, self.server_udp_port))
            logging.info(f"Sending UDP message: {message}")
        except Exception as e:
            logging.error(f"Error sending UDP message: {e}")

    def listen_for_messages(self):
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
                    logging.error(f"Error receiving message: {e}")

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
            elif msg.command == MessageType.BUY_ACK:
                self.handle_buy_ack(msg)
            elif msg.command == MessageType.CANCEL:
                self.handle_transaction_cancel(msg)
            elif msg.command == MessageType.ERROR:
                self.handle_error_message(msg)
            else:
                logging.info(f"Unhandled message type: {msg.command}")
        except Exception as e:
            logging.error(f"Error handling incoming message: {e}")


    def handle_error_message(self, msg: Message):
        """Handle error messages from server"""
        try:
            error_message = msg.params.get("message", "Unknown error")
            print(f"\nError from server: {error_message}")
            logging.error(f"Received error from server: {error_message}")

            # If this was during a purchase, update item status
            with self.search_lock:
                for search in self.active_searches.values():
                    if search.status == "found":
                        search.status = "error"
                        logging.info(f"Updated search status to error for {search.item_name}")

        except Exception as e:
            logging.error(f"Error handling error message: {e}")

    def handle_search_request(self, msg: Message):
        """Handle incoming SEARCH messages as a seller"""
        try:
            item_name = msg.params["item_name"]
            rq_number = msg.rq_number  # Use this RQ# in OFFER

            with self.items_lock:
                matching_items = [
                    item for item in self.items_for_sale.values()
                    if (item_name.lower() in item.name.lower() or
                        item.name.lower() in item_name.lower()) and not item.reserved
                ]

            if matching_items:
                for item in matching_items:
                    offer_message = self.message_handler.create_message(
                        MessageType.OFFER,
                        rq_number,  # Use RQ# from SEARCH message
                        name=self.name,
                        item_name=item.name,
                        price=item.price
                    )
                    self.send_udp_message_no_response(offer_message)
                    logging.info(f"Sent offer for {item.name} at price {item.price}")
            else:
                # Do not respond if no matching items
                pass

        except Exception as e:
            logging.error(f"Error handling search request: {e}")

    def handle_found_notification(self, msg: Message):
        """Handle notifications about found items"""
        try:
            item_name = msg.params["item_name"]
            price = msg.params["price"]
            rq_number = msg.rq_number

            with self.search_lock:
                # Update active search status
                search_entry = self.active_searches.get(rq_number)
                if search_entry:
                    search_entry.status = "found"
                    search_entry.found_price = price
                else:
                    # Create a new search entry if not present
                    search_entry = ActiveSearch(
                        item_name=item_name,
                        max_price=price,
                        status="found",
                        rq_number=rq_number
                    )
                    self.active_searches[rq_number] = search_entry

            print(f"\nItem found: {item_name} at price ${price:.2f}")
            logging.info(f"Found notification received for {item_name} at {price}")

            # Prompt the buyer to decide
            self.prompt_purchase_decision(rq_number, item_name, price)

        except Exception as e:
            logging.error(f"Error handling found notification: {e}")

    def prompt_purchase_decision(self, rq_number: str, item_name: str, price: float):
        """Prompt the buyer to decide whether to buy the item or cancel"""
        try:
            # Clear any pending input
            import sys, termios, tty
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                sys.stdin.read(1)  # Clear one character
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

            decision = input(f"\nDo you want to buy '{item_name}' at ${price:.2f}? (yes/no): ").strip().lower()

            if decision == 'yes':
                # Send BUY message to server
                buy_message = self.message_handler.create_message(
                    MessageType.BUY,
                    rq_number,
                    item_name=item_name,
                    price=price
                )
                response = self.send_udp_message(buy_message)
                logging.info(f"Sent BUY message for {item_name} at {price}")

                # Wait for BUY_ACK from server
                if response:
                    msg = self.message_handler.parse_message(response)
                    if msg and msg.command == MessageType.BUY_ACK:
                        seller_ip = msg.params.get("seller_ip")
                        seller_tcp_port = msg.params.get("seller_tcp_port")
                        if seller_ip and seller_tcp_port:
                            print("Connecting to server for purchase...")
                            self.initiate_tcp_purchase(seller_ip, seller_tcp_port, rq_number, item_name, price)
                        elif msg and msg.command == MessageType.ERROR:
                            print(f"Error from server: {msg.params.get('message', 'Unknown error')}")
                        else:
                            print("Unexpected response from server")
            else:
                print("Purchase cancelled")
                # Send CANCEL message to server
                cancel_message = self.message_handler.create_message(
                    MessageType.CANCEL,
                    rq_number,
                    item_name=item_name,
                    price=price
                )
                self.send_udp_message_no_response(cancel_message)

        except Exception as e:
            logging.error(f"Error prompting purchase decision: {e}")
            print(f"Error during purchase: {e}")

    def handle_reserve_request(self, msg: Message):
        """Handle RESERVE message as a seller"""
        try:
            item_name = msg.params["item_name"]
            price = msg.params["price"]
            rq_number = msg.rq_number

            with self.items_lock:
                if item_name not in self.items_for_sale:
                    logging.warning(f"Reserve request for non-existent item: {item_name}")
                    return

                item = self.items_for_sale[item_name]
                if item.reserved:
                    logging.warning(f"Item {item_name} is already reserved")
                    return

                item.reserved = True
                self.save_items()
                print(f"\nItem '{item_name}' has been reserved at price ${price:.2f}")
                logging.info(f"Item {item_name} reserved at price {price}")

            # Initiate TCP connection
            self.initiate_tcp_transaction(rq_number, item_name, price)

        except Exception as e:
            logging.error(f"Error handling reserve request: {e}")

    def initiate_tcp_transaction(self, rq_number: str, item_name: str, price: float):
        """Handle TCP transaction as seller"""
        try:
            # Create TCP connection to server
            transaction_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            transaction_socket.settimeout(30)

            try:
                # Connect to server
                transaction_socket.connect((self.server_ip, self.server_tcp_port))
                print("Connected to server for transaction...")
                logging.info(f"TCP connection established for transaction {rq_number}")

                # Wait for INFORM_REQ
                data = transaction_socket.recv(1024).decode()
                msg = self.message_handler.parse_message(data)

                if not msg or msg.command != MessageType.INFORM_REQ:
                    raise Exception("Invalid server response")

                # Send INFORM_RES with seller's details (if any)
                inform_res = self.message_handler.create_message(

                        MessageType.INFORM_RES,
                        rq_number,
                        name=self.name,
                        cc_number='',  # Sellers might not need to send cc info
                        cc_exp_date='',
                        address=''  # Seller's address if needed
                        )
                transaction_socket.sendall(inform_res.encode())
                logging.info("Sent INFORM_RES to server from seller")

                # Wait for transaction result
                result = transaction_socket.recv(1024).decode()
                result_msg = self.message_handler.parse_message(result)

                if result_msg:
                    if result_msg.command == MessageType.SHIPPING_INFO:
                        print("\nTransaction completed. Please ship the item to:")
                        print(f"Name: {result_msg.params['name']}")
                        print(f"Address: {result_msg.params['address']}")
                    elif result_msg.command == MessageType.TRANSACTION_SUCCESS:
                        print("\nTransaction completed successfully!")
                        # Update local item status if seller
                        with self.items_lock:
                            if item_name in self.items_for_sale:
                                del self.items_for_sale[item_name]
                                self.save_items()
                    elif result_msg.command == MessageType.TRANSACTION_FAILED:
                        print(f"\nTransaction failed: {result_msg.params.get('reason', 'Unknown error')}")
                        # Release item if seller
                        with self.items_lock:
                            if item_name in self.items_for_sale:
                                self.items_for_sale[item_name].reserved = False
                                self.save_items()
                else:
                    print("Invalid response from server")

            except socket.timeout:
                print("Transaction timed out. Please try again.")
            except ConnectionRefusedError:
                print("Could not connect to server. Please try again.")
            finally:
                transaction_socket.close()

        except Exception as e:
            logging.error(f"Error during TCP transaction: {e}")
            print(f"Error during transaction: {e}")

    def handle_not_found_notification(self, msg: Message):
        """Handle NOT_FOUND message as a buyer"""
        try:
            item_name = msg.params["item_name"]
            max_price = msg.params["max_price"]
            rq_number = msg.rq_number

            with self.search_lock:
                search_entry = self.active_searches.get(rq_number)
                if search_entry:
                    search_entry.status = "not_found"

            print(f"\nItem '{item_name}' not found at or below ${max_price:.2f}")
            logging.info(f"Not found notification received for {item_name}")

        except Exception as e:
            logging.error(f"Error handling not found notification: {e}")

    def handle_not_available_notification(self, msg: Message):
        """Handle NOT_AVAILABLE message as a buyer"""
        try:
            item_name = msg.params["item_name"]
            rq_number = msg.rq_number

            with self.search_lock:
                search_entry = self.active_searches.get(rq_number)
                if search_entry:
                    search_entry.status = "not_available"

            print(f"\nItem '{item_name}' is not available from any seller")
            logging.info(f"Not available notification received for {item_name}")

        except Exception as e:
            logging.error(f"Error handling not available notification: {e}")

    def handle_negotiate_request(self, msg: Message):
        """Handle NEGOTIATE message as a seller"""
        try:
            item_name = msg.params["item_name"]
            max_price = msg.params["max_price"]
            rq_number = msg.rq_number

            with self.items_lock:
                if item_name not in self.items_for_sale:
                    logging.warning(f"Negotiate request for non-existent item: {item_name}")
                    return

                item = self.items_for_sale[item_name]

            # Decide whether to accept the negotiation
            decision = input(f"Server requests to sell '{item_name}' at ${max_price:.2f}. Accept? (yes/no): ").strip().lower()
            if decision == 'yes':
                # Send ACCEPT message to server
                accept_message = self.message_handler.create_message(
                    MessageType.ACCEPT,
                    rq_number,
                    name=self.name,
                    item_name=item_name,
                    max_price=max_price
                )
                self.send_udp_message_no_response(accept_message)
                logging.info(f"Sent ACCEPT message for {item_name} at {max_price}")
            else:
                # Send REFUSE message to server
                refuse_message = self.message_handler.create_message(
                    MessageType.REFUSE,
                    rq_number,
                    name=self.name,
                    item_name=item_name,
                    max_price=max_price
                )
                self.send_udp_message_no_response(refuse_message)
                logging.info(f"Sent REFUSE message for {item_name} at {max_price}")

        except Exception as e:
            logging.error(f"Error handling negotiate request: {e}")

    def handle_buy_ack(self, msg: Message):
        """Handle BUY_ACK message as a buyer to proceed with TCP connection"""
        try:
            seller_ip = msg.params["seller_ip"]
            seller_tcp_port = msg.params["seller_tcp_port"]
            rq_number = msg.rq_number

            # Get item details from active searches
            item_name = None
            price = None
            with self.search_lock:
                search_entry = self.active_searches.get(rq_number)
                if search_entry:
                    item_name = search_entry.item_name
                    price = search_entry.found_price
                else:
                    logging.error(f"No active search found for RQ# {rq_number}")
                    return

            if item_name and price is not None:
                self.initiate_tcp_purchase(seller_ip, seller_tcp_port, rq_number, item_name, price)
            else:
                logging.error("Missing item details for purchase")

        except Exception as e:
            logging.error(f"Error handling BUY_ACK: {e}")

    def connect_to_server_for_purchase(self, server_ip: str, server_tcp_port: int, rq_number: str, item_name: str, price: float):
        try:
            # Establish TCP connection to server
            with socket.create_connection((self.server_ip, self.server_tcp_port), timeout=5) as sock:
                # Send INFORM_REQ
                inform_req = self.message_handler.create_message(
                    MessageType.INFORM_REQ,
                    rq_number,
                    item_name=item_name,
                    price=price
                )
                sock.sendall(inform_req.encode())
                logging.info("Sent INFORM_REQ to server")

                # Receive INFORM_RES from server
                data = sock.recv(1024).decode()
                msg = self.message_handler.parse_message(data)
                if msg and msg.command == MessageType.INFORM_RES:
                    # Send INFORM_RES with required information
                    name = self.name
                    cc_number = input("Enter your credit card number: ").strip()
                    cc_exp_date = input("Enter your credit card expiration date (MM/YY): ").strip()
                    address = input("Enter your address: ").strip()
                    inform_res = self.message_handler.create_message(
                        MessageType.INFORM_RES,
                        rq_number,
                        name=name,
                        cc_number=cc_number,
                        cc_exp_date=cc_exp_date,
                        address=address
                    )
                    sock.sendall(inform_res.encode())
                    logging.info("Sent INFORM_RES to server")
                    # Wait for transaction result
                    response = sock.recv(1024).decode()
                    msg = self.message_handler.parse_message(response)
                    if msg and msg.command == MessageType.TRANSACTION_SUCCESS:
                        print("Transaction successful!")
                    elif msg and msg.command == MessageType.TRANSACTION_FAILED:
                        print(f"Transaction failed: {msg.params['reason']}")
                else:
                    logging.error(f"Unexpected TCP message: {data}")

        except Exception as e:
            logging.error(f"Error connecting to server for purchase: {e}")
            print(f"Failed to finalize purchase: {e}")

    def initiate_tcp_purchase(self, server_ip: str, server_tcp_port: int, rq_number: str, item_name: str, price: float):
        """Handle TCP purchase process"""
        try:
            # Create TCP connection to server
            purchase_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            purchase_socket.settimeout(30)

            try:
                # Connect to server
                purchase_socket.connect((server_ip, server_tcp_port))
                print("Connected to server. Processing transaction...")
                logging.info(f"TCP connection established for purchase {rq_number}")

                # wait for INFORM_REQ
                data = purchase_socket.recv(1024).decode()
                msg = self.message_handler.parse_message(data)

                if not msg or msg.command != MessageType.INFORM_REQ:
                    raise Exception("Invalid server response")

                # Get user info
                print("\nPlease provide transaction details:")
                cc_number = input("Enter credit card number: ").strip()
                cc_exp_date = input("Enter credit card expiration date (MM/YY): ").strip()
                address = input("Enter shipping address: ").strip()

                # Send INFORM_REQ
                inform_res = self.message_handler.create_message(
                        MessageType.INFORM_RES,
                        rq_number,
                        name=self.name,
                        cc_number=cc_number,
                        cc_exp_date=cc_exp_date,
                        address=address
                        )
                purchase_socket.sendall(inform_res.encode())
                print("Waiting for transaction processing...")

                # Wait for transaction result
                result = purchase_socket.recv(1024).decode()
                result_msg = self.message_handler.parse_message(result)

                if result_msg:
                    if result_msg.command == MessageType.TRANSACTION_SUCCESS:
                        print("\nTransaction completed successfully!")
                        # Update local item status if seller
                        with self.items_lock:
                            if item_name in self.items_for_sale:
                                del self.items_for_sale[item_name]
                                self.save_items()
                    elif result_msg.command == MessageType.SHIPPING_INFO:
                        print("\nTransaction completed. Please ship the item to:")
                        print(f"Name: {result_msg.params['name']}")
                        print(f"Address: {result_msg.params['address']}")
                    elif result_msg.command == MessageType.TRANSACTION_FAILED:
                        print(f"\nTransaction failed: {result_msg.params.get('reason', 'Unknown error')}")
                        # Release item if seller
                        with self.items_lock:
                            if item_name in self.items_for_sale:
                                self.items_for_sale[item_name].reserved = False
                                self.save_items()
                else:
                    print("Invalid response from server")

            except socket.timeout:
                print("Transaction timed out. Please try again.")
            except ConnectionRefusedError:
                print("Could not connect to server. Please try again.")
            finally:
                purchase_socket.close()

        except Exception as e:
            logging.error(f"Error during TCP purchase: {e}")
            print(f"Error during purchase: {e}")

    def handle_transaction_cancel(self, msg: Message):
        """Handle transaction cancellation"""
        try:
            reason = msg.params.get("reason", "Unknown reason")
            print(f"\nTransaction cancelled: {reason}")

            # Update item status if seller
            item_name = msg.params.get("item_name")
            if item_name:
                with self.items_lock:
                    if item_name in self.items_for_sale:
                        self.items_for_sale[item_name].reserved = False
                        self.save_items()
                        logging.info(f"Item {item_name} reservation cancelled")

        except Exception as e:
            logging.error(f"Error handling transaction cancel: {e}")

    def save_items(self):
        try:
            items_file = os.path.join(os.path.dirname(__file__), f'{self.name}_items.json')
            items_data = {}
            for item in self.items_for_sale.values():
                item_data = item.__dict__.copy()
                item_data['timestamp'] = item_data['timestamp'].isoformat()
                items_data[item.name] = item_data
            with open(items_file, 'w') as file:
                json.dump(items_data, file, indent=4)
            logging.info("Items saved successfully")
        except Exception as e:
            logging.error(f"Error saving items: {e}")

    def load_items(self):
        try:
            items_file = os.path.join(os.path.dirname(__file__), f'{self.name}_items.json')
            if os.path.exists(items_file):
                with open(items_file, 'r') as file:
                    items_data = json.load(file)
                    self.items_for_sale = {}
                    for name, data in items_data.items():
                        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                        self.items_for_sale[name] = ItemForSale(**data)
                logging.info("Items loaded successfully")
        except Exception as e:
            logging.error(f"Error loading items: {e}")

    def cleanup(self):
        try:
            self.running = False
            if hasattr(self, 'listener_thread') and self.listener_thread.is_alive():
                self.listener_thread.join(timeout=1)
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
            if hasattr(self, 'tcp_server_socket'):
                try:
                    self.tcp_server_socket.close()
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

