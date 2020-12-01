import tellopy

import socket
import time
from threading import Thread, Lock
from typing import List, Tuple
import netifaces, netaddr

# Tello's default address when in station mode is 192.168.10.1
TELLO_DEFAULT_ADDR = ("192.168.10.1", 8889)
# Tello uses IPv4, UDP for connection
TELLO_SOCK_PROTOCOL = socket.AF_INET, socket.SOCK_DGRAM

class TelloDrone(object):
    def __init__(self, sock: socket.socket, serial: str, ip: str) -> None:
        self._sock: socket.socket = sock
        self._serial: str = serial
        self.ip: str = ip
        self.name: str = None
        self._lock: Lock = Lock()

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

    def takeoff(self) -> None:
        self._send_command("takeoff", 8.0)

    def land(self) -> None:
        self._send_command("land", 8.0)

    # Rotate the drone by given angle
    # 0 <= abs(angle) <= 180 
    # positive angle: clockwise
    # negative angle: counterclockwise
    def rotate(self, angle: int) -> None:
        if angle > 0:
            self._send_command(f"cw {angle}")
        elif angle < 0:
            self._send_command(f"ccw {angle}")
        else:
            # no need to move when angle == 0
            pass
    
    # Move the drone by given x, y vector
    def move(self, x: float, y: float) -> None:
        # Tello command only accepts int
        param_x = int(x)
        param_y = int(y)
        self._send_command(f"go {param_x} {param_y} {0} 20")

    def _threaded_send(self, comm: str) -> None:
        try:
            self._sock.send(comm.encode('utf-8'))
            response = self._sock.recv(1024)
            if response.decode('utf-8') != "ok":
                raise ConnectionRefusedError
        # lock MUST BE released
        finally:
            self._lock.release()

    def _send_command(self, comm: str, timeout: float = 2.0) -> None:
        self._lock.acquire()
        self._sock.settimeout(timeout)
        # for response time, use per-drone multithreading
        thread = Thread(self._threaded_send, args=(comm,))
        thread.daemon = True
        thread.start()

    # Get abstract, relational position from control point
    def pos(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

class SwarmManager(object):
    def __init__(self, wifi_ssid: str, wifi_pwd: str) -> None:
        self._drones: List[TelloDrone] = []
        self._ssid: str = wifi_ssid
        self._pwd: str  = wifi_pwd

    # Given that this PC is connected to Tello in Station mode,
    # switch Tello to AP mode and add the drone instance once the mode's switched
    def add_drone_to_network(self) -> None:
        self._change_drone_mode()
        # time to shut down, reboot, connect to wifi, ...
        time.sleep(15)
        self.find_drones_on_network(1)

    # Find drones on AP mode and create drone instance from it
    def find_drones_on_network(self, num: int) -> None:
        tello_socks: List[Tuple[str, socket.socket]] = self._connect_to_drones_online(num)
        for (ip, sock) in tello_socks:
            try:
                sock.settimeout(3.0)
                # get serial number
                comm = "sn?"
                sock.send(comm.encode('utf-8'))
                serial = sock.recv(1024).decode('utf-8')
                self._drones.append(TelloDrone(sock, serial, ip))
            except OSError:
                print(f"Drone at {ip} lost connection")
                sock.close()
                continue
                
        print(self._drones)

    def get_connected_drones(self) -> List[TelloDrone]:
        return self._drones

    # Get (ip, socket)s to Tellos in network
    def _connect_to_drones_online(self, num: int) -> List[Tuple[str, socket.socket]]:
        possible_ips = self._get_possible_ips()
        already_added_ips: List[str] = [drone.ip for drone in self._drones]
        tello_socks: List[socket.socket] = []

        for ip in possible_ips:
            # do not try to connect if that ip is already added
            if ip in already_added_ips:
                continue
            # print(f"trying for {ip}")
            sock = socket.socket(*TELLO_SOCK_PROTOCOL)
            # lots of ips to scan...
            sock.settimeout(0.2)
            try:
                # establish connection with drone
                sock.connect((ip, 8889))
                comm = "command"
                sock.send(comm.encode('utf-8'))
                response = sock.recv(1024)
                if response.decode('utf-8') == "ok":
                    tello_socks.append((ip, sock))
                    if len(tello_socks) == num:
                        break
                else:
                    raise ConnectionRefusedError
            except OSError:
                sock.close()
                continue
        
        return tello_socks

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
            # establish connection to Tello
            sock.connect(TELLO_DEFAULT_ADDR)

            # check connection btw/ Tello and PC
            comm = "command"
            sock.send(comm.encode('utf-8'))
            response = sock.recv(1024)
            if response.decode('utf-8') != "ok":
                raise ConnectionRefusedError
            
            # get serial number from Tello
            comm = "sn?"
            sock.send(comm.encode('utf-8'))
            response = sock.recv(1024)
            serial = response.decode('utf-8')

            # switch the Tello mode
            comm = f"ap {self._ssid} {self._pwd}"
            sock.send(comm.encode('utf-8'))
            response = sock.recv(1024)
            print(f"{response.decode('utf-8')} from {serial}")

        # timeout: failed to connect to Tello for 5 seconds
        except OSError:
            raise ConnectionRefusedError

        finally:
            sock.close()

if __name__ == "__main__":
    ctrl = SwarmManager("U+Net2AE6", "1C4C024328")
    ctrl.find_drones_on_network(3)
    drones: List[TelloDrone] = ctrl.get_connected_drones()
    drones[0].takeoff()
    time.sleep(1)
    drones[1].takeoff()
    time.sleep(1)
    drones[2].takeoff()
    time.sleep(1)
    drones[0].land()
    drones[1].land()
    drones[2].land()
