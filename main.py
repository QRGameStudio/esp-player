from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM
from select import select
try:
    from typing import Dict, List, Set, Tuple
except ImportError:
    Dict, List, Set, Tuple = (dict, list, set, tuple)

from network import WLAN, AP_IF
from machine import Pin
from time import sleep

CONTENT = """\
HTTP/1.0 200 OK

<!doctype html>
<html>
    <head>
        <title>MicroPython Captive LED Portal</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta charset="utf8">
    </head>
    <body>
        <h1>Working!</h1>
    </body>
</html>
""".encode('ascii')


class DNSQuery:
    def __init__(self, data):  # type: (bytes) -> None
        self.data = data
        self.domain = ''

        m = data[2]  # ord(data[2])
        query_type = (m >> 3) & 15  # Opcode bits
        if query_type == 0:  # Standard query
            ini = 12
            lon = data[ini]  # ord(data[ini])
            while lon != 0:
                self.domain += data[ini + 1:ini + lon + 1].decode("utf-8") + '.'
                ini += lon + 1
                lon = data[ini]  # ord(data[ini])

    def redirect(self, ip):  # type: (str) -> bytes
        packet = b''
        if self.domain:
            packet += self.data[:2] + b"\x81\x80"
            packet += self.data[4:6] + self.data[4:6] + b'\x00\x00\x00\x00'  # Questions and Answers Counts
            packet += self.data[12:]  # Original Domain Name Question
            packet += b'\xc0\x0c'  # Pointer to domain name
            # Response type, ttl and resource data length -> 4 bytes
            packet += b'\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'
            packet += bytes(map(int, ip.split('.')))  # 4 bytes of IP
        return packet


def blink(seconds):  # type: (float) -> None
    led = Pin(2, Pin.OUT)
    led.on()
    sleep(seconds)
    led.off()


def create_wifi():  # type: () -> str
    ssid = "QRGames Player"

    ap = WLAN(AP_IF)
    ap.active(True)
    ap.config(essid=ssid)
    return ap.ifconfig()[0]


def main():
    # safeguard if everything went bananas
    print("Initializing")
    blink(2)

    device_ip = create_wifi()
    print("Running with IP", device_ip)

    # DNS Server
    dns_socket = socket(AF_INET, SOCK_DGRAM)
    dns_socket.setblocking(False)
    dns_socket.bind(('', 53))
    print("DNS Server: Listening %s:53" % device_ip)

    # Web Server
    web_server_socket = socket(AF_INET, SOCK_STREAM)
    web_server_socket.setblocking(False)
    web_server_socket.bind(('', 80))
    web_server_socket.listen(16)
    print("Web Server: Listening http://%s:80/" % device_ip)

    all_readers = [web_server_socket, dns_socket]  # type: List[socket]

    write_cache = []  # type: List[Tuple[socket, bytes]]
    all_writers = []  # type: List[socket]

    while True:
        readers, writers, in_error = select(all_readers, all_writers, all_writers + all_readers)
        print('sockets: ', len(readers), len(writers), len(in_error), len(all_readers), len(all_writers), len(write_cache))

        if web_server_socket in readers:
            print("Web: incoming client")
            client_soc, _ = web_server_socket.accept()
            all_readers.append(client_soc)
            readers.remove(web_server_socket)
        if dns_socket in readers:
            print("DNS: incoming request")
            data, client_addr = dns_socket.recvfrom(1024)
            p = DNSQuery(data)
            dns_socket.sendto(p.redirect(device_ip), client_addr)
            print('DNS: redirect %s -> %s' % (p.domain, device_ip))
            readers.remove(dns_socket)

        finished_readers = []
        for reader in readers:
            # HTTP requests
            request_lines = reader.recv(4096).decode('ascii').splitlines()
            for line in request_lines:
                if line.startswith('GET'):
                    try:
                        filepath = line.split(' ')[1]
                        print('Web: serving', filepath)
                        if reader not in all_writers:
                            all_writers.append(reader)
                            write_cache.append((reader, CONTENT))
                    except IndexError:
                        pass
                    break
            finished_readers.append(reader)

        for reader in finished_readers:
            try:
                all_readers.remove(reader)
            except ValueError:
                pass

        finished_writers = []
        write_cache_finished = []  # type: List[Tuple[socket, bytes]]
        for writer in all_writers:
            to_write_next = []  # type: List[Tuple[socket, bytes]]
            for to_send in write_cache:
                writer2, data = to_send
                if writer != writer2:
                    continue
                bytes_to_send = data[:1024]
                bytes_left = data[1024:]
                writer.send(bytes_to_send)
                if bytes_left:
                    to_write_next.append((writer, bytes_left))
                write_cache_finished.append(to_send)
            if to_write_next:
                write_cache.extend(to_write_next)
            else:
                finished_writers.append(writer)

        for finished in write_cache_finished:
            write_cache.remove(finished)

        for writer in finished_writers:
            try:
                writer.close()
                all_writers.remove(writer)
            except ValueError:
                pass


if __name__ == '__main__':
    main()
