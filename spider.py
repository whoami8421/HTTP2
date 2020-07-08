import ssl
import socket
from connection import H2Connection, ConnectionState
import logconfig, logging
from events import *
import gzip,zlib
import time
import re
import traceback
import threading

class H2Response(object):
    # 响应体


    def __init__(self, headers, data):
        self.DEFAULT_DECODE = 'utf-8'
        self.headers = headers
        self.__parse_headers()
        self.content = data
        self.__decompress_data()

        self.__decode = self.DEFAULT_DECODE
        self.__decode_pattern = re.compile(r'charset=(\S+)')
        self.__content_decode()
        self.status = None


    @property
    def decode(self):
        # 手动设置解码方法
        return self.__decode

    @decode.setter
    def decode(self, value):
        self.__decode = value

    def __content_decode(self):
        content_type = self.headers.get('content-type',None)
        if content_type:
            de = self.__decode_pattern.search(content_type)
            if de:
                self.__decode = de.group(1)

    def __parse_headers(self):
        self.headers = dict(self.headers)
        self.status = self.headers.get(':status', None)

    def __decompress_data(self):
        dcpr = self.headers.get('content-encoding',None)
        if dcpr == 'gzip':
            try:
                self.content = gzip.decompress(self.content)
            except:
                traceback.print_exc()
                print('the content:')
                print(self.content)
        if dcpr == 'deflate':
            self.content = zlib.decompress(self.content)

    @property
    def text(self):
        return self.content.decode(self.decode,'ignore')


class RawResponse(object):
    # 临时数据存储
    def __init__(self):
        super(RawResponse, self).__init__()
        self.headers = b''
        self.data = b''
        self.lock = threading.Lock()
        self.completed = False


class H2Socket(object):
    # 用于h2通信的socket
    DEFAULT_PORT = 443

    def __init__(self, host, port=443, timeout=1):
        super(H2Socket, self).__init__()
        context = ssl.create_default_context()
        context.set_alpn_protocols(['h2'])
        s = socket.create_connection((host, port))
        s.settimeout(timeout)
        self.sock = context.wrap_socket(s, server_hostname=host)
        self.time_wait = 0
        self.lock = threading.RLock()

    def sendall(self, data):

        response = self.sock.sendall(data)
        return response

    def recv(self, buf_size):

        response = self.sock.recv(buf_size)
        return response

    def close(self):

        response = self.sock.close()
        return response

    def refresh_wait_time(self):
        # 更新挂起时间
        self.time_wait = time.perf_counter() - self.time_wait

