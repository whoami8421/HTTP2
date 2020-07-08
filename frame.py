#import os,sys
#sys.path.append(os.path.dirname(os.path.abspath(__name__)))

try:
    from .flags import *
except:
    from flags import *
import struct
import logging, logconfig


FRAME_MAX_LEN = (2 ** 14)

# The maximum allowed length of a frame.-
FRAME_MAX_ALLOWED_LEN = (2 ** 24) - 1


# Structs for packing and unpacking
# name | C | python | size(bytes)
# B	| unsigned char | integer | 1
# H	|unsigned short	|integer  |2
# L	|unsigned long	|long	|4
# 网络传输默认大端模式存储数据
_STRUCT_HBBBL = struct.Struct(">HBBBL")
_STRUCT_LL = struct.Struct(">LL")
_STRUCT_HL = struct.Struct(">HL")
_STRUCT_LB = struct.Struct(">LB")
_STRUCT_L = struct.Struct(">L")
_STRUCT_H = struct.Struct(">H")
_STRUCT_B = struct.Struct(">B")


class Frame(object):


    type = None
    defined_flags = []
    # flags为包含有标志字符串的元组
    def __init__(self,stream_id,flags=()):
        self.stream_id = stream_id
        self.body_len = 0
        self.flags = Flags(self.defined_flags)
        # 添加标志位初始化
        for flag in flags:
            self.flags.add(flag)

    def __repr__(self):
        return type(self).__name__

    # 将相关数据按照帧首部格式进行填充，添加payload数据负载后返回已封装完毕的帧
    def serialize(self):
        body = self.serialize_body()
        self.body_len = len(body)
        # 逐一检查flag标志位
        flags = 0
        for flag, flag_bit in self.defined_flags:
            if flag in self.flags:
                flags |= flag_bit

        # 封装头部
        header = _STRUCT_HBBBL.pack(
            (self.body_len >> 8) & 0xFFFF,  # 高位24比特
            self.body_len & 0xFF, # 低8位比特
            self.type,
            flags,
            self.stream_id & 0x7FFFFFFF  # Stream ID  31比特.
        )

        return header + body


    # 返回payload序列化后的数据
    # 此函数提供接口，需在具体帧类型内部进行各自的方法实现覆盖
    def serialize_body(self):
        raise NotImplementedError

    # 传入前帧首部（数据前9字节）进行解析，返回指定类型的Frame(flags已识别）和长度
    @staticmethod
    def parse_frame_header(header):
        fields = _STRUCT_HBBBL.unpack(header)
        #payload数据长度
        length = (fields[0] << 8) + fields[1]
        #帧类型
        type = fields[2]
        #帧具体服务标志
        flags = fields[3]
        # 保留比特位，暂未使用
        R = fields[4] & 0x80000000
        # 流id
        stream_id = fields[4] & 0x7FFFFFFF
        try:
            frame = FRAMES[type](stream_id)
        except KeyError:
            print(header)
            raise('unknow type frame.')
        frame.body_len = length
        frame._set_flags(flags)
        return (frame,length)

    # 对payload解析然后填充，需在各自类型帧内部实现
    def parse_body(self, data):

        raise NotImplementedError

    # 根据flags的原始数据字段，格式化成Flags
    def _set_flags(self,flags_bytes):
        for flag, bit in self.defined_flags:
            if flags_bytes & bit:
                self.flags.add(flag)
        return self.flags

    # 添加flag
    def add_flag(self,flag_string):
        self.flags.add(flag_string)

    # 移除flag
    def discard_flag(self,flag_string):
        self.flags.discard(flag_string)

    def show_itself(self):
        N = 'NULL'
        info = f'\n=======================\n' \
               f'Frame Body Length: {self.body_len}\n' \
               f'Frame Type: {self.type if self.type != None else N}\n' \
               f'Flags: {self.flags if self.flags else N}\n' \
               f'Stream ID: {self.stream_id}' \
               f'\n=======================\n'
        print(info)

class DataFrame(Frame):

    type = 0x00
    defined_flags = [
        Flag('END_STREAM', 0x01),
        Flag('PADDED', 0x08),
    ]

    def __init__(self,
                 stream_id,
                 data=b'',
                 flags=(),
                 padded_length=0):
        super(DataFrame,self).__init__(stream_id,flags=flags)
        self.data = data
        self.padded_length = padded_length
        self.body_len = len(data)+ padded_length + 1

    def serialize_body(self):
        data = self.data
        padded_length_data = b''
        padded_data = b''
        if 'PADDED' in self.flags:
            padded_length_data = _STRUCT_B.pack(self.padded_length)
            padded_data = b'\0' * self.padded_length
        return b''.join([padded_length_data,
                         data,
                         padded_data])

    def parse_body(self, data):
        self.body_len = len(data)
        if 'PADDED' in self.flags:
            self.padded_length = _STRUCT_B.unpack(data[0])[0]
            if (len(data) - 1) < self.padded_length:
                raise ValueError('Invalid headers data.')
        else:
            self.padded_length = 0

        self.data = data[1:-self.padded_length] if self.padded_length else data


