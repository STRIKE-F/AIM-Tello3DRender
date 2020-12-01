import socket
import time
from threading import Thread, Lock
from typing import List, Tuple
import netifaces, netaddr
from tello import APTello
from math import atan2, degrees, sqrt

# Tello's default address when in station mode is 192.168.10.1
TELLO_DEFAULT_ADDR = ("192.168.10.1", 8889)
# Tello uses IPv4, UDP for connection
TELLO_SOCK_PROTOCOL = socket.AF_INET, socket.SOCK_DGRAM

class TelloDrone(APTello):
    def __init__(self, comm_sock: socket.socket, vid_sock: socket.socket, serial: str, ip: str) -> None:
        APTello.__init__(self, comm_sock, vid_sock, ip)
        self._serial: str = serial
        self.name: str = None

        self.x: float = 0
        self.y: float = 0
        self.z: float = 0
        self.yaw: int = 0

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
            self.clockwise(angle)
        elif angle < 0:
            self.counter_clockwise(-angle)
        else:
            # no need to move when angle == 0
            pass
    
    # Move the drone by given x, y vector
    # and align to deg = 0
    def move(self, x: float, y: float) -> None:
        # convert x, y vec to angular vec
        # and rotate to that degrees
        rad = atan2(-x, y)
        angle = int(-degrees(rad))
        self.rotate(angle)

        dist = int(sqrt(x**2 + y**2))
        self.forward(dist)

        # align back to 0 degrees
        self.rotate(-angle)

        # update position info
        self.x += x
        self.y += y

    # Get abstract, relational position from control point
    def pos(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

class SwarmManager(object):
    def __init__(self, wifi_ssid: str, wifi_pwd: str) -> None:
        self._drones: List[TelloDrone] = []
        self._ssid: str = wifi_ssid
        self._pwd: str  = wifi_pwd
        self._control_sock = socket.socket(*TELLO_SOCK_PROTOCOL)
        self._video_sock = socket.socket(*TELLO_SOCK_PROTOCOL)
        self._control_sock.bind(('', 9000))
        self._video_sock.bind(('', 6038))

    # Given that this PC is connected to Tello in Station mode,
    # switch Tello to AP mode and add the drone instance once the mode's switched
    def add_drone_to_network(self) -> None:
        self._change_drone_mode()
        # time to shut down, reboot, connect to wifi, ...
        time.sleep(15)
        self.find_drones_on_network(1)

    # Find drones on AP mode and create drone instance from it
    def find_drones_on_network(self, num: int) -> None:
        tello_ips: List[str] = self._find_drones_online(num)

        sock = self._control_sock
        sock.settimeout(2.0)

        for ip in tello_ips:
            try:
                # get serial number
                comm = "sn?"
                sock.sendto(comm.encode('utf-8'), (ip, 8889))
                response, _ = sock.recvfrom(1024)
                serial = response.decode('utf-8')
                self._drones.append(TelloDrone(sock, self._video_sock, serial, ip))
            except OSError:
                print(f"Drone at {ip} lost connection")
                continue
                
        print(self._drones)

    def get_connected_drones(self) -> List[TelloDrone]:
        return self._drones

    # Get ips of Tellos in network
    def _find_drones_online(self, num: int) -> List[str]:
        possible_ips = self._get_possible_ips()
        already_added_ips: List[str] = [drone.ip for drone in self._drones]
        tello_ips: List[str] = []
        
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
                    tello_ips.append(ip)
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