# h2请求的封装，类似h1中的request
class H2Spider(object):
    # h2请求的处理爬虫
    DEFAULT_HEADERS = {
        # 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'accept-encoding': 'gzip, deflate',
        ':scheme': 'https',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'
    }
    def __init__(self, max_connection=4, timeout=1):
        super(H2Spider,self).__init__()
        self.timeout = timeout
        self.__socks_conns = {}
        self.max_connection = max_connection
        # 用于解析服务器名和端口的正则表达式
        self.__host_pattern = re.compile(r'https://([^/:]+)/?')
        self.__port_pattern = re.compile(r'https://\S+?:(\d+)/?')
        self.__path_pattern = re.compile(r'https://\S+?/(\S+?)$')
        self.response_data = {}

    def request(self,method,url=None, headers=None, proxy = None ):
        method = method.upper()
        host = self._parse_host(url)
        port = self._parse_port(url)
        #print(host,port)
        sock, conn = self.__get_sock_conn(host, port)
        with sock.lock:
            conn.status = ConnectionState.OPEN
            stream_id = 0
            while not stream_id:
                stream_id = conn.get_next_available_stream()
                if not stream_id:
                    time.sleep(1)
            id = (host, port, stream_id)
            # self.response_data[id] = RawResponse()
            if method:

                h2headers = self._build_headers('GET', url, headers)
                # with sock.lock:
                conn.send_headers(stream_id, h2headers, end_stream=True)
                sock.sendall(conn.data_to_send())
                if_break = False
                while not if_break:
                    try:
                        data = sock.recv(65535)
                    except socket.timeout:
                        try:
                            if self.response_data[id].completed:
                                if_break = True
                        except KeyError:
                            pass
                        continue
                    #with sock.lock:
                    events = conn.receive_data(data)
                    received = {}
                    # print(events)
                    for e in events:
                        if isinstance(e, (HeadersReceived, DataReceived)):
                            if e.end_stream:
                                try:
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].completed = True
                                except KeyError:
                                    self.response_data[(host, port, e.stream_id)] = RawResponse()
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].completed = True
                                # self.response_data[url].compeleted = True
                                if e.stream_id == stream_id:
                                    if_break = True
                            if isinstance(e, HeadersReceived) :
                                try:
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].headers = e.headers
                                except KeyError:
                                    self.response_data[(host, port, e.stream_id)] = RawResponse()
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].headers = e.headers

                            if isinstance(e,DataReceived):
                                if e.data:
                                    try:
                                        with self.response_data[(host, port, e.stream_id)].lock:
                                            self.response_data[(host,port,e.stream_id)].data += e.data
                                    except KeyError:

                                        self.response_data[(host, port, e.stream_id)] = RawResponse()
                                        with self.response_data[(host, port, e.stream_id)].lock:
                                            self.response_data[(host, port, e.stream_id)].data += e.data

                                    # self.response_data[url].data += e.data

                                try:
                                    received[e.stream_id] += e.flow_window_length
                                except KeyError:
                                    received[e.stream_id] = e.flow_window_length
                    for sid, ack_len in received.items():
                        conn.ack_data_received(ack_len,sid)
                        sock.sendall(conn.data_to_send())
                r = self.response_data.pop(id)
                response = H2Response(r.headers, r.data)
                sock.refresh_wait_time()
        conn.status = ConnectionState.CLOSED
        return response

    def another_request(self,method,url=None, headers=None, proxy = None ):

        method = method.upper()
        host = self._parse_host(url)
        port = self._parse_port(url)
        # print(host,port)
        sock, conn = self.__get_sock_conn(host, port)

        with sock.lock:
            conn.status = ConnectionState.OPEN
            stream_id = 0
            while not stream_id:
                stream_id = conn.get_next_available_stream()
                if not stream_id:
                    time.sleep(1)
            id = (host, port, stream_id)
            # self.response_data[id] = RawResponse()
            if method:

                h2headers = self._build_headers('GET', url, headers)
                # with sock.lock:
                conn.send_headers(stream_id, h2headers, end_stream=True)
                sock.sendall(conn.data_to_send())
                if_break = False
                while not if_break:
                    try:
                        data = sock.recv(65535)
                    except socket.timeout:
                        try:
                            if self.response_data[id].completed:
                                if_break = True
                        except KeyError:
                            pass
                        continue
                    #with sock.lock:
                    events = conn.receive_data(data)
                    received = {}
                    # print(events)
                    for e in events:
                        if isinstance(e, (HeadersReceived, DataReceived)):
                            if e.end_stream:
                                try:
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].completed = True
                                except KeyError:
                                    self.response_data[(host, port, e.stream_id)] = RawResponse()
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].completed = True
                                # self.response_data[url].compeleted = True
                                if e.stream_id == stream_id:
                                    if_break = True
                            if isinstance(e, HeadersReceived) :
                                try:
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].headers = e.headers
                                except KeyError:
                                    self.response_data[(host, port, e.stream_id)] = RawResponse()
                                    with self.response_data[(host, port, e.stream_id)].lock:
                                        self.response_data[(host, port, e.stream_id)].headers = e.headers

                            if isinstance(e,DataReceived):
                                if e.data:
                                    try:
                                        with self.response_data[(host, port, e.stream_id)].lock:
                                            self.response_data[(host,port,e.stream_id)].data += e.data
                                    except KeyError:

                                        self.response_data[(host, port, e.stream_id)] = RawResponse()
                                        with self.response_data[(host, port, e.stream_id)].lock:
                                            self.response_data[(host, port, e.stream_id)].data += e.data

                                    # self.response_data[url].data += e.data

                                try:
                                    received[e.stream_id] += e.flow_window_length
                                except KeyError:
                                    received[e.stream_id] = e.flow_window_length
                    for sid, ack_len in received.items():
                        conn.ack_data_received(ack_len,sid)
                        sock.sendall(conn.data_to_send())
                r = self.response_data.pop(id)
                response = H2Response(r.headers, r.data)
                sock.refresh_wait_time()
        conn.status = ConnectionState.CLOSED
        return response

    def _build_headers(self,method, url, headers: dict):
        # 构建请求头部
        h2headers = self.DEFAULT_HEADERS
        host = self._parse_host(url)
        path = self._parse_path(url)
        if headers:
            for k, v in headers.items():
                h2headers[k] = v
        h2headers[':authority'] = host
        h2headers[':method'] = method
        h2headers[':path'] = path
        return h2headers

    def __get_sock_conn(self, host, port=None):

        if port is None:
            port = 443
        sock_conn = self.__socks_conns.get((host, port), None)
        # 获取失败，说明此时连接器内部可用连接对为空，也可能满，也可能不空不满仅无对应连接对
        if not sock_conn:
            sock = H2Socket(host, port, timeout=self.timeout)
            conn = H2Connection()
            conn.initiate_connection()
            sock_conn = (sock, conn)
            # 满的情况，删除最大挂起时间的连接对
            if len(self.__socks_conns.keys()) >= self.max_connection:
                max_sock_conn = None
                while not max_sock_conn:
                    max_sock_conn = self.__get_max_time_sock_conn()
                    if not max_sock_conn:
                        time.sleep(1)
                ip_port, (sock, conn) = max_sock_conn
                # 断开连接
                conn.close_connection()
                try:
                    sock.sendall(conn.data_to_send())
                except:
                    traceback.print_exc()
                # with sock.lock:
                #     sock.close()
                try:
                    self.__socks_conns.pop(ip_port)
                except KeyError:
                    pass
            # # 添加新连接对
            self.__socks_conns[(host, port)] = sock_conn
        # 验证可用性
        try:
            sock, conn = sock_conn
            conn.send_ping()
            sock.sendall(conn.data_to_send())
        except socket.error:
            sock_conn = self.__get_sock_conn(host,port)
        return sock_conn

    def __get_max_time_sock_conn(self):
        # 取出当前挂起最久的[(ip, port),[socket,conn,lock]]
        sock_list = sorted(self.__socks_conns.items(),
                           key=lambda x:x[1][0].time_wait,
                           reverse=True)
        sock_conn = None
        for ip_port, c_s in sock_list:
            if c_s[1].status == ConnectionState.CLOSED:
                return (ip_port, c_s)
        return sock_conn

    def get(self,url,headers=None, proxy = None):
        # get请求
        return self.request(method='GET',url=url, headers=headers,proxy=proxy)

    def post(self, url, headers=None):
        return self.request('POST', url, headers)

    def _parse_host(self, url):

        result = self.__host_pattern.match(url)
        host = result.group(1)
        return host

    def _parse_port(self, url):

        result = self.__port_pattern.match(url)
        try:
            port = result.group(1)
        except:
            port = 443
        return int(port)

    def _parse_path(self, url):
        result = self.__path_pattern.match(url)
        path = ''
        if result:
            path = result.group(1)
        path = '/'+path
        return path


if __name__ == '__main__':
    pass

