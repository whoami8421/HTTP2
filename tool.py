import socket
import enum
def GetHostInfo(domain):
    #IP = (socket.gethostbyname(domain))

    ipinfo = (socket.getaddrinfo(domain,None))
    print(ipinfo)
    info = {}
    ipv6,ipv4 = [],[]
    for item in ipinfo:
        if isinstance(item[0],enum.Enum):
            if item[0].value==23:
                ipv6.append(item[4][0])
            if item[0].value==2:
                ipv4.append(item[4][0])
    info['ipv4'] = ipv4
    info['ipv6'] = ipv6
    return info

# getIP('www.ustc.edu.cn')

def main():
    hostname = 'www.ustc.edu.cn'
    ipv6 = GetHostInfo(hostname)['ipv6'][0]
    sock = socket.socket(socket.AF_INET6,socket.SOCK_STREAM)
    #sock.bind(('127.0.0.1',8888))
    sock.connect((ipv6,443))
    sock.sendall(b'hello')
    re = sock.recv(1024)
    print(re)


if __name__=='__main__':
    import socket
    sock = socket.socket()
    sock.close()
