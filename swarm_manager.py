import tellopy

import socket
import time
from typing import List, Tuple
import netifaces, netaddr

# Tello's default address when in station mode is 192.168.10.1
TELLO_DEFAULT_ADDR = ("192.168.10.1", 8889)
# Tello uses IPv4, UDP for connection
TELLO_SOCK_PROTOCOL = socket.AF_INET, socket.SOCK_DGRAM

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
                sock.settimeout(2)
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
            sock.settimeout(0.05)
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

class TelloDrone(object):
    def __init__(self, sock: socket.socket, serial: str, ip: str) -> None:
        self._sock: socket.socket = sock
        self._serial: str = serial
        self.ip: str = ip
        self.name: str = None

        self.x: float = 0.0
        self.y: float = 0.0
        self.z: float = 0.0

    def __repr__(self) -> str:
        if self.name:
            return f"Tello {self.name}@{self.ip}"
        else:
            # only use last 4 digits of serial
            return f"Tello {self._serial[-4:]}@{self.ip}"

    # Get abstract, relational position from control point
    def pos(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

if __name__ == "__main__":
    ctrl = SwarmManager("U+Net2AE6", "1C4C024328")
    # ctrl.add_new_drone()
    ctrl.find_drones_on_network(3)
