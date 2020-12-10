import socket
import time
from threading import Thread, Lock
from typing import List, Optional, Tuple
import netifaces, netaddr

# Tello's default address when in station mode is 192.168.10.1
TELLO_DEFAULT_ADDR = ("192.168.10.1", 8889)
# Tello uses IPv4, UDP for connection
TELLO_SOCK_PROTOCOL = socket.AF_INET, socket.SOCK_DGRAM

class TelloDrone(object):
    # manager: TelloDrone
    def __init__(self, sock: socket.socket, serial: str, ip: str, manager) -> None:
        self._sock = sock
        self._serial: str = serial
        self.ip: str = ip
        self.name: str = None

        self.x: float = 0
        self.y: float = 0
        self.z: float = 0
        self.yaw: int = 0

        self._command_queue: List[str] = []
        self._queue_lock = Lock()
        self._thread = Thread(target=self._command_thread)
        self._thread.start()

        self._manager = manager

    def __del__(self):
        self._thread.join()

    def __repr__(self) -> str:
        if self.name:
            return f"Tello {self.name}@{self.ip}"
        else:
            # only use last 4 digits of serial
            return f"Tello {self._serial[-4:]}@{self.ip}"

    # Rotate the drone by given angle
    # 0 <= abs(angle) <= 180 
    # positive angle: clockwise
    # negative angle: counterclockwise
    def rotate(self, angle: int) -> None:
        if angle > 0:
            self._clockwise(angle)
        elif angle < 0:
            self._counter_clockwise(-angle)
        else:
            # no need to move when angle == 0
            pass
        
    def move(self, x: int, y: int, z: int = 0, speed: int = 30):
        self._enqueue_command(f"go {y} {-x} {z} {speed}")
        self.x += x
        self.y += y
        self.z += z

    # Get abstract, relational position from control point
    def pos(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    # Terminate connection between Drone and PC
    def shutdown(self):
        self._enqueue_command("shutdown")

    def takeoff(self):
        self._enqueue_command("takeoff")

    def land(self):
        self._enqueue_command("land")

    def _forward(self, dist: int):
        self._enqueue_command(f"forward {dist}")

    def _back(self, dist: int):
        self._enqueue_command(f"back {dist}")

    def _speed(self, speed: int):
        self._enqueue_command(f"speed {speed}")

    def _clockwise(self, angle: int):
        self._enqueue_command(f"cw {angle}")

    def _counter_clockwise(self, angle: int):
        self._enqueue_command(f"ccw {angle}")

    def _up(self, dist: int):
        self._enqueue_command(f"up {dist}")

    def _down(self, dist: int):
        self._enqueue_command(f"down {dist}")

    def _send_command(self, cmd: str):
        self._sock.sendto(cmd.encode('utf-8'), (self.ip, 8889))
        response, addr = self._sock.recvfrom(1024)
        print(f"response from {addr}: {response.decode('utf-8')}")

    def _enqueue_command(self, cmd: str):
        with self._queue_lock:
            self._command_queue.append(cmd)

    def _is_complete(self) -> bool:
        with self._queue_lock:
            if self._command_queue:
                return False
            else:
                return True

    def _command_thread(self):
        while self._sock:
            self._queue_lock.acquire()
            if self._command_queue:
                command = self._command_queue.pop(0)
                if command == "shutdown":
                    self._sock = None
                else:
                    self._send_command(command)
            self._queue_lock.release()
            time.sleep(0.1)

class SwarmManager(object):
    def __init__(self, wifi_ssid: str, wifi_pwd: str) -> None:
        self._drones: List[TelloDrone] = []
        self._ssid: str = wifi_ssid
        self._pwd: str  = wifi_pwd
        self._control_sock = socket.socket(*TELLO_SOCK_PROTOCOL)
        self._video_sock = socket.socket(*TELLO_SOCK_PROTOCOL)
        self._control_sock.bind(('', 9000))
        self._video_sock.bind(('', 6038))
        self._signals = {}
        self._signals_lock = Lock()

    # Given that this PC is connected to Tello in Station mode,
    # switch Tello to AP mode and add the drone instance once the mode's switched
    def add_drone_to_network(self) -> None:
        self._change_drone_mode()
        # time to shut down, reboot, connect to wifi, ...
        time.sleep(15)
        self.find_drones_on_network(1)

    # Find drones on AP mode and create drone instance from it
    def find_drones_on_network(self, num: int) -> None:
        tellos: List[Tuple[str, str]] = self._find_drones_online(num)
        self._control_sock.settimeout(None)

        for (ip, serial) in tellos:
            tello = TelloDrone(self._control_sock, serial, ip, self)
            self._drones.append(tello)
                
        print(self._drones)       


    def get_connected_drones(self) -> List[TelloDrone]:
        return self._drones

    # Get ips of Tellos in network
    def _find_drones_online(self, num: int) -> List[Tuple[str, str]]:
        possible_ips = self._get_possible_ips()
        already_added_ips: List[str] = [drone.ip for drone in self._drones]
        tello_ips: List[Tuple[str, str]] = []
        
        sock = self._control_sock

        for ip in possible_ips:
            # do not try to connect if that ip is already added
            if ip in already_added_ips:
                continue
            print(f"trying for {ip}")
            # lots of ips to scan...
            sock.settimeout(0.1)
            try:
                # establish connection with drone
                comm = "command"
                sock.sendto(comm.encode('utf-8'), (ip, 8889))
                response, _ = sock.recvfrom(1024)
                if response.decode('utf-8') == "ok":
                    comm = "sn?"
                    sock.sendto(comm.encode('utf-8'), (ip, 8889))
                    response, _ = sock.recvfrom(1024)
                    serial = response.decode('utf-8')
                    tello_ips.append((ip, serial))
                    if len(tello_ips) == num:
                        break
                else:
                    raise ConnectionRefusedError
            except OSError:
                continue
        
        return tello_ips

    # Get entire IPs on a subnet
    def _get_possible_ips(self) -> List[str]:
        ips: List[str] = []

        for iface in netifaces.interfaces():
            addr = netifaces.ifaddresses(iface)

            if socket.AF_INET not in addr:
                continue

            # Get ipv4 stuff
            ipinfo = addr[socket.AF_INET][0]
            address, netmask = ipinfo['addr'], ipinfo['netmask']

            # limit range of search. This will work for router subnets
            if netmask != '255.255.255.0':
                continue

            # Create ip object and get
            subnet = netaddr.IPNetwork(f'{address}/{netmask}')
            network = netaddr.IPNetwork(f"{subnet.network}/{netmask}")
            for ip in network:
                if str(ip).split('.')[3] not in ['0', '255'] and str(ip) != address:
                    ips.append(str(ip))
        
        return ips

    # Switch the Tello in Station Mode to AP mode,
    # and connect the Tello to designated wifi AP
    def _change_drone_mode(self) -> None:
        # Tello uses IPv4 and UDP
        sock = socket.socket(*TELLO_SOCK_PROTOCOL)
        sock.settimeout(5)
        
        try:
            # check connection btw/ Tello and PC
            comm = "command"
            sock.sendto(comm.encode('utf-8'), TELLO_DEFAULT_ADDR)
            response, _ = sock.recvfrom(1024)
            if response.decode('utf-8') != "ok":
                raise ConnectionRefusedError
            
            # get serial number from Tello
            comm = "sn?"
            sock.sendto(comm.encode('utf-8'), TELLO_DEFAULT_ADDR)
            response, _ = sock.recvfrom(1024)
            serial = response.decode('utf-8')

            # switch the Tello mode
            comm = f"ap {self._ssid} {self._pwd}"
            sock.sendto(comm.encode('utf-8'), TELLO_DEFAULT_ADDR)
            response, _ = sock.recvfrom(1024)
            print(f"{response.decode('utf-8')} from {serial}")

        # timeout: failed to connect to Tello for 5 seconds
        except OSError:
            raise ConnectionRefusedError

        finally:
            sock.close()

    def sync(self):
        wait = True
        while wait:
            wait = False
            for drone in self._drones:
                if not drone._is_complete():
                    wait = True
                    break
            time.sleep(0.1)

