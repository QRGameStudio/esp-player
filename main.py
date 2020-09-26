from socket import socket, AF_INET, SOCK_DGRAM, SOCK_STREAM
from select import select
try:
    from typing import Dict, List, Set, Tuple, Optional
except ImportError:
    Dict, List, Set, Tuple, Optional = (dict, list, set, tuple, any)

from network import WLAN, AP_IF
from machine import Pin
from time import sleep
from os import listdir

PRINT_WEB = True
PRINT_DNS = False

# these hosts will not be redirected and others will be redirected to the first one
ACCEPTED_HOSTS = ['qrpr.eu', 'test.qrpr.eu', 'unsecure.qrpr.eu']


HTTP = {
    'OK': 'HTTP/1.0 200 OK\n\n'.encode('ascii'),
    'REDIRECT': ('HTTP/1.0 302 Found\nLocation: http://%s\n\n'
                 '<head>'
                 '<meta http-equiv="Refresh" content="0; URL=http://%s">'
                 '<script>window.location.replace(`http://%s`)</script>'
                 '</head>' % (ACCEPTED_HOSTS[0], ACCEPTED_HOSTS[0], ACCEPTED_HOSTS[0])).encode('ascii')
}


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


def file_exists(path):  # type: (str) -> bool
    path_parts = path.split('/')
    filename = path_parts[-1]
    dirpath = '/'.join(path_parts[:-1])
    try:
        return filename in listdir(dirpath)
    except OSError:
        return False


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
    if PRINT_DNS:
        print("DNS Server: Listening %s:53" % device_ip)

    # Web Server
    web_server_socket = socket(AF_INET, SOCK_STREAM)
    web_server_socket.setblocking(False)
    web_server_socket.bind(('', 80))
    web_server_socket.listen(64)
    if PRINT_WEB:
        print("Web Server: Listening http://%s:80/" % device_ip)

    all_readers = [web_server_socket, dns_socket]  # type: List[socket]

    write_cache = []  # type: List[Tuple[socket, bytes, Optional[str], int]]
    all_writers = []  # type: List[socket]

    while True:
        readers, writers, in_error = select(all_readers, all_writers, all_writers + all_readers)

        print("ALL: Sockets count:", len(all_readers), len(all_writers), len(in_error), len(write_cache))

        if web_server_socket in readers:
            if PRINT_WEB:
                print("Web: incoming client")
            client_soc, _ = web_server_socket.accept()
            all_readers.append(client_soc)
            readers.remove(web_server_socket)
        if dns_socket in readers:
            if PRINT_DNS:
                print("DNS: incoming request")
            filepath, client_addr = dns_socket.recvfrom(1024)
            p = DNSQuery(filepath)
            dns_socket.sendto(p.redirect(device_ip), client_addr)
            if PRINT_DNS:
                print('DNS: redirect %s -> %s' % (p.domain, device_ip))
            readers.remove(dns_socket)

        finished_readers = []
        for reader in readers:
            # HTTP requests
            request_lines = reader.recv(4096).decode('ascii').splitlines()
            filepath = ''
            host = ''
            for line in request_lines:
                lower = line.lower()
                if lower.startswith('get'):
                    try:
                        filepath = line.split(' ')[1]
                    except IndexError:
                        pass
                if lower.startswith('host'):
                    try:
                        host = line.split(' ')[1]
                    except IndexError:
                        pass
            if host.lower() in ACCEPTED_HOSTS:
                filepath = 'web' + filepath
                if PRINT_WEB:
                    print('Web: serving', filepath)

                if not file_exists(filepath):
                    filepath = 'web/index.html'
                write_cache.append((reader, HTTP['OK'], filepath, 0))
            else:
                if PRINT_WEB:
                    print('WEB: Preparing redirect of', host)
                write_cache.append((reader, HTTP['REDIRECT'], None, 0))
            if reader not in all_writers:
                all_writers.append(reader)
            finished_readers.append(reader)

        for reader in finished_readers:
            try:
                all_readers.remove(reader)
            except ValueError:
                pass

        finished_writers = []
        write_cache_finished = []  # type: List[Tuple[socket, bytes, Optional[str], int]]
        for writer in writers:
            to_write_next = []  # type: List[Tuple[socket, bytes, Optional[str], int]]
            for to_send in write_cache:
                requestor, http_bytes, filepath, offset = to_send
                if writer != requestor:
                    continue

                # start of the message, send the HTTP first
                if offset == 0:
                    writer.send(http_bytes)
                if filepath is not None:
                    with open(filepath, 'rb') as f:
                        f.seek(offset)
                        bytes_to_send = f.read(4096)
                        if len(bytes_to_send) == 4096:
                            offset += 4096
                        else:
                            offset = 0
                    writer.send(bytes_to_send)
                if offset:
                    to_write_next.append((writer, bytes(), filepath, offset))
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
    # noinspection PyBroadException
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        try:
            import traceback
            traceback.print_exc()
        except ImportError:
            traceback = None
        while True:
            blink(1)
            sleep(1)
