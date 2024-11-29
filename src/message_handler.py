import shlex
import logging
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
            return len(rq) > 0 and rq.isdigit()
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
            if command == MessageType.REGISTER:
                params["name"] = parts[2]
                params["ip"] = parts[3]
                params["udp_port"] = int(parts[4])
                params["tcp_port"] = int(parts[5])
            elif command == MessageType.REGISTERED:
                pass
            elif command == MessageType.REGISTER_DENIED:
                params["reason"] = parts[2]
            elif command == MessageType.DE_REGISTER:
                params["name"] = parts[2]
            elif command == MessageType.DE_REGISTERED:
                params["name"] = parts[2]
            elif command == MessageType.LOOKING_FOR:
                params["name"] = parts[2]
                params["item_name"] = parts[3]
                params["item_description"] = parts[4]
                params["max_price"] = float(parts[5])
            elif command == MessageType.SEARCH:
                params["item_name"] = parts[2]
                params["item_description"] = parts[3]
            elif command == MessageType.SEARCH_ACK:
                params["item_name"] = parts[2]
            elif command == MessageType.OFFER:
                params["name"] = parts[2]
                params["item_name"] = parts[3]
                params["price"] = float(parts[4])
            elif command == MessageType.NEGOTIATE:
                params["item_name"] = parts[2]
                params["max_price"] = float(parts[3])
            elif command == MessageType.ACCEPT:
                params["name"] = parts[2]
                params["item_name"] = parts[3]
                params["max_price"] = float(parts[4])
            elif command == MessageType.REFUSE:
                params["name"] = parts[2]
                params["item_name"] = parts[3]
                params["max_price"] = float(parts[4])
            elif command == MessageType.FOUND:
                params["item_name"] = parts[2]
                params["price"] = float(parts[3])
            elif command == MessageType.NOT_FOUND:
                params["item_name"] = parts[2]
                params["max_price"] = float(parts[3])
            elif command == MessageType.NOT_AVAILABLE:
                params["item_name"] = parts[2]
            elif command == MessageType.RESERVE:
                params["item_name"] = parts[2]
                params["price"] = float(parts[3])
            elif command == MessageType.BUY:
                params["item_name"] = parts[2]
                params["price"] = float(parts[3])
            elif command == MessageType.BUY_ACK:
                params["seller_ip"] = parts[2]
                params["seller_tcp_port"] = int(parts[3])
            elif command == MessageType.INFORM_REQ:
                params["item_name"] = parts[2]
                params["price"] = float(parts[3])
            elif command == MessageType.INFORM_RES:
                params["name"] = parts[2]
                params["cc_number"] = parts[3]
                params["cc_exp_date"] = parts[4]
                params["address"] = parts[5]
            elif command == MessageType.SHIPPING_INFO:
                params["name"] = parts[2]
                params["address"] = parts[3]
            elif command == MessageType.TRANSACTION_SUCCESS:
                pass
            elif command == MessageType.TRANSACTION_FAILED:
                params["reason"] = parts[2]
            elif command == MessageType.CANCEL:
                params["item_name"] = parts[2]
                params["price"] = float(parts[3])
            elif command == MessageType.ERROR:
                params["message"] = parts[2]
            else:
                # Handle other message types as needed
                pass

            return Message(command=command, rq_number=rq, params=params)

        except Exception as e:
            logging.error(f"Error parsing message: {e}")
            return None

    def create_message(self, command: MessageType, rq_number: str, **params) -> str:
        """Create formatted message string."""
        try:
            msg_parts = [command.value, rq_number]

            if command == MessageType.REGISTER:
                msg_parts.extend([
                    params["name"],
                    params["ip"],
                    str(params["udp_port"]),
                    str(params["tcp_port"])
                ])
            elif command == MessageType.REGISTERED:
                pass
            elif command == MessageType.REGISTER_DENIED:
                msg_parts.append(params["reason"])
            elif command == MessageType.DE_REGISTER:
                msg_parts.append(params["name"])
            elif command == MessageType.DE_REGISTERED:
                msg_parts.append(params["name"])
            elif command == MessageType.LOOKING_FOR:
                msg_parts.extend([
                    params["name"],
                    params["item_name"],
                    params.get("item_description", ""),
                    str(params["max_price"])
                ])
            elif command == MessageType.SEARCH:
                msg_parts.extend([
                    params["item_name"],
                    params.get("item_description", "")
                ])
            elif command == MessageType.SEARCH_ACK:
                msg_parts.append(params["item_name"])
            elif command == MessageType.OFFER:
                msg_parts.extend([
                    params["name"],
                    params["item_name"],
                    str(params["price"])
                ])
            elif command == MessageType.NEGOTIATE:
                msg_parts.extend([
                    params["item_name"],
                    str(params["max_price"])
                ])
            elif command == MessageType.ACCEPT:
                msg_parts.extend([
                    params["name"],
                    params["item_name"],
                    str(params["max_price"])
                ])
            elif command == MessageType.REFUSE:
                msg_parts.extend([
                    params["name"],
                    params["item_name"],
                    str(params["max_price"])
                ])
            elif command == MessageType.FOUND:
                msg_parts.extend([
                    params["item_name"],
                    str(params["price"])
                ])
            elif command == MessageType.NOT_FOUND:
                msg_parts.extend([
                    params["item_name"],
                    str(params["max_price"])
                ])
            elif command == MessageType.NOT_AVAILABLE:
                msg_parts.append(params["item_name"])
            elif command == MessageType.RESERVE:
                msg_parts.extend([
                    params["item_name"],
                    str(params["price"])
                ])
            elif command == MessageType.BUY:
                msg_parts.extend([
                    params["item_name"],
                    str(params["price"])
                ])
            elif command == MessageType.BUY_ACK:
                msg_parts.extend([
                    params["seller_ip"],
                    str(params["seller_tcp_port"])
                ])
            elif command == MessageType.INFORM_REQ:
                msg_parts.extend([
                    params["item_name"],
                    str(params["price"])
                ])
            elif command == MessageType.INFORM_RES:
                msg_parts.extend([
                    params["name"],
                    params["cc_number"],
                    params["cc_exp_date"],
                    params["address"]
                ])
            elif command == MessageType.SHIPPING_INFO:
                msg_parts.extend([
                    params["name"],
                    params["address"]
                ])
            elif command == MessageType.TRANSACTION_SUCCESS:
                pass
            elif command == MessageType.TRANSACTION_FAILED:
                msg_parts.append(params["reason"])
            elif command == MessageType.CANCEL:
                msg_parts.extend([
                    params["item_name"],
                    str(params["price"])
                ])
            elif command == MessageType.ERROR:
                msg_parts.append(params.get("message", ""))
            else:
                # Handle other message types as needed
                pass

            # Quote all string parameters (excluding numbers)
            message_parts = [str(msg_parts[0]), str(msg_parts[1])]
            for part in msg_parts[2:]:
                if isinstance(part, (int, float)):
                    message_parts.append(str(part))
                else:
                    message_parts.append(f'"{str(part)}"')
            message = " ".join(message_parts)
            return message

        except Exception as e:
            logging.error(f"Error creating message: {e}")
            raise

