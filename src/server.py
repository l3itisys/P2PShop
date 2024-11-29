import socket
import threading
import json
import os
import logging
import time
import signal
import sys
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from threading import RLock
from datetime import datetime
from message_handler import MessageHandler, MessageType, Message

@dataclass
class SearchRequest:
    buyer_name: str
    item_name: str
    max_price: float
    offers: List[Dict] = field(default_factory=list)
    status: str = "active"
    client_address: Optional[tuple] = None
    timestamp: datetime = field(default_factory=datetime.now)
    buyer_rq_number: str = ""
    server_rq_number: str = ""

@dataclass
class ItemReservation:
    seller: str
    buyer: str
    item_name: str
    price: float
    timestamp: datetime = field(default_factory=datetime.now)

class MessageDelivery:
    def __init__(self, udp_socket: socket.socket):
        self.udp_socket = udp_socket
        self.max_retries = 3
        self.retry_delay = 1.0

    def send_with_retry(
        self,
        message: str,
        address: tuple,
        expect_response: bool = False
    ) -> Optional[Tuple[bool, str]]:
        for attempt in range(self.max_retries):
            try:
                self.udp_socket.sendto(message.encode(), address)
                logging.info(f"Sent message to {address} (attempt {attempt + 1})")

                if expect_response:
                    self.udp_socket.settimeout(self.retry_delay)
                    response, _ = self.udp_socket.recvfrom(1024)
                    return True, response.decode()
                return True, None

            except socket.timeout:
                logging.warning(f"Timeout on attempt {attempt + 1}")
                continue
            except Exception as e:
                logging.error(f"Error sending message: {e}")
                break

        return False, None

class SearchTimeoutManager:
    def __init__(self, timeout_duration: int = 300):
        self.timeout_duration = timeout_duration
        self.active_timers: Dict[str, threading.Timer] = {}

    def start_timer(self, search_id: str, callback: callable):
        if search_id in self.active_timers:
            self.cancel_timer(search_id)

        timer = threading.Timer(self.timeout_duration, callback, args=[search_id])
        timer.daemon = True
        timer.start()
        self.active_timers[search_id] = timer

    def cancel_timer(self, search_id: str):
        if search_id in self.active_timers:
            self.active_timers[search_id].cancel()
            del self.active_timers[search_id]

    def cleanup(self):
        for timer in self.active_timers.values():
            timer.cancel()
        self.active_timers.clear()

