import asyncio 
from socket import *
import dataclasses
import enum
import time
import json 
import numpy as np
from header import * 


@dataclasses.dataclass
class Player:
    id: int
    address: tuple
    ready: bool = False
    last_update_time: float = 0
    last_snapshot_id: int = 0
    state_data: dict = dataclasses.field(default_factory=dict)
    score: int = 0


class ServerState(enum.Enum):
    WAITING_FOR_JOIN = 1
    WAITING_FOR_INIT = 2
    GAME_LOOP = 3
    GAME_OVER = 4


class GameServer:
    def __init__(self):
        #server fields
        self.server_socket = socket(AF_INET, SOCK_DGRAM)
        self.server_socket.bind(('', 8888))
        self.state = ServerState.WAITING_FOR_JOIN
        self.seq_num = 0

        #game fields
        self.players = {}
        self.game_running = False
        self.ready_count = 0
        self.last_broadcast_time = time.time()

        #time fields
        self.interval = 0.05
        self.join_time_gap_allowed = 10
        self.game_start_time = 0

        #snapshot fields
        self.last_snapshot_deltas = []
        self.current_snapshot = {}
        self.previous_snapshot = {}
        self.snapshot_id = 0





async def state_waiting_for_join(server):

    join_time = time.monotonic()
    loop = asyncio.get_event_loop()
    server.server_socket.setblocking(False)
    
    while True:
        if  (time.monotonic()-join_time >= server.join_time_gap_allowed and len(server.players) >1) or  server.ready_count >= len(server.players)/2:
            return ServerState.WAITING_FOR_INIT
        
        try:
            data, addr = await loop.sock_recvfrom(server.server_socket, 1200)
        except Exception:
            continue

        header, payload = parse_packet(data)
        msg_type = header["msg_type"]
        
         # --- handle join request ---
        if msg_type == MSG_JOIN_REQ:
            if addr in server.players:
                print(f"Ignoring duplicate join from {addr}")
                existing_player = server.players[addr]
                ack_payload = json.dumps({"player_id": existing_player.id}).encode()
                server.seq_num += 1
                ack_packet = make_packet(MSG_JOIN_ACK, payload=ack_payload,seq_num=server.seq_num)
                await loop.sock_sendto(server.server_socket, ack_packet, addr)
                continue

            # Otherwise, new join
            new_id = len(server.players) + 1
            player = Player(id=new_id, address=addr)
            server.players[addr] = player
            print(f"Player {new_id} joined from {addr}")

            # Send join acknowledgment
            ack_payload = json.dumps({"player_id": new_id}).encode()
            server.seq_num += 1
            ack_packet = make_packet(MSG_JOIN_ACK, payload=ack_payload,seq_num=server.seq_num)
            await loop.sock_sendto(server.server_socket, ack_packet, addr)

        # --- handle ready request ---
        elif msg_type == MSG_READY_REQ:
            if addr in server.players:
                server.players[addr].ready = True
                server.ready_count += 1
                print(f"Player {server.players[addr].id} is ready")
                server.seq_num += 1
                ack_packet = make_packet(MSG_READY_ACK, seq_num=server.seq_num)
                await loop.sock_sendto(server.server_socket, ack_packet, addr)



async def  state_waiting_for_init(server):

    print("Sending initial snapshot...")
    loop = asyncio.get_event_loop()
    server.server_socket.setblocking(False)

    server.current_snapshot = {
        "grid": ([[0 for _ in range(20)] for _ in range(20)]),
        "timestamp": time.monotonic(),
        "snapshot_id": server.snapshot_id
    }

    snapshot_payload = json.dumps(server.current_snapshot).encode()
    server.seq_num += 1
    snapshot_packet = make_packet(MSG_SNAPSHOT_FULL, payload=snapshot_payload, snapshot_id=server.snapshot_id, seq_num=server.seq_num)

    for player in server.players.values():
            await loop.sock_sendto(server.server_socket, snapshot_packet, player.address)
            print(f"Sent initial snapshot to Player {player.id}")

    server.snapshot_id += 1
    server.game_running = True
    server.game_start_time = time.monotonic()
    return ServerState.GAME_LOOP