class HeadersFrame(Frame):


    type = 0x01
    defined_flags = [
        Flag('END_STREAM', 0x01),
        Flag('END_HEADERS', 0x04),
        Flag('PADDED', 0x08),
        Flag('PRIORITY', 0x20)
    ]
    # 填充字段长度（8位，只有在PADDED标记设置时这个字段才出现）
    # 是否为独占流（1位，默认0，这个字段只有在PRIORITY标记设置时才会出现）
    # 依赖于哪一个流id（31位，默认依赖于0x00，这个字段只有在PRIORITY标记设置时才会出现）
    # 优先权重（8位，所有流的默认权重为16，这个字段只有在PRIORITY标记设置时才会出现）
    def __init__(self,
                 stream_id,
                 header_data=b'',
                 flags:tuple=(),
                 padded_length=0,
                 exclusive=False,
                 stream_dependency=0x0,
                 weight = 16
                 ):
        super(HeadersFrame, self).__init__(stream_id, flags=flags)
        self.data = header_data
        if padded_length < 0 or padded_length > 255:
            raise ValueError('padded_length should be 0 to 255')
        self.padded_length = padded_length
        self.exclusive = exclusive
        self.stream_dependency = stream_dependency
        self.weight = weight


    def serialize_body(self):
        padded_length_data = b''
        padded_data = b''
        dependency_data = b''
        weight_data = b''
        if 'PADDED' in self.flags:
            padded_length_data = _STRUCT_B.pack(self.padded_length)
            padded_data = b'\0' * self.padded_length
        if 'PRIORITY' in self.flags:
            dependency_data = _STRUCT_L.pack((self.stream_dependency & 0x7FFFFFFF) |
                                             (0xFFFFFFFF if self.exclusive else 1))
            weight_data = _STRUCT_B.pack(self.weight)

        payload = b''.join([
            padded_length_data,
            dependency_data,
            weight_data,
            self.data,
            padded_data
                        ])

        return payload

    def parse_body(self, data):
        # 去除填充字段，解析出原始头数据
        # 注意body_len指的是整个payload（包含了填充以及优先信息）的长度
        # data指的是头部数据块的长度（仅头部主体数据）
        self.body_len = len(data)
        if 'PADDED' in self.flags:
            self.padded_length = _STRUCT_B.unpack(data[0])[0]
        else:
            self.padded_length = 0
        if (len(data) - 1) < self.padded_length:
            raise ValueError('Invalid headers data.')
        self.data = data[1:-self.padded_length] if self.padded_length else data
        if 'PRIORITY' in self.flags:
            fields = _STRUCT_LB.unpack(self.data[0:5])
            self.exclusive = fields[0] >> 31
            self.stream_dependency = fields[0] & 0x7FFFFFFF
            self.weight = fields[1]
            self.data = self.data[5:]


class PriorityFrame(Frame):
    pass

class RstStreamFrame(Frame):
    # 标识流的结束，可选参数错误码

    type = 0x03

    def __init__(self, stream_id, error_code=0x00):
        super(RstStreamFrame, self).__init__(stream_id)
        self.error_code = error_code

    def serialize_body(self):
        payload = b''
        if self.error_code != None:
            payload = _STRUCT_L.pack(self.error_code)
        return payload

    def parse_body(self, data):
        self.error_code = _STRUCT_L.unpack(data[0:4])[0]