class ServerUDP_TCP:
    def __init__(self, udp_port=3000, tcp_port=3001):
        self._setup_logging()
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = True

        # Thread-safe locks
        self.registration_lock = RLock()
        self.search_lock = RLock()
        self.reservation_lock = RLock()

        # Data storage
        self.active_searches: Dict[str, SearchRequest] = {}
        self.reservations: Dict[str, ItemReservation] = {}
        self.registration_data = {}

        self.message_handler = MessageHandler()
        self.setup_sockets()
        self.message_delivery = MessageDelivery(self.udp_socket)
        self.timeout_manager = SearchTimeoutManager()
        self.search_cleanup_interval = 60
        self._start_cleanup_thread()

    def _setup_logging(self):
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'server.log')

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

    def setup_sockets(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(('', self.udp_port))

            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('', self.tcp_port))
            self.tcp_socket.listen(5)
            print(f"Server TCP listening on port {self.tcp_port}")

            self.registration_data = self.load_registrations()
            logging.info(f"Server started - UDP port: {self.udp_port}, TCP port: {self.tcp_port}")

            self.start_listening_threads()
            print("Server running... (Press Ctrl+C to stop)")
            logging.info("Server running...")

        except Exception as e:
            logging.error(f"Failed to initialize server: {e}")
            self.cleanup()
            raise

    def start_listening_threads(self):
        self.udp_thread = threading.Thread(target=self.listen_udp)
        self.tcp_thread = threading.Thread(target=self.listen_tcp)
        self.udp_thread.daemon = True
        self.tcp_thread.daemon = True
        self.udp_thread.start()
        self.tcp_thread.start()

    def _start_cleanup_thread(self):
        def cleanup_loop():
            while self.running:
                self._cleanup_expired_searches()
                time.sleep(self.search_cleanup_interval)

        self.cleanup_thread = threading.Thread(target=cleanup_loop)
        self.cleanup_thread.daemon = True
        self.cleanup_thread.start()

    def save_registrations(self):
        try:
            registration_file = os.path.join(os.path.dirname(__file__), 'registrations.json')
            cleaned_data = {
                name: data for name, data in self.registration_data.items()
                if all(k in data for k in ['ip', 'udp_port', 'tcp_port'])
            }
            with open(registration_file, 'w') as file:
                json.dump({"users": cleaned_data}, file, indent=4)
            logging.info("Registrations saved successfully")
        except Exception as e:
            logging.error(f"Error saving registrations: {e}")

    def load_registrations(self):
        try:
            registration_file = os.path.join(os.path.dirname(__file__), 'registrations.json')
            if os.path.exists(registration_file) and os.path.getsize(registration_file) > 0:
                with open(registration_file, 'r') as file:
                    data = json.load(file)
                    return data.get("users", {})
            return {}
        except Exception as e:
            logging.error(f"Error loading registrations: {e}")
            return {}

    def _cleanup_expired_searches(self):
        try:
            with self.search_lock:
                current_time = datetime.now()
                expired_searches = []

                for search_id, search in self.active_searches.items():
                    elapsed_time = (current_time - search.timestamp).total_seconds()
                    if elapsed_time >= self.timeout_manager.timeout_duration:
                        expired_searches.append(search_id)
                        logging.info(f"Search {search_id} expired after {elapsed_time} seconds")

                for search_id in expired_searches:
                    self._handle_search_timeout(search_id)

        except Exception as e:
            logging.error(f"Error in cleanup: {e}")

    def handle_registration(self, msg: Message, client_address: tuple):
        try:
            name = msg.params["name"]
            ip = msg.params["ip"]
            udp_port = msg.params["udp_port"]
            tcp_port = msg.params["tcp_port"]
            response = None

            with self.registration_lock:
                # Check if name is already registered
                if name in self.registration_data:
                    response = self.message_handler.create_message(
                        MessageType.REGISTER_DENIED,
                        msg.rq_number,
                        reason="Name already registered"
                    )
                    logging.warning(f"Registration denied for {name}: Name already registered")
                else:
                    # Register the user
                    self.registration_data[name] = {
                        'ip': ip,
                        'udp_port': udp_port,
                        'tcp_port': tcp_port,
                        'source_address': client_address
                    }
                    self.save_registrations()
                    response = self.message_handler.create_message(
                        MessageType.REGISTERED,
                        msg.rq_number
                    )
                    logging.info(f"User {name} registered successfully")

            if response:
                self.udp_socket.sendto(response.encode(), client_address)
                logging.info(f"Sent registration response to {name} at {client_address}")

        except Exception as e:
            logging.error(f"Registration error: {e}")
            try:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message=f"Registration failed: {str(e)}"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)
            except Exception as send_error:
                logging.error(f"Error sending registration error response: {send_error}")

    def handle_deregistration(self, msg: Message, client_address: tuple):
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

                    # Clean up searches and reservations
                    with self.search_lock:
                        searches_to_remove = [
                            search_id for search_id, search in self.active_searches.items()
                            if search.buyer_name == name
                        ]
                        for search_id in searches_to_remove:
                            self.timeout_manager.cancel_timer(search_id)
                            del self.active_searches[search_id]

                    with self.reservation_lock:
                        reservations_to_remove = [
                            res_id for res_id, reservation in self.reservations.items()
                            if reservation.buyer == name or reservation.seller == name
                        ]
                        for res_id in reservations_to_remove:
                            del self.reservations[res_id]
                else:
                    response = self.message_handler.create_message(
                        MessageType.DE_REGISTERED,
                        msg.rq_number,
                        name=name
                    )

                self.udp_socket.sendto(response.encode(), client_address)

        except Exception as e:
            logging.error(f"De-registration error: {e}")
            self._send_error_to_client(client_address, msg.rq_number, str(e))

    def _send_error_to_client(self, client_address: tuple, rq_number: str, error_msg: str):
        try:
            error_response = self.message_handler.create_message(
                MessageType.ERROR,
                rq_number,
                message=error_msg
            )
            self.udp_socket.sendto(error_response.encode(), client_address)
            logging.error(f"Sent error to {client_address}: {error_msg}")
        except Exception as e:
            logging.error(f"Failed to send error message: {e}")

    def handle_looking_for(self, msg: Message, client_address: tuple):
        try:
            buyer_name = msg.params["name"]
            item_name = msg.params["item_name"]
            item_description = msg.params.get("item_description", "")
            max_price = msg.params["max_price"]

            with self.search_lock:
                buyer_rq_number = msg.rq_number  # RQ# from LOOKING_FOR message
                server_rq_number = str(random.randint(1000, 9999))  # New RQ# for SEARCH message
                search_request = SearchRequest(
                    buyer_name=buyer_name,
                    item_name=item_name,
                    max_price=max_price,
                    client_address=client_address,
                    buyer_rq_number=buyer_rq_number,
                    server_rq_number=server_rq_number
                )
                self.active_searches[server_rq_number] = search_request
                self.timeout_manager.start_timer(server_rq_number, self._handle_search_timeout)

                # Send SEARCH_ACK to buyer using the buyer's RQ#
                search_ack = self.message_handler.create_message(
                    MessageType.SEARCH_ACK,
                    buyer_rq_number,
                    item_name=item_name
                )
                self.message_delivery.send_with_retry(search_ack, client_address)
                logging.info(f"Search {server_rq_number} started with {self.timeout_manager.timeout_duration}s timeout")

                # Send SEARCH message to all registered peers except the buyer
                search_message = self.message_handler.create_message(
                    MessageType.SEARCH,
                    server_rq_number,
                    item_name=item_name,
                    item_description=item_description
                )

                with self.registration_lock:
                    for peer_name, peer_info in self.registration_data.items():
                        if peer_name != buyer_name:
                            peer_address = (peer_info['ip'], peer_info['udp_port'])
                            self.message_delivery.send_with_retry(search_message, peer_address)
                            logging.info(f"Search broadcast sent to {peer_name}")

        except Exception as e:
            logging.error(f"Error handling LOOKING_FOR: {e}")
            self._send_error_to_client(client_address, msg.rq_number, str(e))

    def handle_offer(self, msg: Message, client_address: tuple):
        try:
            seller_name = msg.params["name"]
            if seller_name not in self.registration_data:
                logging.warning(f"Offer received from unregistered seller: {seller_name}")
                return

            with self.search_lock:
                if msg.rq_number not in self.active_searches:
                    logging.warning(f"Offer received for inactive search: {msg.rq_number}")
                    return

                search_request = self.active_searches[msg.rq_number]
                offer = {
                    "seller": seller_name,
                    "price": msg.params["price"],
                    "item_name": msg.params["item_name"],
                    "timestamp": datetime.now()
                }
                search_request.offers.append(offer)
                logging.info(f"Offer received from {seller_name} for search {msg.rq_number}")

                # Process offers immediately
                self._process_offers(msg.rq_number, search_request)

        except Exception as e:
            logging.error(f"Error handling offer: {e}")

    def _process_offers(self, search_id: str, search_request: SearchRequest):
        try:
            # Check if the search has already been processed
            if search_request.status != "active":
                return

            sorted_offers = sorted(search_request.offers, key=lambda x: x["price"])
            acceptable_offers = [
                offer for offer in sorted_offers
                if offer["price"] <= search_request.max_price
            ]

            if acceptable_offers:
                self._handle_accepted_offer(search_id, search_request, acceptable_offers[0])
                search_request.status = "completed"
                self.timeout_manager.cancel_timer(search_id)
                del self.active_searches[search_id]
            elif sorted_offers:
                # Start negotiation only if negotiation hasn't been started yet
                if not search_request.status == "negotiation_started":
                    self._start_negotiation(search_id, search_request, sorted_offers[0])
                    search_request.status = "negotiation_started"
            else:
                # Do nothing; wait for more offers
                pass

        except Exception as e:
            logging.error(f"Error processing offers: {e}")

    def _handle_accepted_offer(self, search_id: str, search_request: SearchRequest, offer: Dict):
        try:
            # Create reservation
            reservation = ItemReservation(
                seller=offer["seller"],
                buyer=search_request.buyer_name,
                item_name=offer["item_name"],
                price=offer["price"]
            )
            with self.reservation_lock:
                self.reservations[search_id] = reservation
            logging.info(f"Created reservation for search {search_id}")

            # Send FOUND message to buyer using buyer's RQ#
            buyer_info = self.registration_data.get(search_request.buyer_name)
            if buyer_info:
                buyer_address = (buyer_info['ip'], buyer_info['udp_port'])
                found_message = self.message_handler.create_message(
                    MessageType.FOUND,
                    search_request.buyer_rq_number,  # Use buyer's RQ#
                    item_name=offer["item_name"],
                    price=offer["price"]
                )
                self.message_delivery.send_with_retry(found_message, buyer_address)
                logging.info(f"Sent FOUND message to buyer {search_request.buyer_name}")
            else:
                logging.error(f"Buyer {search_request.buyer_name} not found in registration data")

            # Send RESERVE message to seller
            seller_info = self.registration_data.get(offer["seller"])
            if seller_info:
                seller_address = (seller_info['ip'], seller_info['udp_port'])
                reserve_message = self.message_handler.create_message(
                    MessageType.RESERVE,
                    search_id,  # Use server's RQ#
                    item_name=offer["item_name"],
                    price=offer["price"]
                )
                self.message_delivery.send_with_retry(reserve_message, seller_address)
                logging.info(f"Sent RESERVE message to seller {offer['seller']}")
            else:
                logging.error(f"Seller {offer['seller']} not found in registration data")

            logging.info(f"Successfully completed offer acceptance for search {search_id}")

        except Exception as e:
            logging.error(f"Error handling accepted offer: {e}")

    def _start_negotiation(self, search_id: str, search_request: SearchRequest, offer: Dict):
        try:
            # Send NEGOTIATE message to seller
            seller_info = self.registration_data.get(offer["seller"])
            if seller_info:
                seller_address = (seller_info['ip'], seller_info['udp_port'])
                negotiate_message = self.message_handler.create_message(
                    MessageType.NEGOTIATE,
                    search_id,  # Use server's RQ#
                    item_name=offer["item_name"],
                    max_price=search_request.max_price
                )
                self.message_delivery.send_with_retry(negotiate_message, seller_address)
                logging.info(f"Sent NEGOTIATE message to seller {offer['seller']}")
            else:
                logging.error(f"Seller {offer['seller']} not found in registration data")

        except Exception as e:
            logging.error(f"Error starting negotiation: {e}")

    def handle_accept(self, msg: Message, client_address: tuple):
        try:
            seller_name = msg.params["name"]
            with self.search_lock:
                if msg.rq_number not in self.active_searches:
                    logging.warning(f"Accept received for inactive search: {msg.rq_number}")
                    return

                search_request = self.active_searches[msg.rq_number]
                if search_request.status != "negotiation_started":
                    logging.warning(f"Accept received but negotiation not started for search {msg.rq_number}")
                    return

                # Update reservation
                reservation = ItemReservation(
                    seller=seller_name,
                    buyer=search_request.buyer_name,
                    item_name=msg.params["item_name"],
                    price=msg.params["max_price"]
                )
                with self.reservation_lock:
                    self.reservations[msg.rq_number] = reservation

                # Inform buyer with FOUND message using buyer's RQ#
                buyer_info = self.registration_data.get(search_request.buyer_name)
                if buyer_info:
                    buyer_address = (buyer_info['ip'], buyer_info['udp_port'])
                    found_message = self.message_handler.create_message(
                        MessageType.FOUND,
                        search_request.buyer_rq_number,  # Use buyer's RQ#
                        item_name=msg.params["item_name"],
                        price=msg.params["max_price"]
                    )
                    self.message_delivery.send_with_retry(found_message, buyer_address)
                    logging.info(f"Sent FOUND message to buyer {search_request.buyer_name}")
                else:
                    logging.error(f"Buyer {search_request.buyer_name} not found in registration data")

                search_request.status = "completed"
                self.timeout_manager.cancel_timer(msg.rq_number)
                del self.active_searches[msg.rq_number]

            logging.info(f"Accept handled successfully for search {msg.rq_number}")

        except Exception as e:
            logging.error(f"Error handling accept: {e}")

    def handle_refuse(self, msg: Message, client_address: tuple):
        try:
            seller_name = msg.params["name"]
            with self.search_lock:
                if msg.rq_number not in self.active_searches:
                    logging.warning(f"Refuse received for inactive search: {msg.rq_number}")
                    return

                search_request = self.active_searches[msg.rq_number]
                # Inform buyer with NOT_FOUND message using buyer's RQ#
                buyer_info = self.registration_data.get(search_request.buyer_name)
                if buyer_info:
                    buyer_address = (buyer_info['ip'], buyer_info['udp_port'])
                    not_found_message = self.message_handler.create_message(
                        MessageType.NOT_FOUND,
                        search_request.buyer_rq_number,  # Use buyer's RQ#
                        item_name=msg.params["item_name"],
                        max_price=msg.params["max_price"]
                    )
                    self.message_delivery.send_with_retry(not_found_message, buyer_address)
                    logging.info(f"Sent NOT_FOUND message to buyer {search_request.buyer_name}")
                else:
                    logging.error(f"Buyer {search_request.buyer_name} not found in registration data")

                search_request.status = "completed"
                self.timeout_manager.cancel_timer(msg.rq_number)
                del self.active_searches[msg.rq_number]

        except Exception as e:
            logging.error(f"Error handling refuse: {e}")

    def _handle_search_timeout(self, search_id: str):
        try:
            with self.search_lock:
                if search_id not in self.active_searches:
                    return

                search_request = self.active_searches[search_id]

                # Only process if search is still active
                if search_request.status == "active":
                    if not search_request.offers:
                        self._handle_no_offers(search_id, search_request)
                    else:
                        self._process_offers(search_id, search_request)

                self.timeout_manager.cancel_timer(search_id)
                del self.active_searches[search_id]

        except Exception as e:
            logging.error(f"Error handling search timeout: {e}")

    def _handle_no_offers(self, search_id: str, search_request: SearchRequest):
        try:
            buyer_info = self.registration_data.get(search_request.buyer_name)
            if buyer_info:
                buyer_address = (buyer_info['ip'], buyer_info['udp_port'])
                not_available_message = self.message_handler.create_message(
                    MessageType.NOT_AVAILABLE,
                    search_request.buyer_rq_number,  # Use buyer's RQ#
                    item_name=search_request.item_name
                )
                self.message_delivery.send_with_retry(not_available_message, buyer_address)
                logging.info(f"Sent NOT_AVAILABLE message to buyer {search_request.buyer_name}")
            else:
                logging.error(f"Buyer {search_request.buyer_name} not found in registration data")
        except Exception as e:
            logging.error(f"Error handling no offers: {e}")

    def get_name_by_address(self, client_address: tuple) -> Optional[str]:
        """Get client name by matching either IP/port or just IP"""
        try:
            with self.registration_lock:
                # first try exact match
                for name, info in self.registration_data.items():
                    if (info['ip'] == client_address[0] and
                        info['udp_port'] == client_address[1]):
                        return name

                # If no, try matching just IP
                for name, info in self.registration_data.items():
                    if info['ip'] == client_address[0]:
                        return name
            return None
        except Exception as e:
            logging.error(f"Error in get_name_by_address: {e}")
            return None

    def handle_cancel(self, msg: Message, client_address: tuple):
        try:
            buyer_name = self.get_name_by_address(client_address)
            if not buyer_name:
                logging.warning(f"CANCEL received from unregistered buyer at {client_address}")
                return

            with self.reservation_lock:
                # Find reservation matching the buyer and item
                reservation = None
                for res_id, res in self.reservations.items():
                    if res.buyer == buyer_name and res.item_name == msg.params["item_name"]:
                        reservation = res
                        break

                if not reservation:
                    logging.warning(f"No reservation found for buyer {buyer_name} and item {msg.params['item_name']}")
                    return

                # Remove reservation
                del self.reservations[res_id]
                logging.info(f"Reservation canceled for buyer {buyer_name} and item {msg.params['item_name']}")

                # Notify seller to release the item (Optional)
                seller_info = self.registration_data.get(reservation.seller)
                if seller_info:
                    seller_address = (seller_info['ip'], seller_info['udp_port'])
                    # Send CANCEL message to seller
                    cancel_message = self.message_handler.create_message(
                        MessageType.CANCEL,
                        res_id,
                        item_name=reservation.item_name,
                        price=reservation.price
                    )
                    self.message_delivery.send_with_retry(cancel_message, seller_address)
                    logging.info(f"Sent CANCEL message to seller {reservation.seller}")

        except Exception as e:
            logging.error(f"Error handling CANCEL: {e}")
            self._send_error_to_client(client_address, msg.rq_number, str(e))

    def handle_buy(self, msg: Message, client_address: tuple):
        try:
            # Find buyer by source address
            buyer_name = None
            with self.registration_lock:
                for name, info in self.registration_data.items():
                    if info.get('source_address') == client_address:
                        buyer_name = name
                        break

            if not buyer_name:
                logging.warning(f"BUY received from unregistered buyer at {client_address}")
                error_msg = self.message_handler.create_message(
                        MessageType.ERROR,
                        msg.rq_number,
                        message="Buyer not registered"
                        )
                self.udp_socket.sendto(error_msg.encode(), client_address)
                return

            # Find the reservation
            item_name = msg.params["item_name"]
            price = msg.params["price"]

            with self.reservation_lock:
                reservation = None
                reservation_id = None
                for res_id, res in self.reservations.items():
                    if (res.buyer == buyer_name and
                        res.item_name == item_name and
                        abs(res.price - price) < 0.01):
                        reservation = res
                        reservation_id = res_id
                        break

                if not reservation:
                    error_msg = self.message_handler.create_message(
                            MessageType.ERROR,
                            msg.rq_number,
                            message="No matching reservation found"
                            )
                    self.udp_socket.sendto(error_msg.encode(), client_address)
                    return

                # Send BUY_ACK to buyer with server's IP and TCP port
                buy_ack = self.message_handler.create_message(
                    MessageType.BUY_ACK,
                    msg.rq_number,
                    seller_ip=self.server_ip,
                    seller_tcp_port=self.tcp_port
                )
                self.udp_socket.sendto(buy_ack.encode(), client_address)
                logging.info(f"Sent BUY_ACK to buyer {buyer_name}")

                # Start purchase finalization
                threading.Thread(
                        target=self.finalize_purchase,
                        args=(reservation, reservation_id),
                        daemon=True
                        ).start()

        except Exception as e:
            logging.error(f"Error handling BUY: {e}")

    def finalize_purchase(self, reservation: ItemReservation, rq_number: str):
        """Handle the purchase finalization over TCP"""
        try:
            # Open TCP connections to buyer and seller
            buyer_info = self.registration_data.get(reservation.buyer)
            seller_info = self.registration_data.get(reservation.seller)

            if not buyer_info or not seller_info:
                logging.error("Buyer or seller information not found for finalizing purchase")
                return

            # Accept TCP connections with timeouts
            self.tcp_socket.settimeout(30)

            # Wait for buyer connection
            logging.info("Waiting for TCP connections...")

            # Accept fisrt connection
            conn1, addr1 = self.tcp_socket.accept()
            logging.info(f"First connection accepted from {addr1}")

            # Accept second connection
            conn2, addr2 = self.tcp_socket.accept()
            logging.info(f"Second connection accepted from {addr2}")

            # Determine which is buyer and seller
            if addr1[0] == buyer_info['ip']:
                buyer_socket = conn1
                seller_socket == conn2
            else:
                buyer_socket = conn2
                seller_socket = conn1

            # Set timeouts
            buyer_socket.settimeout(30)
            seller_socket.settimeout(30)

            # Send INFORM_REQ to both parties
            inform_req = self.message_handler.create_message(
                    MessageType.INFORM_REQ,
                    rq_number,
                    item_name=reservation.item_name,
                    price=reservation.price
                    )
            buyer_socket.sendall(inform_req.encode())
            seller_socket.sendall(inform_req.encode())

            # Get responses
            buyer_res = buyer_socket.recv(1024).decode()
            seller_res = seller_socket.recv(1024).decode()

            buyer_msg = self.message_handler.parse_message(buyer_res)
            seller_msg = self.message_handler.parse_message(seller_res)

            # Process payment
            if self.process_payment(buyer_msg, seller_msg, reservation.price):
                # Send sucess messages
                success_msg = self.message_handler.create_message(
                        MessageType.TRANSACTION_SECCESS,
                        rq_number
                        )
                buyer_socket.sendall(success_msg.encode())

                # Send SHIPPING_INFO to seller
                shipping_info = self.message_handler.create_message(
                        Messagetype.SHIPPING_INFO,
                        rq_number,
                        name=buyer_msg.params["name"],
                        address=buyer_msg.params["address"]
                        )
                seller_socket.sendall(shipping_info.encode())

                logging.info(f"Transaction {rq_number} completed successfully")
            else:
                # Send failure messages
                fail_msg = self.message_handler.create_message(
                        MessageType.TRANSACTION_FAILED,
                        rq_number,
                        reason="Payment processing failed"
                        )
                buyer_socket.sendall(fail_msg.encode())
                seller_socket.sendall(fail_msg.encode())
                logging.error(f"Transaction {rq_number} failed during payment")

        except socket.timeout:
            logging.error(f"TCP connection timeout for transaction {rq_number}")
            self._handle_transaction_timeout(rq_number, reservation)
        except Exception as e:
            logging.error(f"Error finalizing purchase: {e}")
            self._handle_transaction_error(rq_number, reservation)
        finally:
            # Cleanup connections
            if 'buyer_socket' in locals():
                buyer_socket.close()
            if 'seller_socket' in locals():
                seller_socket.close()

    def _handle_transaction_timeout(self, rq_number: str, reservation: ItemReservation):
        """Handle timeout during transaction"""
        try:
            # Remove reservation
            with self.reservation_lock:
                if rq_number in self.reservations:
                    del self.reservations[rq_number]

            # Notify both parties through UDP
            cancel_msg = self.message_handler.create_message(
                    MessageType.CANCEL,
                    rq_number,
                    reason="Transaction timeout"
                    )

            buyer_info = self.registration_data.get(reservation.buyer)
            seller_info = self.registration_data.get(reservation.seller)

            if buyer_info:
                self.message_delivery.send_with_retry(
                        cancel_msg,
                        (buyer_info['ip'], buyer_info['udp_port'])
                        )

            if seller_info:
                self.message_delivery.send_with_retry(
                        cancel_msg,
                        (seller_info['ip'], seller_info['udp_port'])
                        )

        except Exception as e:
            logging.error(f"Error handling transaction timeout: {e}")

    def _handle_transaction_error(self, rq_number: str, reservation: ItemReservation):
        """Handle general transaction errors"""
        try:
            # Remove Transaction
            with self.reservation_lock:
                if rq_number in self.reservations:
                    del self.reservations[rq_number]

            # Notify both parties
            error_msg = self.message_handler.create_message(
                    MessageType.CANCEL,
                    rq_number,
                    reason="Transaction failed"

                    )
            buyer_info = self.registration_data.get(reservation.buyer)
            seller_info = self.registration_data.get(reservation.seller)\

            if buyer_info:
                self.message_delivery.send_with_retry(
                        error_msg,
                        (buyer_info['ip'], buyer_info['udp_port'])
                        )
            if seller_info:
                self.message_delivery.send_with_retry(
                        error_msg,
                        (seller_info['ip'], seller_info['udp_port'])
                        )

        except Exception as e:
            logging.error(f"Error handling transaction error: {e}")

    def process_payment(self, buyer_msg: Message, seller_msg: Message, price: float) -> bool:
        # Simulate payment processing
        # Charge buyer's credit card and credit seller's credit card with 90% of the price
        # Return True if successful, False otherwise
        return True  # Assuming success for simulation

    def handle_udp_client(self, data: bytes, client_address: tuple):
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

            logging.info(f"Processing message type: {msg.command}")
            self.route_message(msg, client_address)

        except Exception as e:
            logging.error(f"Error handling UDP client: {e}")
            self._send_error_to_client(client_address, msg.rq_number if msg else "0000", "Internal server error")

    def route_message(self, msg: Message, client_address: tuple):
        try:
            handlers = {
                MessageType.REGISTER: self.handle_registration,
                MessageType.DE_REGISTER: self.handle_deregistration,
                MessageType.LOOKING_FOR: self.handle_looking_for,
                MessageType.OFFER: self.handle_offer,
                MessageType.ACCEPT: self.handle_accept,
                MessageType.REFUSE: self.handle_refuse,
                MessageType.CANCEL: self.handle_cancel,
                MessageType.BUY: self.handle_buy,
                # Add other handlers as needed
            }

            handler = handlers.get(msg.command)
            if handler:
                handler(msg, client_address)
            else:
                error_response = self.message_handler.create_message(
                    MessageType.ERROR,
                    msg.rq_number,
                    message=f"Unknown command: {msg.command.value}"
                )
                self.udp_socket.sendto(error_response.encode(), client_address)
                logging.warning(f"Unknown command received: {msg.command}")

        except Exception as e:
            logging.error(f"Error routing message: {e}")
            self._send_error_to_client(client_address, msg.rq_number, "Internal server error")

    def listen_udp(self):
        print("Starting UDP listener...")
        self.udp_socket.settimeout(1)
        while self.running:
            try:
                data, client_address = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_udp_client,
                                 args=(data, client_address)).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"UDP listening error: {e}")

    def listen_tcp(self):
        self.tcp_socket.settimeout(1)
        while self.running:
            try:
                client_socket, client_address = self.tcp_socket.accept()
                threading.Thread(target=self.handle_tcp_connection,
                                 args=(client_socket, client_address)).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logging.error(f"TCP listening error: {e}")

    def handle_tcp_connection(self, client_socket: socket.socket, client_address: tuple):
        # Handle incoming TCP connections if necessary
        # In this implementation, we handle TCP connections during purchase finalization
        client_socket.close()

    def cleanup(self):
        try:
            print("\nStarting server cleanup...")
            self.running = False
            logging.info("Starting server cleanup...")

            self.timeout_manager.cleanup()

            with self.registration_lock:
                self.save_registrations()

            for socket_attr in ['udp_socket', 'tcp_socket']:
                if hasattr(self, socket_attr):
                    try:
                        getattr(self, socket_attr).close()
                    except:
                        pass

            for thread_attr in ['udp_thread', 'tcp_thread', 'cleanup_thread']:
                if hasattr(self, thread_attr):
                    thread = getattr(self, thread_attr)
                    if thread.is_alive():
                        thread.join(timeout=1)

            logging.info("Server cleanup completed")
            print("Server shutdown complete")

        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
            print(f"Error during shutdown: {e}")

    def signal_handler(self, signum, frame):
        print("\nSignal received. Shutting down server...")
        self.cleanup()
        os._exit(0)

    def run(self):
        try:
            signal.signal(signal.SIGINT, self.signal_handler)
            signal.signal(signal.SIGTERM, self.signal_handler)

            while self.running:
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\nShutdown requested...")
        except Exception as e:
            logging.error(f"Server error: {e}")
            print(f"Server error: {e}")
        finally:
            self.cleanup()

    @property
    def server_ip(self):
        return socket.gethostbyname(socket.gethostname())

def main():
    try:
        server = ServerUDP_TCP()
        server.run()
    except Exception as e:
        print(f"Failed to start server: {e}")
        logging.error(f"Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

