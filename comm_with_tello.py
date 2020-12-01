from swarm_manager import TelloDrone, SwarmManager
from typing import List, Tuple

# Set according to individual's wifi environment
ROUTER_SSID_PASSWORD = "U+Net2AE6", "1C4C024328"

if __name__ == "__main__":
    manager = SwarmManager(*ROUTER_SSID_PASSWORD)
    manager.find_drones_on_network(1)
    drones: List[TelloDrone] = manager.get_connected_drones()

    drones[0].takeoff()
    drones[0].move(30, 30)
    drones[0].land()
