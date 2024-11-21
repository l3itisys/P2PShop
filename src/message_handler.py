import json
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging
import shlex
from enum import Enum

class MessageType(Enum):
    REGISTER = "REGISTER"
    REGISTERED = "REGISTERED"
    REGISTER_DENIED = "REGISTER-DENIED"
    DE_REGISTER = "DE-REGISTER"
    DE_REGISTERED = "DE-REGISTERED"
    LOOKING_FOR = "LOOKING_FOR"
    SEARCH = "SEARCH"
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

@dataclass
class Message:
    command: MessageType
    rq_number: str
    params: Dict[str, Any]

class MessageHandler:
    @staticmethod
    def validate_request_number(rq: str) -> bool:
        """Validate request number format"""
        try:
            return len(rq) == 4 and rq.isdigit()
        except:
            return False

    @staticmethod
    def parse_message(message: str) -> Optional[Message]:
        """Parse incoming messages into structured format"""
        try:
            parts = shlex.split(message)
            logging.debug(f"Parsed message parts: {parts}")
            if len(parts) < 2:
                logging.error("Invalid message format: insufficient parts")
                return None

            try:
                command = MessageType(parts[0])
            except ValueError:
                logging.error(f"Invalid command: {parts[0]}")
                return None

            rq = parts[1]
            if not MessageHandler.validate_request_number(rq):
                logging.error(f"Invalid request number: {rq}")
                return None

            params = {}
            if len(parts) > 2:
                try:
                    params = MessageHandler.parse_params(command, parts[2:])
                except Exception as e:
                    logging.error(f"Error parsing parameters: {e}")
                    return None

            return Message(command=command, rq_number=rq, params=params)

        except Exception as e:
            logging.error(f"Error parsing message: {e}")
            return None

    @staticmethod
    def parse_params(command: MessageType, param_parts: list) -> Dict[str, Any]:
        """Parse parameters based on command type"""
        params = {}

        try:
            if command == MessageType.REGISTER:
                # Handle name with spaces and quotes
                name = ''
                index = 0
                if param_parts[0].startswith('"'):
                    while index < len(param_parts):
                        name_part = param_parts[index]
                        name += name_part + ' '
                        if name_part.endswith('"'):
                            break
                        index += 1
                    name = name.strip().strip('"')
                    index += 1
                else:
                    name = param_parts[0]
                    index = 1

                ip = param_parts[index]
                udp_port = int(param_parts[index + 1])
                tcp_port = int(param_parts[index + 2])

                params = {
                    "name": name,
                    "ip": ip,
                    "udp_port": udp_port,
                    "tcp_port": tcp_port
                }

            elif command == MessageType.DE_REGISTER:
                params = {"name": param_parts[0].strip('"')}
            elif command == MessageType.LOOKING_FOR:
                name = param_parts[0].strip('"')
                item_name = param_parts[1].strip('"')
                max_price = float(param_parts[2])
                params = {
                    "name": name,
                    "item_name": item_name,
                    "max_price": max_price
                }
            elif command == MessageType.SEARCH:
                params = {"item_name": param_parts[0].strip('"')}
            elif command == MessageType.OFFER:
                name = param_parts[0].strip('"')
                item_name = param_parts[1].strip('"')
                price = float(param_parts[2])
                params = {
                    "name": name,
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.NEGOTIATE:
                item_name = param_parts[0].strip('"')
                max_price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "max_price": max_price
                }
            elif command == MessageType.ACCEPT:
                name = param_parts[0].strip('"')
                item_name = param_parts[1].strip('"')
                price = float(param_parts[2])
                params = {
                    "name": name,
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.REFUSE:
                item_name = param_parts[0].strip('"')
                max_price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "max_price": max_price
                }
            elif command == MessageType.FOUND:
                item_name = param_parts[0].strip('"')
                price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.NOT_FOUND:
                item_name = param_parts[0].strip('"')
                max_price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "max_price": max_price
                }
            elif command == MessageType.NOT_AVAILABLE:
                item_name = param_parts[0].strip('"')
                params = {"item_name": item_name}
            elif command == MessageType.REGISTER_DENIED:
                reason = " ".join(param_parts)
                params = {"reason": reason}
            elif command == MessageType.ERROR:
                message = " ".join(param_parts)
                params = {"message": message}
            elif command == MessageType.RESERVE:
                item_name = param_parts[0].strip('"')
                price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.CANCEL:
                item_name = param_parts[0].strip('"')
                price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "price": price
                }
            else:
                # Handle other commands if necessary
                pass

            return params

        except (IndexError, ValueError) as e:
            logging.error(f"Error parsing parameters for {command}: {e}")
            raise

    @staticmethod
    def create_message(command: MessageType, rq_number: str, **params) -> str:
        """Create formatted message with parameters"""
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
                    str(params["max_price"])
                ])
            elif command == MessageType.SEARCH:
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
            elif command == MessageType.REGISTER_DENIED:
                msg_parts.append(params.get("reason", ""))
            elif command == MessageType.ERROR:
                msg_parts.append(params["message"])
            elif command == MessageType.RESERVE:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])
            elif command == MessageType.CANCEL:
                msg_parts.extend([
                    f'"{params["item_name"]}"',
                    str(params["price"])
                ])
            else:
                # Handle other commands if necessary
                pass

            return " ".join(msg_parts)

        except Exception as e:
            logging.error(f"Error creating message: {e}")
            raise

