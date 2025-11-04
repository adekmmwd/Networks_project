import socket
import json
import uuid
import time
from collections import deque
from enum import Enum, auto


class ClientState(Enum):
    WAIT_FOR_JOIN = 1
    WAIT_FOR_READY = 2
    WAIT_FOR_STARTGAME = 3
    IN_GAME_LOOP = 4
    GAME_OVER = 5


TICK = 0.05
JOIN_RESEND = 0.25
READY_RESEND = 0.25
ACQUIRE_RESEND = 0.15
START_TIMEOUT = 2.0


class ClientHeaders:
    def __init__(self, color="red", position=(0, 0)):
        self.id = str(uuid.uuid4())  # unique client id
        self.color = color
        self.position = position
        self.score = 0
        self.start_time = None

    def start_timer(self):
        self.start_time = time.time()

    def time_elapsed(self):
        return time.time() - self.start_time if self.start_time else 0


class ClientFSM:
    def __init__(self, socket, client_headers, server_address):
        self.sock = socket
        self.server_addr = server_address
        self.headers = client_headers
        self.state = ClientState.WAIT_FOR_JOIN
        self.last_send_time = 0
        self.last_ack_time = 0
        self.last_acquire_time = 0
        self.last_snapshot = 0
        self.snapshot_buffer = deque(maxlen=10)
        self.recent_transition = 0
        self.pending_acquire = None
        self.running = True
        self.sock.settimeout(TICK)


def transition(self, new_state):
    print(f" Transition: {self.state.name} → {new_state.name}")
    self.state = new_state
    self.recent_transition = 1


def send(self, msg_dict):
    self.sock.sendto(json.dumps(msg_dict).encode(), self.server_addr)


def recv(self):
    try:
        data, _ = self.sock.recvfrom(4096)
        return json.loads(data.decode())
    except socket.timeout:
        return None


def run(self):
    print(f"client: {self.headers.id} started")
    print(f"client: state: {self.state.name}")
    while self.running:
        if self.state == ClientState.WAIT_FOR_JOIN:
            self.handle_join()
        elif self.state == ClientState.WAIT_FOR_READY:
            self.handle_ready()
        elif self.state == ClientState.WAIT_FOR_STARTGAME:
            self.handle_start_game()
        elif self.state == ClientState.IN_GAME_LOOP:
            self.handle_game_loop()
        elif self.state == ClientState.GAME_OVER:
            self.handle_game_over()

        time.sleep(self.TICK)


def handle_join(self):
    curr_time = time.time()

    if curr_time - self.last_send_time >= START_TIMEOUT or self.last_send_time == 0:

        join_req = {"type": "join_req", "client_id": self.headers.id}
        self.send(join_req)
        print("Sent join request")
        self.last_send_time = curr_time

        msg = self.recv()
        if msg and msg["type"] == "join_ack":
            print("recieved join ack")
            self.transition(ClientState.WAIT_FOR_READY)


def handle_ready(self):
    curr_time = time.time()

    if curr_time - self.last_send_time >= READY_RESEND or self.recent_transition == 1:

        self.recent_transition = 0
        ready_req = {"type": "ready_req", "client_id": self.headers.id}
        self.send(ready_req)
        print("→ Sent Ready")
        self.last_send_time = curr_time

        msg = self.recv()
        if msg["type"] == "ready_ack":
            print("ready ACK Received")
            self.transition(ClientState.WAIT_FOR_STARTGAME)


def handle_start_game(self):
    msg = self.recv()
    curr_time = time.time()

    if msg and msg["type"] == "Snapshot_full":
        snapshot_id = msg.get["snapshot_id"]
        self.last_snapshot_id = msg["snapshot_id"]
        print(f"full snapshot ID: {snapshot_id} Recieved")
        ack_msg = {
            "type": "ack",
            "client_id": self.headers.id,
            "snapshot_id": snapshot_id,
        }
        self.send(ack_msg)
        self.transition(ClientState.IN_GAME_LOOP)

    elif curr_time - self.last_acquire_time > START_TIMEOUT or self.recent_transition == 1:
        self.recent_transition = 0
        ready_msg = {"type": "ready_req", "client_id": self.headers.id}
        self.send(ready_msg)
        print("Waiting for full Snapshot")
        self.last_send_time = curr_time


def handle_game_loop(self):
    msg = self.recv()
    curr_time = time.time()
    msg_type = msg.get["type"]
    if msg_type in ("Snapshot_full", "snapshot_delta"):
        snapshot_id = msg.get("snapshot_id")
        payload = msg.get("data", {})
        if snapshot_id <= self.last_snapshot_id or snapshot_id - self.last_snapshot_id > 1:
            print(f"⚠️ Ignored outdated snapshot #{snapshot_id} (last {self.last_snapshot_id})")

        ##
        # update snapshot or delta to game state here
        ##
        else:
            self.last_snapshot_id = snapshot_id
            self.last_ack_time = curr_time

            ack_msg = {"type": "ack", "client_id": self.headers.id, "snapshot_id": snapshot_id}
            self.send(ack_msg)
            print(f"✔️ Applied snapshot #{snapshot_id} and sent ACK")

    ##
    ##acquire cell logic here
    ##

    elif msg_type == "GAME_OVER":
        print("Game Over message received")
        self.transition(ClientState.GAME_OVER)
        return


def handle_game_over(self):
    print("🏁 Game over. Cleaning up...")
    over_ack = {"type": "game_over_ack", "client_id": self.headers.id}
    self.send(over_ack)
    self.sock.close()
    self.running = False
    print("🔒 Connection closed.")



def main():
    server_address = ("127.0.0.1", 1234)
    clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    clientSocket.settimeout(TICK)

    headers = ClientHeaders()
    fsm = ClientFSM(headers, clientSocket, server_address)

    print(f"Client started with ID: {headers.id}")
    print(f"Initial state: {fsm.state.name}")

    fsm.run()


if __name__ == "__main__":
    main()
