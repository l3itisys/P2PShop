import json
from dataclasses import dataclass
from typing import Optional, Dict, Any
import logging
import shlex
import time

@dataclass
class Message:
    command: str
    rq_number: str
    params: Dict[str, Any]

class MessageHandler:
    @staticmethod
    def parse_message(message: str) -> Optional[Message]:
        """Parse incoming messages into structured format"""
        try:
            parts = message.split(maxsplit=2)
            if len(parts) < 2:
                return None

            command, rq = parts[:2]
            params = {}

            if len(parts) > 2:
                if command == "REGISTER":
                    param_parts = shlex.split(parts[2])
                    params = {
                        "name": param_parts[0],
                        "ip": param_parts[1],
                        "udp_port": int(param_parts[2]),
                        "tcp_port": int(param_parts[3])
                    }
                elif command == "DE-REGISTER":
                    params = {"name": shlex.split(parts[2])[0]}
                elif command == "test":
                    params = {"test": True}

            return Message(command=command, rq_number=rq, params=params)
        except Exception as e:
            logging.error(f"Error parsing message: {e}")
            return None

    @staticmethod
    def create_response(command: str, rq_number: str, message: str = "") -> str:
        """Create formatted response messages"""
        return f"{command} {rq_number} {message}".strip()
