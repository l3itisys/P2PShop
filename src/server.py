import socket
import threading
import json
import os
import logging
import time
import signal
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from threading import Lock
from datetime import datetime, timedelta
from message_handler import MessageHandler, MessageType, Message

@dataclass
class SearchData:
    """Data class to hold search information"""
    buyer: str
    item_name: str
    max_price: float
    offers: List[Dict] = field(default_factory=list)
    status: str = "active"
    client_address: Optional[tuple] = None
    timer: Optional[threading.Timer] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class ItemReservation:
    """Data class to track item reservations"""
    seller: str
    buyer: str
    item_name: str
    price: float
    timestamp: datetime = field(default_factory=datetime.now)

class ServerUDP_TCP:
    def __init__(self, udp_port=3000, tcp_port=3001):
        # Initialize server configuration
        self._setup_logging()
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = True

        # Data structures with locks for thread safety
        self.registration_lock = Lock()
        self.search_lock = Lock()
        self.reservation_lock = Lock()

        self.active_searches: Dict[str, SearchData] = {}
        self.reservations: Dict[str, ItemReservation] = {}
        self.registration_data = {}

        # Configuration
        self.search_timeout = 300  # 5 minutes in seconds

        self.message_handler = MessageHandler()
        self.setup_sockets()

    def _setup_logging(self):
        """Initialize logging configuration"""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'server.log')

        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    def setup_sockets(self):
        """Initialize server sockets"""
        try:
            # Setup UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass
            self.udp_socket.bind(('0.0.0.0', self.udp_port))
            print(f"Server UDP listening on port {self.udp_port}")

            # Setup TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except AttributeError:
                pass
            self.tcp_socket.bind(('0.0.0.0', self.tcp_port))
            self.tcp_socket.listen(5)
            print(f"Server TCP listening on port {self.tcp_port}")

            # Load existing registrations
            self.registration_data = self.load_registrations()
            logging.info(f"Server started - UDP port: {self.udp_port}, TCP port: {self.tcp_port}")

            # Start listening threads
            self.start_listening_threads()

            print("Server running... (Press Ctrl+C to stop)")
            logging.info("Server running...")

        except Exception as e:
            logging.error(f"Failed to initialize server: {e}")
            self.cleanup()
            raise

    def start_listening_threads(self):
        """Start UDP and TCP listening threads"""
        self.udp_thread = threading.Thread(target=self.listen_udp)
        self.tcp_thread = threading.Thread(target=self.listen_tcp)

        self.udp_thread.daemon = True
        self.tcp_thread.daemon = True

        self.udp_thread.start()
        self.tcp_thread.start()

    def load_registrations(self):
        """Load registered users from persistent storage"""
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
        """Save registered users to persistent storage"""
        try:
            with self.registration_lock:
                registration_file = os.path.join(os.path.dirname(__file__), 'registrations.json')
                with open(registration_file, 'w') as file:
                    json.dump(self.registration_data, file, indent=4)
            logging.info("Registrations saved successfully")
        except Exception as e:
            logging.error(f"Error saving registrations: {e}")

    def handle_registration(self, msg: Message, client_address: tuple):
        """Handle client registration requests"""
        try:
            name = msg.params["name"]
            response = None
            
            with self.registration_lock:
                if name in self.registration_data:
                    response = self.message_handler.create_message(
                        MessageType.REGISTER_DENIED,
                        msg.rq_number,
                        reason=f"User {name} is already registered"
                    )
                    logging.warning(f"Registration denied for {name}: already registered")
                else:
                    self.registration_data[name] = {
                        'ip': msg.params["ip"],
                        'udp_port': msg.params["udp_port"],
                        'tcp_port': msg.params["tcp_port"]
                    }
                    self.save_registrations()
                    response = self.message_handler.create_message(
                        MessageType.REGISTERED,
                        msg.rq_number
                    )
                    logging.info(f"User {name} registered successfully")

            if response:
                # Send response with explicit address tuple
                addr = (client_address[0], client_address[1])
                encoded_response = response.encode()
                self.udp_socket.sendto(encoded_response, addr)
                logging.info(f"Sent registration response to {name} at {addr}: {response}")

        except Exception as e:
            logging.error(f"Registration error: {e}")
            try:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message=f"Registration failed: {str(e)}"
                )
                addr = (client_address[0], client_address[1])
                self.udp_socket.sendto(error_response.encode(), addr)
            except Exception as send_error:
                logging.error(f"Error sending registration error response: {send_error}")

    def handle_deregistration(self, msg: Message, client_address: tuple):
        """Handle client deregistration requests"""
        try:
            name = msg.params["name"]
            with self.registration_lock:
                if name in self.registration_data:
                    del self.registration_data[name]
                    self.save_registrations()
                    response = self.message_handler.create_message(
                        MessageType.DE_REGISTERED,
                        msg.rq_number,
                        name=name
                    )
                    logging.info(f"User {name} de-registered successfully")
                else:
                    response = self.message_handler.create_message(
                        MessageType.ERROR,
                        msg.rq_number,
                        message=f"User {name} not found"
                    )
                    logging.warning(f"De-registration failed: user {name} not found")

            self.udp_socket.sendto(response.encode(), client_address)

        except Exception as e:
            logging.error(f"De-registration error: {e}")
            try:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message=f"De-registration failed: {str(e)}"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)
            except Exception as send_error:
                logging.error(f"Error sending de-registration error response: {send_error}")

    def listen_udp(self):
        """Listen for UDP messages"""
        while self.running:
            try:
                data, client_address = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_client,
                               args=(data, client_address)).start()
            except socket.error:
                if self.running:
                    logging.error("UDP socket error, restarting UDP listener")
                    time.sleep(1)
            except Exception as e:
                if self.running:
                    logging.error(f"UDP listening error: {e}")

    def listen_tcp(self):
        """Listen for TCP connections"""
        self.tcp_socket.settimeout(1)  # Add timeout to allow checking self.running
        while self.running:
            try:
                client_socket, client_address = self.tcp_socket.accept()
                threading.Thread(target=self.handle_tcp_client,
                               args=(client_socket,)).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"TCP listening error: {e}")

    def handle_looking_for(self, msg: Message, client_address: tuple):
        """Handle search requests from buyers"""
        try:
            buyer_name = msg.params["name"]
            if buyer_name not in self.registration_data:
                response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message="User not registered"
                )
                self.udp_socket.sendto(response.encode(), client_address)
                return

            search_data = SearchData(
                buyer=buyer_name,
                item_name=msg.params["item_name"],
                max_price=msg.params["max_price"],
                client_address=client_address
            )

            with self.search_lock:
                self.active_searches[msg.rq_number] = search_data

            self._broadcast_search(msg.rq_number, search_data)

            timer = threading.Timer(
                self.search_timeout,
                self._handle_search_timeout,
                args=[msg.rq_number]
            )
            timer.start()
            search_data.timer = timer

            logging.info(f"Search initiated by {buyer_name} for {msg.params['item_name']}")

        except Exception as e:
            logging.error(f"Error handling search request: {e}")
            try:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message=f"Search request failed: {str(e)}"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)
            except Exception as send_error:
                logging.error(f"Error sending search error response: {send_error}")

    def _broadcast_search(self, search_id: str, search_data: SearchData):
        """Broadcast search request to all registered peers except buyer"""
        try:
            search_message = self.message_handler.create_message(
                MessageType.SEARCH,
                search_id,
                item_name=search_data.item_name
            )

            with self.registration_lock:
                for user, user_data in self.registration_data.items():
                    if user != search_data.buyer:
                        seller_address = (user_data["ip"], user_data["udp_port"])
                        try:
                            self.udp_socket.sendto(search_message.encode(), seller_address)
                            logging.info(f"Search broadcast sent to {user}")
                        except Exception as e:
                            logging.error(f"Failed to send search to {user}: {e}")

        except Exception as e:
            logging.error(f"Error broadcasting search: {e}")

    def handle_offer(self, msg: Message, client_address: tuple):
        """Handle offer responses from sellers"""
        try:
            seller_name = msg.params["name"]
            if seller_name not in self.registration_data:
                logging.warning(f"Offer received from unregistered seller: {seller_name}")
                return

            with self.search_lock:
                if msg.rq_number not in self.active_searches:
                    logging.warning(f"Offer received for inactive search: {msg.rq_number}")
                    return

                search_data = self.active_searches[msg.rq_number]
                offer = {
                    "seller": seller_name,
                    "price": msg.params["price"],
                    "timestamp": datetime.now()
                }
                search_data.offers.append(offer)

                # If price is within budget, process immediately
                if msg.params["price"] <= search_data.max_price:
                    self._process_acceptable_offer(msg.rq_number, search_data, offer)
                else:
                    # Try negotiation with the seller
                    self._initiate_negotiation(msg.rq_number, search_data, offer)

                logging.info(f"Offer received from {seller_name} for search {msg.rq_number}")

        except Exception as e:
            logging.error(f"Error handling offer: {e}")

    def _process_acceptable_offer(self, search_id: str, search_data: SearchData, offer: Dict):
        """Process an acceptable offer"""
        try:
            # Reserve the item
            with self.reservation_lock:
                reservation = ItemReservation(
                    seller=offer["seller"],
                    buyer=search_data.buyer,
                    item_name=search_data.item_name,
                    price=offer["price"]
                )
                self.reservations[search_id] = reservation

            # Send RESERVE to seller
            seller_data = self.registration_data[offer["seller"]]
            reserve_msg = self.message_handler.create_message(
                MessageType.RESERVE,
                search_id,
                item_name=search_data.item_name,
                price=offer["price"]
            )
            seller_address = (seller_data["ip"], seller_data["udp_port"])
            self.udp_socket.sendto(reserve_msg.encode(), seller_address)

            # Send FOUND to buyer
            found_msg = self.message_handler.create_message(
                MessageType.FOUND,
                search_id,
                item_name=search_data.item_name,
                price=offer["price"]
            )
            self.udp_socket.sendto(found_msg.encode(), search_data.client_address)

            # Cancel search timer and remove search
            if search_data.timer:
                search_data.timer.cancel()
            del self.active_searches[search_id]

        except Exception as e:
            logging.error(f"Error processing acceptable offer: {e}")

    def _initiate_negotiation(self, search_id: str, search_data: SearchData, offer: Dict):
        """Initiate negotiation with seller"""
        try:
            seller_data = self.registration_data[offer["seller"]]
            negotiate_msg = self.message_handler.create_message(
                MessageType.NEGOTIATE,
                search_id,
                item_name=search_data.item_name,
                max_price=search_data.max_price
            )
            seller_address = (seller_data["ip"], seller_data["udp_port"])
            self.udp_socket.sendto(negotiate_msg.encode(), seller_address)

        except Exception as e:
            logging.error(f"Error initiating negotiation: {e}")

    def _handle_search_timeout(self, search_id: str):
        """Handle timeout for search requests"""
        try:
            with self.search_lock:
                if search_id not in self.active_searches:
                    return

                search_data = self.active_searches[search_id]

                if not search_data.offers:
                    # No offers received
                    response = self.message_handler.create_message(
                        MessageType.NOT_AVAILABLE,
                        search_id,
                        item_name=search_data.item_name
                    )
                    self.udp_socket.sendto(response.encode(), search_data.client_address)
                    logging.info(f"Search {search_id} timed out with no offers")

                del self.active_searches[search_id]

        except Exception as e:
            logging.error(f"Error handling search timeout: {e}")
    def handle_tcp_client(self, client_socket):
        """Handle TCP client connections"""
        try:
            client_socket.settimeout(5)
            data = client_socket.recv(1024).decode()
            logging.info(f"Received TCP message: {data}")
            response = "TCP message received"
            client_socket.send(response.encode())
        except Exception as e:
            logging.error(f"TCP client handling error: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass

    def handle_udp_client(self, data, client_address):
        """Handle UDP client messages"""
        try:
            message = data.decode()
            logging.info(f"Received UDP message from {client_address}: {message}")

            if message == "test":
                self.udp_socket.sendto(b"ok", client_address)
                return

            msg = self.message_handler.parse_message(message)
            if not msg:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    "0000",
                    message="Invalid message format"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)
                return

            # Handle different message types
            if msg.command == MessageType.REGISTER:
                self.handle_registration(msg, client_address)
            elif msg.command == MessageType.DE_REGISTER:
                self.handle_deregistration(msg, client_address)
            elif msg.command == MessageType.LOOKING_FOR:
                self.handle_looking_for(msg, client_address)
            elif msg.command == MessageType.OFFER:
                self.handle_offer(msg, client_address)
            elif msg.command == MessageType.ACCEPT:
                self.handle_accept(msg, client_address)
            elif msg.command == MessageType.REFUSE:
                self.handle_refuse(msg, client_address)
            else:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message=f"Unknown command: {msg.command.value}"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)

        except Exception as e:
            logging.error(f"Error handling UDP client: {e}")
            try:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    "0000",
                    message="Internal server error"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)
            except Exception as send_error:
                logging.error(f"Error sending error response: {send_error}")

    def handle_accept(self, msg: Message, client_address: tuple):
        """Handle seller's acceptance of negotiated price"""
        try:
            with self.search_lock:
                for search_id, search_data in self.active_searches.items():
                    if search_data.item_name == msg.params["item_name"]:
                        # Create reservation
                        with self.reservation_lock:
                            reservation = ItemReservation(
                                seller=msg.params["name"],
                                buyer=search_data.buyer,
                                item_name=msg.params["item_name"],
                                price=msg.params["price"]
                            )
                            self.reservations[search_id] = reservation

                        # Notify buyer
                        found_msg = self.message_handler.create_message(
                            MessageType.FOUND,
                            search_id,
                            item_name=msg.params["item_name"],
                            price=msg.params["price"]
                        )
                        self.udp_socket.sendto(found_msg.encode(), search_data.client_address)

                        # Cancel search timer and cleanup
                        if search_data.timer:
                            search_data.timer.cancel()
                        del self.active_searches[search_id]
                        break

        except Exception as e:
            logging.error(f"Error handling accept: {e}")

    def handle_refuse(self, msg: Message, client_address: tuple):
        """Handle seller's refusal of negotiated price"""
        try:
            with self.search_lock:
                for search_id, search_data in self.active_searches.items():
                    if search_data.item_name == msg.params["item_name"]:
                        # Notify buyer
                        not_found_msg = self.message_handler.create_message(
                            MessageType.NOT_FOUND,
                            search_id,
                            item_name=msg.params["item_name"],
                            max_price=search_data.max_price
                        )
                        self.udp_socket.sendto(not_found_msg.encode(), search_data.client_address)

                        # Cleanup search
                        if search_data.timer:
                            search_data.timer.cancel()
                        del self.active_searches[search_id]
                        break

        except Exception as e:
            logging.error(f"Error handling refuse: {e}")

    def cleanup(self):
        """Clean up server resources"""
        try:
            self.running = False
            logging.info("Shutting down server...")

            # Save registration data
            self.save_registrations()

            # Cancel all search timers
            with self.search_lock:
                for search in self.active_searches.values():
                    if search.timer:
                        search.timer.cancel()

            # Close UDP socket
            if hasattr(self, 'udp_socket'):
                try:
                    self.udp_socket.shutdown(socket.SHUT_RDWR)
                    self.udp_socket.close()
                except:
                    pass

            # Close TCP socket
            if hasattr(self, 'tcp_socket'):
                try:
                    self.tcp_socket.shutdown(socket.SHUT_RDWR)
                    self.tcp_socket.close()
                except:
                    pass

            # Wait for threads to finish
            if hasattr(self, 'udp_thread'):
                self.udp_thread.join(timeout=1)
            if hasattr(self, 'tcp_thread'):
                self.tcp_thread.join(timeout=1)

            logging.info("Server cleaned up successfully")
            print("Server shutdown complete")

        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
            print(f"Error during shutdown: {e}")

    def signal_handler(self, signum, frame):
        """Handle termination signals"""
        print("\nSignal received. Shutting down server...")
        self.cleanup()
        # Force exit after cleanup
        os._exit(0)

    def run(self):
        """Main server loop"""
        try:
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)

            # Keep the main thread alive until shutdown
            while self.running:
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nShutdown requested...")
        except Exception as e:
            logging.error(f"Server error: {e}")
            print(f"Server error: {e}")
        finally:
            self.cleanup()

def main():
    """Main entry point for server"""
    try:
        server = ServerUDP_TCP()
        server.run()
    except Exception as e:
        print(f"Failed to start server: {e}")
        logging.error(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

