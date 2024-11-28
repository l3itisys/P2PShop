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
    INFORM_REQ = "INFORM_REQ"
    INFORM_RES = "INFORM_RES"
    SHIPPING_INFO = "SHIPPING_INFO"

@dataclass
class Message:
    command: MessageType
    rq_number: str
    params: Dict[str, Any]

class MessageHandler:
    @staticmethod
    def validate_request_number(rq: str) -> bool:
        try:
            return len(rq) == 4 and rq.isdigit()
        except:
            return False

    @staticmethod
    def parse_message(message: str) -> Optional[Message]:
        try:
            parts = shlex.split(message)
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
        params = {}
        try:
            if command == MessageType.REGISTER:
                name = param_parts[0].strip('"')
                ip = param_parts[1]
                udp_port = int(param_parts[2])
                tcp_port = int(param_parts[3])
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
            elif command == MessageType.SEARCH_ACK:
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
                params = {"item_name": param_parts[0].strip('"')}
            elif command == MessageType.RESERVE:
                item_name = param_parts[0].strip('"')
                price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.REGISTER_DENIED:
                params = {"reason": " ".join(param_parts)}
            elif command == MessageType.ERROR:
                params = {"message": " ".join(param_parts)}
            elif command == MessageType.BUY:
                item_name = param_parts[0].strip('"')
                price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.INFORM_REQ:
                item_name = param_parts[0].strip('"')
                price = float(param_parts[1])
                params = {
                    "item_name": item_name,
                    "price": price
                }
            elif command == MessageType.INFORM_RES:
                name = param_parts[0].strip('"')
                cc_number = param_parts[1]
                cc_exp_date = param_parts[2]
                address = " ".join(param_parts[3:]).strip('"')
                params = {
                    "name": name,
                    "cc_number": cc_number,
                    "cc_exp_date": cc_exp_date,
                    "address": address
                }
            elif command == MessageType.SHIPPING_INFO:
                name = param_parts[0].strip('"')
                address = " ".join(param_parts[1:]).strip('"')
                params = {
                    "name": name,
                    "address": address
                }

            return params

        except (IndexError, ValueError) as e:
            logging.error(f"Error parsing parameters for {command}: {e}")
            raise

    @staticmethod
    def create_message(command: MessageType, rq_number: str, **params) -> str:
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
