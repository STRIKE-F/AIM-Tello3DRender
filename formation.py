from typing import List, Tuple
from swarm_manager import TelloDrone, SwarmManager
from math import radians, sin, cos

class DroneVector(object):
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"M({self.x: .4f}, {self.y: .4f})"

class Formation(object):
    def __init__(self, manager):
        self._center_x: float = 0
        self._center_y: float = 0
        self._formation_height: float = 0
        self._manager: SwarmManager = manager

    def set_drone_starting_points(self, pad_size: float, cols: int, rows: int) -> None:
        drones = self._manager.get_connected_drones()
        if len(drones) != cols * rows:
            raise OverflowError

        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                drones[idx].x = pad_size * col
                drones[idx].y = -(pad_size * row)
                drones[idx].z = 0
                drones[idx].yaw = 0

    # get vectors for each drone on launch point to form a formation
    def _get_vectors_to_move_formation_of(self, radius: float) -> List[DroneVector]:
        drones: List[TelloDrone] = self._manager.get_connected_drones()
        angle: float = 360 / len(drones)
        vectors: List[DroneVector] = []

        # assume the default yaw is 0
        self._center_y = radius

        for (idx, drone) in enumerate(drones):
            deg: float = angle * idx
            rad: float = radians(deg)
            x: float = self._center_x + (radius * sin(rad))
            y: float = self._center_y + (radius * cos(rad))
            
            vector = DroneVector(x - drone.x, y - drone.y)
            vectors.append(vector)

        return vectors

    # move drones to formation and align them to 0 degrees
    def form_formation_of(self, radius: float) -> None:
        vectors = self._get_vectors_to_move_formation_of(radius)
        # TODO: Actually move drones by vectors, without collision!

    def move_in_formation(self, x: float, y: float) -> None:
        drones = self._manager.get_connected_drones()
        for drone in drones:
            drone.move(x, y)

    def _get_rotations_to_video_formation(self) -> List[int]:
        drones: List[TelloDrone] = self._manager.get_connected_drones()
        angle: float = 360 / len(drones)
        rotations: List[int] = []

        for (idx, drone) in enumerate(drones):
            deg: float = angle * idx
            yaw: int = int((deg + 180) % 360)
            
            rotation = 0
            yaw_delta = yaw - drone.yaw
            if yaw_delta < 0:
                rotation = 360 + yaw_delta
            if yaw_delta > 180:
                rotation = yaw_delta - 360
            rotations.append(rotation)

        return rotations

    def start_photography(self) -> None:
        drones = self._manager.get_connected_drones()
        rotations = self._get_rotations_to_video_formation()

        # rotate drones to focus on object
        for (idx, drone) in enumerate(drones):
            drone.rotate(rotations[idx])

        # TODO: circle drones around center

if __name__ == "__main__":
    manager = SwarmManager("U+Net2AE6", "1C4C024328")
    manager.find_drones_on_network(3)

    formation = Formation(manager)
    