# UDP/TCP Client-Server Registration System

A lightweight client-server application written in Python for handling user registration over both UDP and TCP protocols. This project emphasizes robust communication, multithreading, and structured message handling between distributed clients and a central server.

---

## 🧠 Features

- Register and deregister clients with unique IP/TCP/UDP configuration
- Supports both **UDP** (for control messages) and **TCP** (for extended messaging)
- Handles communication errors and retries with exponential backoff
- Thread-safe server implementation using Python's `threading`
- Human-readable, logged communication and registration history
- Built-in signal handling for graceful shutdowns
- JSON-based persistent user registry

---

## 🛠️ Requirements

- Python 3.8+
- Standard library only (no external dependencies)

To verify your Python version:

```bash
python3 --version
```

---

## ▶️ How to Run

### 1. Start the Server

In one terminal:

```bash
python3 server.py
```

You’ll see output like:

```
Server UDP listening on port 3000
Server TCP listening on port 3001
Server running... (Press Ctrl+C to stop)
```

---

### 2. Start the Client

In a separate terminal:

```bash
python3 client.py
```

Then follow the interactive prompts to:
- Enter your name
- Enter TCP port
- Send `register`, `deregister`, or `tcp` messages

Example usage:
```
Enter server IP address (or 'localhost'): localhost
Enter client TCP port (1024–65535): 5001
Enter your first name: Alice
Enter your last name: Smith

> register
> tcp
> deregister
> exit
```

---

## 💬 Supported Commands (from client)

| Command     | Description                          |
|-------------|--------------------------------------|
| `register`  | Register your identity to the server |
| `deregister`| Remove yourself from the registry    |
| `tcp`       | Send a custom TCP message            |
| `help`      | Show all commands                    |
| `exit`      | Exit the client                      |

---

## 🗃️ Persistent Registration

Registered clients are saved to `registrations.json` like this:

```json
{
  "Alice Smith": {
    "ip": "127.0.0.1",
    "udp_port": 50123,
    "tcp_port": 5001
  }
}
```

---

## 🧪 Logging

Both `client.py` and `server.py` write detailed logs to:

- `logs/client.log`
- `logs/server.log`

---

## 📚 Learning Outcomes

- Socket programming (UDP & TCP)
- Message parsing and protocol design
- Concurrency using Python’s `threading`
- Robust user interaction and error handling
- JSON-based persistence and logging

---

## 📄 License

MIT License. See `LICENSE` file for details.