async def  state_game_loop(server):
    print("Entering GAME_LOOP...")
    loop = asyncio.get_event_loop()
    server.server_socket.setblocking(False)

    async def receive_events():
       while server.game_running:
            try:
                data, addr = await loop.sock_recvfrom(server.server_socket, 2048)
            except Exception:
                continue

            header, payload = parse_packet(data)
            msg_type = header["msg_type"]

            if msg_type == MSG_ACQUIRE_EVENT:
                payload_dict = json.loads(payload.decode())
                cell_x, cell_y = payload_dict["x"], payload_dict["y"]
                player = server.players.get(addr)

                if player:
                    
                    if  server.current_snapshot["grid"][cell_y][cell_x]== 0:
                        server.current_snapshot["grid"][cell_y][cell_x] = player.id
                        player.score += 1
                        print(f"Player {player.id} acquired cell ({cell_x}, {cell_y})")
                server.current_snapshot["timestamp"] = time.monotonic()


    async def receive_acks():
       while server.game_running:
            try:
                data, addr = await loop.sock_recvfrom(server.server_socket, 1024)
            except Exception:
                continue

            header, payload = parse_packet(data)
            msg_type = header["msg_type"]

            if msg_type == MSG_SNAPSHOT_ACK:
                ack_info = json.loads(payload.decode())
                snapshot_id = ack_info.get("snapshot_id", 0)

                player = server.players.get(addr)
                if player:
                    player.last_snapshot_id = snapshot_id
                    player.last_update_time = time.monotonic()
                    print(f"ACK from Player {player.id} for snapshot {snapshot_id}")




    async def broadcast_snapshots():
        """Send deltas or full snapshots depending on how far each player is behind."""
        while server.game_running:
            await asyncio.sleep(server.interval)
            server.seq_num += 1
            server.snapshot_id += 1

            # Compute delta from last snapshot (if exists)
            if server.previous_snapshot and "grid" in server.previous_snapshot:
                old_grid = server.previous_snapshot["grid"]
            else:
                old_grid = [[0 for _ in range(20)] for _ in range(20)]


            new_grid = server.current_snapshot["grid"]


            old_arr = np.array(old_grid)
            new_arr = np.array(new_grid)
            diff_indices = np.argwhere(old_arr != new_arr)
            delta_changes = [(int(x), int(y), int(new_arr[y, x])) for y, x in diff_indices]
             

            delta_entry = {
                "snapshot_id": server.snapshot_id,
                "delta": delta_changes,
            }

            server.last_snapshot_deltas.append(delta_entry)
            if len(server.last_snapshot_deltas) > 3:
                server.last_snapshot_deltas.pop(0)

            # Prepare full snapshot packet once (reuse if needed)
            full_payload = json.dumps(server.current_snapshot).encode()
            full_packet = make_packet(MSG_SNAPSHOT_FULL, payload=full_payload,
                                      snapshot_id=server.snapshot_id, seq_num=server.seq_num)

            for player in server.players.values():
                diff = server.snapshot_id - player.last_snapshot_id

                if diff <= len(server.last_snapshot_deltas) and diff > 0:
                    # Combine missed deltas
                    missed = server.last_snapshot_deltas[-diff:]
                    combined_changes = [cell for delta in missed for cell in delta["delta"]]

                    delta_payload = json.dumps({
                        "snapshot_id": server.snapshot_id,
                        "changes": combined_changes
                    }).encode()

                    delta_packet = make_packet(MSG_SNAPSHOT_DELTA, payload=delta_payload,
                                               snapshot_id=server.snapshot_id, seq_num=server.seq_num)

                    await loop.sock_sendto(server.server_socket, delta_packet, player.address)
                    print(f"Sent DELTA snapshot to Player {player.id}")
                else:
                    # Too far behind or no baseline → send full
                    await loop.sock_sendto(server.server_socket, full_packet, player.address)
                    print(f"Sent FULL snapshot to Player {player.id} (resync)")
            
            server.previous_snapshot = {
                "grid": [row.copy() for row in server.current_snapshot["grid"]],
                "timestamp": server.current_snapshot["timestamp"],
                "snapshot_id": server.current_snapshot["snapshot_id"]
            }

            grid_flat = np.array(server.current_snapshot["grid"]).flatten()
            if np.all(grid_flat != 0):
                print("All cells claimed — ending game.")
                server.game_running = False
             

                




            



    tasks = [
    asyncio.create_task(receive_events()),
    asyncio.create_task(broadcast_snapshots()),
    asyncio.create_task(receive_acks())
    ]

    await asyncio.gather(*tasks)


    return ServerState.GAME_OVER

    
async def state_game_over(server):
    print("\n--- GAME OVER ---")


    end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"Game ended at: {end_time}")

    # Calculate game duration
    duration = round(time.monotonic() - server.game_start_time, 2)
    print(f"Total game duration: {duration} seconds")

    # Generate leaderboard
    leaderboard = sorted(server.players.values(), key=lambda p: p.score, reverse=True)

    print("\n=== FINAL LEADERBOARD ===")
    for rank, player in enumerate(leaderboard, start=1):
        print(f"{rank}. Player {player.id} — Score: {player.score}")
    print("==========================\n")

    # --- Broadcast leaderboard to all players ---
    loop = asyncio.get_event_loop()

    leaderboard_data = {
        "type": "leaderboard",
        "results": [
            {"rank": rank, "player_id": player.id, "score": player.score}
            for rank, player in enumerate(leaderboard, start=1)
        ]
    }

    leaderboard_payload = json.dumps(leaderboard_data).encode()
    leaderboard_packet = make_packet(MSG_LEADERBOARD, payload=leaderboard_payload)

    for player in leaderboard:
        await loop.sock_sendto(server.server_socket, leaderboard_packet, player.address)
        print(f"Leaderboard sent to Player {player.id}")

    # Terminate and reset server
    print("Terminating game session...")
    server.server_socket.close()

    # Reopen for next game safely
    server.server_socket = socket(AF_INET, SOCK_DGRAM)
    server.server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    server.server_socket.bind(('', 8888))
    server.server_socket.setblocking(False)
    server.last_broadcast_time = time.time()


    # Reset game state
    server.players.clear()
    server.ready_count = 0
    server.seq_num = 0
    server.snapshot_id = 0
    server.last_snapshot_deltas.clear()
    server.current_snapshot = {}
    server.previous_snapshot = {}
    server.game_running = False
    server.state = ServerState.WAITING_FOR_JOIN

    print("Game session ended. Server ready for next round.")




async def main_loop(server):
    while True:
        if server.state == ServerState.WAITING_FOR_JOIN:
            server.state = await state_waiting_for_join(server)

        elif server.state == ServerState.WAITING_FOR_INIT:
            server.state = await state_waiting_for_init(server)

        elif server.state == ServerState.GAME_LOOP:
            server.state = await state_game_loop(server)

        elif server.state == ServerState.GAME_OVER:
            server.state = await state_game_over(server)



asyncio.run(main_loop(GameServer()))


