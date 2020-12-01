from swarm_manager import TelloDrone, SwarmManager
from typing import List, Tuple

if __name__ == "__main__":
    manager = SwarmManager("U+Net2AE6", "1C4C024328")
    manager.find_drones_on_network(1)
    drones: List[TelloDrone] = manager.get_connected_drones()

    drones[0].takeoff()
    drones[0].move(30, 30)
    drones[0].land()
