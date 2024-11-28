import json
import logging
import shlex
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

class MessageType(Enum):
    REGISTER = "REGISTER"
    REGISTERED = "REGISTERED"
    REGISTER_DENIED = "REGISTER-DENIED"
    DE_REGISTER = "DE-REGISTER"
    DE_REGISTERED = "DE-REGISTERED"
    LOOKING_FOR = "LOOKING_FOR"
    SEARCH = "SEARCH"
    SEARCH_ACK = "SEARCH_ACK"
    OFFER = "OFFER"
    NEGOTIATE = "NEGOTIATE"
    ACCEPT = "ACCEPT"
    REFUSE = "REFUSE"
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    RESERVE = "RESERVE"
    ERROR = "ERROR"
    CANCEL = "CANCEL"
    BUY = "BUY"
    BUY_ACK = "BUY_ACK"
    INFORM_REQ = "INFORM_REQ"
    INFORM_RES = "INFORM_RES"
    SHIPPING_INFO = "SHIPPING_INFO"
    TRANSACTION_SUCCESS = "TRANSACTION_SUCCESS"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"

@dataclass
class Message:
    command: MessageType
    rq_number: str
    params: Dict[str, Any]

class MessageHandler:
    def __init__(self):
        self.supported_commands = {cmd.value: cmd for cmd in MessageType}

    @staticmethod
    def validate_request_number(rq: str) -> bool:
        """Validate request number format."""
        try:
            return len(rq) == 4 and rq.isdigit()
        except:
            return False

    @staticmethod
    def validate_credit_card(cc_number: str, cc_exp_date: str) -> bool:
        """Basic credit card validation."""
        try:
            # Check credit card number
            if not cc_number.isdigit() or len(cc_number) < 13 or len(cc_number) > 19:
                return False

            # Validate expiration date format (MM/YY)
            if not cc_exp_date.count('/') == 1:
                return False

            month, year = cc_exp_date.split('/')
            if not (month.isdigit() and year.isdigit()):
                return False

            month_num = int(month)
            if not (1 <= month_num <= 12):
                return False

            return True
        except:
            return False

    def parse_message(self, message: str) -> Optional[Message]:
        """Parse incoming message string into Message object."""
        try:
            parts = shlex.split(message)
            if len(parts) < 2:
                logging.error("Invalid message format: insufficient parts")
                return None

            command_str = parts[0]
            if command_str not in self.supported_commands:
                logging.error(f"Invalid command: {command_str}")
                return None

            command = self.supported_commands[command_str]
            rq = parts[1]

            if not self.validate_request_number(rq):
                logging.error(f"Invalid request number: {rq}")
                return None

            params = {}
            if len(parts) > 2:
                params = self.parse_params(command, parts[2:])
                if params is None:  # Invalid parameters
                    return None

            return Message(command=command, rq_number=rq, params=params)

        except Exception as e:
            logging.error(f"Error parsing message: {e}")
            return None

    def parse_params(self, command: MessageType, param_parts: list) -> Optional[Dict[str, Any]]:
        """Parse command parameters based on message type."""
        try:
            params = {}

            if command == MessageType.REGISTER:
                if len(param_parts) < 4:
                    logging.error("Insufficient parameters for REGISTER")
                    return None
                params = {
                    "name": param_parts[0].strip('"'),
                    "ip": param_parts[1],
                    "udp_port": int(param_parts[2]),
                    "tcp_port": int(param_parts[3])
                }

            elif command == MessageType.DE_REGISTER:
                params = {"name": param_parts[0].strip('"')}

            elif command == MessageType.REGISTER_DENIED:
                params = {"reason": " ".join(param_parts)}

            elif command == MessageType.LOOKING_FOR:
                if len(param_parts) < 4:
                    logging.error("Insufficient parameters for LOOKING_FOR")
                    return None
                params = {
                    "name": param_parts[0].strip('"'),
                    "item_name": param_parts[1].strip('"'),
                    "item_description": param_parts[2].strip('"'),
                    "max_price": float(param_parts[3])
                }

            elif command == MessageType.SEARCH:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for SEARCH")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "item_description": param_parts[1].strip('"')
                }

            elif command == MessageType.SEARCH_ACK:
                params = {"item_name": param_parts[0].strip('"')}

            elif command == MessageType.OFFER:
                if len(param_parts) < 3:
                    logging.error("Insufficient parameters for OFFER")
                    return None
                params = {
                    "name": param_parts[0].strip('"'),
                    "item_name": param_parts[1].strip('"'),
                    "price": float(param_parts[2])
                }

            elif command == MessageType.NEGOTIATE:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for NEGOTIATE")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "max_price": float(param_parts[1])
                }

            elif command == MessageType.ACCEPT:
                if len(param_parts) < 3:
                    logging.error("Insufficient parameters for ACCEPT")
                    return None
                params = {
                    "name": param_parts[0].strip('"'),
                    "item_name": param_parts[1].strip('"'),
                    "price": float(param_parts[2])
                }

            elif command == MessageType.REFUSE:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for REFUSE")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "max_price": float(param_parts[1])
                }

            elif command == MessageType.FOUND:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for FOUND")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "price": float(param_parts[1])
                }

            elif command == MessageType.NOT_FOUND:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for NOT_FOUND")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "max_price": float(param_parts[1])
                }

            elif command == MessageType.NOT_AVAILABLE:
                params = {"item_name": param_parts[0].strip('"')}

            elif command == MessageType.RESERVE:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for RESERVE")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "price": float(param_parts[1])
                }

            elif command == MessageType.ERROR:
                params = {"message": " ".join(param_parts)}

            elif command == MessageType.CANCEL:
                if len(param_parts) >= 1:
                    params = {"reason": " ".join(param_parts)}
                else:
                    params = {"item_name": param_parts[0].strip('"')}

            elif command == MessageType.BUY:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for BUY")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "price": float(param_parts[1])
                }

            elif command == MessageType.INFORM_REQ:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for INFORM_REQ")
                    return None
                params = {
                    "item_name": param_parts[0].strip('"'),
                    "price": float(param_parts[1])
                }

            elif command == MessageType.INFORM_RES:
                if len(param_parts) < 4:
                    logging.error("Insufficient parameters for INFORM_RES")
                    return None
                name = param_parts[0].strip('"')
                cc_number = param_parts[1]
                cc_exp_date = param_parts[2]

                if not self.validate_credit_card(cc_number, cc_exp_date):
                    logging.error("Invalid credit card information")
                    return None

                params = {
                    "name": name,
                    "cc_number": cc_number,
                    "cc_exp_date": cc_exp_date,
                    "address": " ".join(param_parts[3:]).strip('"')
                }

            elif command == MessageType.SHIPPING_INFO:
                if len(param_parts) < 2:
                    logging.error("Insufficient parameters for SHIPPING_INFO")
                    return None
                params = {
                    "name": param_parts[0].strip('"'),
                    "address": " ".join(param_parts[1:]).strip('"')
                }

            return params

        except Exception as e:
            logging.error(f"Error parsing parameters for {command}: {e}")
            return None

    def create_message(self, command: MessageType, rq_number: str, **params) -> str:
        """Create formatted message string."""
        try:
            msg_parts = [command.value, rq_number]

            if command == MessageType.REGISTER:
                msg_parts.extend([
                    f'"{params["name"]}"',
                    params["ip"],
                    str(params["udp_port"]),
                    str(params["tcp_port"])
                ])

            elif command == MessageType.DE_REGISTER:
                msg_parts.append(f'"{params["name"]}"')

            elif command == MessageType.LOOKING_FOR:
                msg_parts.extend([
                    f'"{params["name"]}"',
                    f'"{params["item_name"]}"',
                    f'"{params.get("item_description", "")}"',
                    str(params["max_price"])
                ])

            elif command == MessageType.SEARCH:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    f'"{params.get("item_description", "")}"'
                ])

            elif command == MessageType.SEARCH_ACK:
                msg_parts.append(f'"{params["item_name"]}"')

            elif command == MessageType.OFFER:
                msg_parts.extend([
                    f'"{params["name"]}"',
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])

            elif command == MessageType.NEGOTIATE:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["max_price"])
                ])

            elif command == MessageType.ACCEPT:
                msg_parts.extend([
                    f'"{params["name"]}"',
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])

            elif command == MessageType.REFUSE:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["max_price"])
                ])

            elif command == MessageType.FOUND:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])

            elif command == MessageType.NOT_FOUND:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["max_price"])
                ])

            elif command == MessageType.NOT_AVAILABLE:
                msg_parts.append(f'"{params["item_name"]}"')

            elif command == MessageType.RESERVE:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])

            elif command == MessageType.REGISTER_DENIED:
                msg_parts.append(params["reason"])

            elif command == MessageType.ERROR:
                msg_parts.append(params["message"])

            elif command == MessageType.CANCEL:
                if "reason" in params:
                    msg_parts.append(params["reason"])
                else:
                    msg_parts.extend([
                        f'"{params["item_name"]}"',
                        str(params["price"])
                    ])

            elif command == MessageType.BUY:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])

            elif command == MessageType.INFORM_REQ:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])

            elif command == MessageType.INFORM_RES:
                msg_parts.extend([
                    f'"{params["name"]}"',
                    params["cc_number"],
                    params["cc_exp_date"],
                    f'"{params["address"]}"'
                ])

            elif command == MessageType.SHIPPING_INFO:
                msg_parts.extend([
                    f'"{params["name"]}"',
                    f'"{params["address"]}"'
                ])

            return " ".join(msg_parts)

        except Exception as e:
            logging.error(f"Error creating message: {e}")
            raise