class SettingsFrame(Frame):
    # 帧类型为0x04，表示SETTINGS帧
    type = 0x04
    #该帧支持的标志位
    defined_flags = [
        Flag('ACK',0x01)
    ]
    #: The byte that signals the SETTINGS_HEADER_TABLE_SIZE setting.
    HEADER_TABLE_SIZE = 0x01
    #: The byte that signals the SETTINGS_ENABLE_PUSH setting.
    ENABLE_PUSH = 0x02
    #: The byte that signals the SETTINGS_MAX_CONCURRENT_STREAMS setting.
    MAX_CONCURRENT_STREAMS = 0x03
    #: The byte that signals the SETTINGS_INITIAL_WINDOW_SIZE setting.
    INITIAL_WINDOW_SIZE = 0x04
    #: The byte that signals the SETTINGS_MAX_FRAME_SIZE setting.
    MAX_FRAME_SIZE = 0x05
    #: The byte that signals the SETTINGS_MAX_HEADER_LIST_SIZE setting.
    MAX_HEADER_LIST_SIZE = 0x06
    #: The byte that signals SETTINGS_ENABLE_CONNECT_PROTOCOL setting.
    ENABLE_CONNECT_PROTOCOL = 0x08

    # flag暂定输入为字符串类型
    def __init__(self,stream_id,flags:tuple = (),settings:dict = None):
        super(SettingsFrame,self).__init__(stream_id,flags)
        if 'ACK' in flags and settings:
            raise ValueError('settings must be empty when ACK is set.')
        # payload 中具体setting的配置，暂定为字典
        self.settings = settings if settings else {}
        #是否为settings的ack帧

    def serialize_body(self):
        body = b''
        for identifier,value in self.settings.items():
            setting = _STRUCT_HL.pack(identifier & 0xFFFF,value & 0xFFFFFFFF)
            body += setting
        return body

    def parse_body(self, data):
        for i in range(0, len(data), 6):
            try:
                identifier, value = _STRUCT_HL.unpack(data[i:i+6])
            except struct.error:
                raise ValueError('Invalid SETTINGS body.')
            self.settings[identifier] = value

class PushPromiseFrame(Frame):
    pass

class PingFrame(Frame):
    # 用于测试连接性和可用性
    type = 0x06
    defined_flags = [Flag('ACK', 0x01)]

    def __init__(self,stream_id=0, opaque_data=b'', flags=()):
        super(PingFrame, self).__init__(stream_id, flags)
        self.opaque_data = opaque_data

    def serialize_body(self):

        if len(self.opaque_data) > 8:
            raise ValueError('opaque data length should not be more than 8 bytes.')
        data = b'\0'* (8 - len(self.opaque_data))
        return data

    def parse_body(self, data):

        self.data = data
        self.body_len = len(self.data)

class GoAwayFrame(Frame):


    type = 0x07

    def __init__(self,stream_id=0,
                 last_stream_id=2**31-1,
                 error_code=0,
                 error_message=b''):
        super(GoAwayFrame, self).__init__(stream_id)
        self.last_stream_id = last_stream_id
        self.error_code = error_code
        self.error_message = error_message

    def serialize_body(self):
        return b''.join([_STRUCT_LL.pack(self.last_stream_id & 0x7FFFFFFF,
                                         self.error_code),
                         self.error_message])

    def parse_body(self, data):
        fields = _STRUCT_LL.unpack(data[0:8])
        self.last_stream_id = fields[0] & 0x7FFFFFFF
        self.error_code = fields[1]
        self.error_message = b''
        if len(data) > 8:
            self.error_message = data[8:]


class WindowUpdateFrame(Frame):
    # 窗口控制增量

    type = 0x08
    _WINDOW_MAX_INCREMENT = 2 ** 31 - 1

    def __init__(self, stream_id, increment:int=None):
        super(WindowUpdateFrame,self).__init__(stream_id)
        if isinstance(increment, int):
            if increment == 0:
                raise ValueError('PROTOCOL_ERROR. Window increment size can not be 0.')
            if increment < 0 or increment > self._WINDOW_MAX_INCREMENT:
                raise ValueError('Invalid window increment size. ')
            self.increment = increment

    def serialize_body(self):
        return _STRUCT_L.pack(self.increment & 0x7FFFFFFF)

    def parse_body(self, data):
        self.increment = _STRUCT_L.unpack(data)[0] & 0x7FFFFFFF

class ContinuationFrame(Frame):


    type = 0x09
    defined_flags = [
        Flag('END_HEADERS',0x04),
    ]
    def __init__(self, stream_id,
                 headers_data=b'',
                 flags=()):
        super(ContinuationFrame,self).__init__(stream_id,flags)
        self.data = headers_data

    def serialize_body(self):
        payload = self.data
        return payload

    def parse_body(self, data):
        self.data = data


_FRAME_CLASSES = [
    DataFrame,
    HeadersFrame,
    # PriorityFrame,
    RstStreamFrame,
    SettingsFrame,
    # PushPromiseFrame,
    PingFrame,
    GoAwayFrame,
    WindowUpdateFrame,
    ContinuationFrame,
]
#: FRAMES maps the type byte for each frame to the class used to represent that
#: frame.
# 包含对应的帧类型值（字节）和帧类，{帧类型:帧对象}
FRAMES = {cls.type: cls for cls in _FRAME_CLASSES}

if __name__ == '__main__':
    pf = PingFrame(0)
    data = pf.serialize()
    pf.show_itself()
    print(data)
    rf,length = Frame.parse_frame_header(data[0:9])
    rf.parse_body(data[0:9])
    rf.parse_body(data[9:])
    rf.show_itself()


