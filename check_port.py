import socket

def check_port(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

if __name__ == "__main__":
    if check_port(9222):
        print("Port 9222 is OPEN")
    else:
        print("Port 9222 is CLOSED")
