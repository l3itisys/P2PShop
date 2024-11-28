import socket
import threading
import json
import os
import logging
import time
import signal
import sys
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
            if os.path.exists(registration_file):
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
                # Update registration if name already exists
                self.registration_data[name] = {
                    'ip': ip,
                    'udp_port': udp_port,
                    'tcp_port': tcp_port
                }
                self.save_registrations()
                response = self.message_handler.create_message(
                    MessageType.REGISTERED,
                    msg.rq_number
                )
                logging.info(f"User {name} registered/updated successfully")

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
                        MessageType.ERROR,
                        msg.rq_number,
                        message=f"User {name} not found"
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

    def handle_accept(self, msg: Message, client_address: tuple):
        try:
            seller_name = msg.params["name"]
            with self.search_lock:
                if msg.rq_number not in self.active_searches:
                    logging.warning(f"Accept received for inactive search: {msg.rq_number}")
                return

            search_request = self.active_searches[msg.rq_number]
            reservation = ItemReservation(
                    seller=seller_name,
                    buyer=search_request.buyer_name,
                    item_name=msg.params["item_name"],
                    price=msg.params["price"]
                    )
            with self.reservation_lock:
                self.reservations[msg.rq_number] = reservation

            self._notify_buyer_found(msg.rq_number, search_request, msg.params)
            search_request.status = "completed"
            self.timeout_manager.cancel_timer(msg.rq_number)
            del self.active_searches[msg.rq_number]

        except Exception as e:
            logging.error(f"Error handling accept: {e}")

    def _notify_buyer_found(self, search_id: str, search_request: SearchRequest, params: dict):
        try:
            found_msg = self.message_handler.create_message(
                    MessageType.FOUND,
                    search_id,
                    item_name=params["item_name"],
                    price=params["price"]
                    )
            buyer_data = self.registration_data[search_request.buyer_name]
            buyer_address = (buyer_data["ip"], buyer_data["udp_port"])
            self.message_delivery.send_with_retry(found_msg, buyer_address)
            logging.info(f"Notified buyer of found item: {params['item_name']}")
        except Exception as e:
            logging.error(f"Error notifying buyer: {e}")


    def _validate_registration(self, name: str, ip: str, udp_port: int, tcp_port: int) -> bool:
       try:
           if not name or len(name.strip()) == 0:
               return False

           try:
               socket.inet_aton(ip)
           except socket.error:
               return False

           if not (1024 <= udp_port <= 65535 and 1024 <= tcp_port <= 65535):
               return False

           return True
       except Exception as e:
           logging.error(f"Error validating registration parameters: {e}")
           return False

    def _send_error_response(self, rq_number: str, message: str, client_address: tuple):
       try:
           error_response = self.message_handler.create_message(
               MessageType.ERROR,
               rq_number,
               message=message
           )
           self.udp_socket.sendto(error_response.encode(), client_address)
           logging.info(f"Sent error response to {client_address}: {message}")
       except Exception as e:
           logging.error(f"Error sending error response: {e}")

    def _validate_search_request(self, msg: Message, client_address: tuple) -> bool:
        try:
            buyer_name = msg.params["name"]
            # Check if user is registered
            if buyer_name not in self.registration_data:
                self._send_error_to_client(
                        client_address,
                        msg.rq_number,
                        "User not registered"
                        )
                return False

            # Validate price
            if msg.params["max_price"] <= 0:
                self._send_error_to_client(
                        client_address,
                        msg.rq_number,
                        "Invalide price"
                        )
                return False
            return True

        except Exception as e:
            logging.error(f"Error validating search request: {e}")
            self._send_error_to_client(
                    client_address,
                    msg.rq_number,
                    str(e)
                    )
            return False

    def _handle_no_sellers(self, search_id: str, search_request: SearchRequest):
        """Handle case when no sellers are available"""
        try:
            not_available_msg = self.message_handler.create_message(
                    MessageType.NOT_AVAILABLE,
                    search_id,
                    item_name=search_request.item_name
                    )
            self.udp_socket.sendto(not_available_msg.encode(), search_request.client_address)

            self._cleanup_search(search_id)
            logging.info(f"No sellers available for item {search_request.item_name}")
        except Exception as e:
            logging.error(f"Error handling no sellers case: {e}")

    def _handle_no_offers(self, search_id: str, search_request: SearchRequest):
        """Handle case when no offers received"""
        try:
            not_available_msg = self.message_handler.create_message(
                    MessageType.NOT_AVAILABLE,
                    search_id,
                    item_name=search_request.item_name
                    )
            self.udp_socket.sendto(not_available_msg.encode(), search_request.client_address)
            logging.info(f"No offers received for search {search_id}")
        except Exception as e:
            logging.error(f"Error handling no offers case: {e}")

    def _start_negotiation(self, search_id: str, search_request: SearchRequest, offer: Dict):
        """Start price negotiation with seller"""
        try:
            # Send negotiate message to seller
            negotiate_msg = self.message_handler.create_message(
                    MessageType.NEGOCIATE,
                    search_id,
                    item_name=offer["item_name"],
                    max_price=search_request.max_price
                    )
            seller_data = self.registration_data[offer["seller"]]
            seller_address = (seller_data["ip"], seller_data["udp_port"])
            self.message_delivery.send_with_retry(negotiate_msg, seller_address)
            logging.info(f"Started negotiation for {offer['item_name']} with seller {offer['seller']}")
        except Exception as e:
            logging.error(f"Error starting negotiation: {e}")

    def _send_not_found(self, search_id: str, search_request: SearchRequest):
        """Send not found message to buyer"""
        try:
            not_found_msg = self.message_handler.create_message(
                    MessageType.NOT_FOUND,
                    search_id,
                    item_name=search_request.item_name,
                    max_price=search_request.max_price
                    )
            self.udp_socket.sendto(not_found_msg.encode(), search_request.client_address)
            logging.info(f"Sent NOT_FOUND to buyer for {search_request.item_name}")
        except Exception as e:
            logging.error(f"Error sending not found message: {e}")

    def handle_looking_for(self, msg: Message, client_address: tuple):
       try:
           buyer_name = msg.params["name"]
           if not self._validate_search_request(msg, client_address):
               return

           search_request = SearchRequest(
               buyer_name=buyer_name,
               item_name=msg.params["item_name"],
               max_price=msg.params["max_price"],
               client_address=client_address
           )

           with self.search_lock:
               self.active_searches[msg.rq_number] = search_request
               self.timeout_manager.start_timer(msg.rq_number, self._handle_search_timeout)

           ack_msg = self.message_handler.create_message(
               MessageType.SEARCH_ACK,
               msg.rq_number,
               item_name=msg.params["item_name"]
           )
           success, _ = self.message_delivery.send_with_retry(ack_msg, client_address)

           if success:
               self._broadcast_search(msg.rq_number, search_request)
               logging.info(f"Search {msg.rq_number} started with {self.timeout_manager.timeout_duration}s timeout")
           else:
               self._cleanup_search(msg.rq_number)

       except Exception as e:
           logging.error(f"Error handling search request: {e}")
           self._send_error_to_client(client_address, msg.rq_number, str(e))


    def _broadcast_search(self, search_id: str, search_request: SearchRequest):
       try:
           search_message = self.message_handler.create_message(
               MessageType.SEARCH,
               search_id,
               item_name=search_request.item_name
           )

           with self.registration_lock:
               found_sellers = False
               for user, user_data in self.registration_data.items():
                   if user != search_request.buyer_name:
                       seller_address = (user_data["ip"], user_data["udp_port"])
                       try:
                           self.udp_socket.sendto(search_message.encode(), seller_address)
                           found_sellers = True
                           logging.info(f"Search broadcast sent to {user}")
                       except Exception as e:
                           logging.error(f"Failed to send search to {user}: {e}")

               if not found_sellers:
                   self._handle_no_sellers(search_id, search_request)

       except Exception as e:
           logging.error(f"Error broadcasting search: {e}")

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

               # process offers immediatly
               self._process_offers(msg.rq_number, search_request)

       except Exception as e:
           logging.error(f"Error handling offer: {e}")

    def _handle_search_timeout(self, search_id: str):
       try:
           with self.search_lock:
               if search_id not in self.active_searches:
                   return

               search_request = self.active_searches[search_id]
               if not search_request.offers:
                   self._handle_no_offers(search_id, search_request)
               else:
                   self._process_offers(search_id, search_request)

               self.timeout_manager.cancel_timer(search_id)
               del self.active_searches[search_id]

       except Exception as e:
           logging.error(f"Error handling search timeout: {e}")
           self._cleanup_search(search_id)

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
               # Start negotiation only if negociation hasn't been started yet
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
           with self.reservation_lock:
               reservation = ItemReservation(
                   seller=offer["seller"],
                   buyer=search_request.buyer_name,
                   item_name=offer["item_name"],
                   price=offer["price"]
               )
               self.reservations[search_id] = reservation
               logging.info(f"Created reservation for search {search_id}")

           # Get addresses
           buyer_data = self.registration_data[search_request.buyer_name]
           seller_data = self.registration_data[offer["seller"]]
           buyer_address = (buyer_data["ip"], buyer_data["udp_port"])
           seller_address = (seller_data["ip"], seller_data["udp_port"])

           # Notify buyer
           found_msg = self.message_handler.create_message(
               MessageType.FOUND,
               search_id,
               item_name=offer["item_name"],
               price=offer["price"]
           )
           success_buyer = self.message_delivery.send_with_retry(found_msg, buyer_address)
           if success_buyer[0]:
               logging.info(f"Sent FOUND message to buyer {search_request.buyer_name}")

           # Notify seller
           reserve_msg = self.message_handler.create_message(
               MessageType.RESERVE,
               search_id,
               item_name=offer["item_name"],
               price=offer["price"]
           )
           success_seller = self.message_delivery.send_with_retry(reserve_msg, seller_address)
           if success_seller[0]:
               logging.info(f"Sent RESERVE message to seller {offer['seller']}")

           if success_buyer[0] and success_seller[0]:
               logging.info(f"Successfully completed offer acceptance for search {search_id}")
           else:
               raise Exception("Failed to notify buyer or seller")

       except Exception as e:
           logging.error(f"Error handling accepted offer: {e}")
           self._cleanup_reservation(search_id)

    def handle_refuse(self, msg: Message, client_address: tuple):
        try:
            if msg.rq_number not in self.active_searches:
                logging.warning(f"Refuse received for inactive search: {msg.rq_number}")
                return

            search_request = self.active_searches[msg.rq_number]
            self._notify_buyer_not_found(msg.rq_number, search_request, msg.params)

            self._cleanup_search(msg.rq_number)
            logging.info(f"Negotiation refused for search {msg.rq_number}")

        except Exception as e:
            logging.error(f"Error handling refuse: {e}")

    def _notify_buyer_not_found(self, search_id: str, search_request: SearchRequest, params: dict):
        try:
            not_found_msg = self.message_handler.create_message(
                    MessageType.NOT_FOUND,
                    search_id,
                    item_name=params["item_name"],
                    max_price=params["max_price"]
                    )
            buyer_data = self.registration_data[search_request.buyer_name]
            buyer_address = (buyer_data["ip"], buyer_data["udp_port"])
            self.message_delivery.send_with_retry(not_found_msg, buyer_address)
            logging.info(f"Sent NOT_FOUND message to buyer {search_request.buyer_name}")
        except Exception as e:
            logging.error(f"Error notifying buyer about not found: {e}")


    def handle_cancel(self, msg: Message, client_address: tuple):
        try:
            search_id = msg.rq_number
            if search_id not in self.reservations:
                logging.warning(f"Cancel received for non-existent reservation: {search_id}")
                return

            with self.reservation_lock:
                reservation = self.reservations[search_id]
                seller_data = self.registration_data[reservation.seller]
                self._notify_seller_cancel(search_id, seller_data, msg.params)
                del self.reservations[search_id]

            logging.info(f"Cancelled reservation for search {search_id}")

        except Exception as e:
            logging.error(f"Error handling cancel: {e}")

    def _notify_seller_cancel(self, search_id: str, seller_data: dict, params: dict):
        try:
            cancel_msg = self.message_handler.create_message(
                    MessageType.CANCEL,
                    search_id,
                    item_name=params["item_name"],
                    price=params["price"]
                    )
            seller_address = (seller_data["ip"], seller_data["udp_port"])
            self.message_delivery.send_with_retry(cancel_msg, seller_address)
            logging.info(f"Notified seller about cancellation")
        except Exception as e:
            logging.error(f"Error notifying seller about cancellation: {e}")

    def _cleanup_search(self, search_id: str):
        try:
            with self.search_lock:
                if search_id in self.active_searches:
                    del self.active_searches[search_id]
                    self.timeout_manager.cancel_timer(search_id)
        except Exception as e:
            logging.error(f"Error cleaning up search: {e}")

    def _cleanup_reservation(self, search_id: str):
        try:
            with self.reservation_lock:
                if search_id in self.reservations:
                    del self.reservations[search_id]
        except Exception as e:
            logging.error(f"Error cleaning up reservation: {e}")


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
               threading.Thread(target=self.handle_tcp_client,
                             args=(client_socket, client_address)).start()
           except socket.timeout:
               continue
           except Exception as e:
               if self.running:
                   logging.error(f"TCP listening error: {e}")


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
           self._send_error_response("0000", "Internal server error", client_address)

    def handle_tcp_client(self, client_socket: socket.socket, client_address: tuple):
       try:
           client_socket.settimeout(30)
           while self.running:
               try:
                   data = client_socket.recv(1024)
                   if not data:
                       break

                   message = data.decode()
                   logging.info(f"Received TCP message from {client_address}: {message}")

                   msg = self.message_handler.parse_message(message)
                   if not msg:
                       error_response = self.message_handler.create_message(
                           MessageType.ERROR,
                           "0000",
                           message="Invalid message format"
                       )
                       client_socket.send(error_response.encode())
                       break

                   if msg.command in [MessageType.BUY, MessageType.INFORM_REQ,
                                      MessageType.INFORM_RES, MessageType.SHIPPING_INFO]:
                       self.handle_tcp_message(msg, client_socket, client_address)
                   else:
                       error_response = self.message_handler.create_message(
                           MessageType.ERROR,
                           msg.rq_number,
                           message="Invalid message type for TCP"
                       )
                       client_socket.send(error_response.encode())

               except socket.timeout:
                   logging.warning(f"TCP connection timeout for {client_address}")
                   break
               except Exception as e:
                   logging.error(f"Error processing TCP message: {e}")
                   break

       except Exception as e:
           logging.error(f"Error handling TCP client: {e}")
       finally:
           try:
               client_socket.close()
           except:
               pass


    def route_message(self, msg: Message, client_address: tuple):
       try:
           handlers = {
               MessageType.REGISTER: self.handle_registration,
               MessageType.DE_REGISTER: self.handle_deregistration,
               MessageType.LOOKING_FOR: self.handle_looking_for,
               MessageType.OFFER: self.handle_offer,
               MessageType.ACCEPT: self.handle_accept,
               MessageType.REFUSE: self.handle_refuse,
               MessageType.CANCEL: self.handle_cancel
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
