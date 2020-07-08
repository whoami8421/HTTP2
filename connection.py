try:
    from .stream import H2Stream, StreamState
except:
    from stream import H2Stream, StreamState

try:
    from .settings import Settings
except:
    from settings import Settings

try:
    from .frame import *
except:
    from frame import *

try:
    from .events import *
except:
    from events import *

from hpack.hpack import Encoder, Decoder
import logging, logconfig
from windows import WindowManager

class ConnectionState(object):
    IDLE = 0
    OPEN = 1
    CLOSED = 2

# 用于处理headers帧以及continuation帧的缓冲区
class FrameBuffer(object):

    CONTINUATION_BACKLOG = 64
    def __init__(self, max_frame_size):
        super(FrameBuffer, self).__init__()
        self.data = b''
        self.max_frame_size = max_frame_size
    def add(self, data):
        self.data += data
        self.header_blocks = []

    def __iter__(self):
        return self

    def __next__(self):
        if len(self.data) < 9:
            # 接收到的头部数据不完整，保留至下一次解析
            raise StopIteration()
        header = self.data[0:9]
        try:
            frame, length = Frame.parse_frame_header(header)
        except:
            raise ValueError('Frame header parse failed. ')
        if len(self.data) < length + 9:
            # 说明缓冲区接收到的数据payload不完整，保留至下一次解析
            raise StopIteration()
        # 暂时未配置push_promise 帧
        # 对被分块的帧合并成一个总headers
        frame.parse_body(self.data[9:9+length])
        if self.header_blocks:
            if frame.stream_id != self.header_blocks[0].stream_id:
                raise ValueError('Invalid continuation frame for its headers.')
            self.header_blocks.append(frame)

            if 'END_HEADERS' in frame.flags:
                self.header_blocks[0].add_flag('END_HEADERS')
                frame = self.header_blocks[0]
                frame.data = b''.join([f.d for f in self.header_blocks])
                self.header_blocks = []
            else:
                frame = None
        elif (isinstance(frame, (HeadersFrame, PushPromiseFrame)) and
                'END_HEADERS' not in frame.flags):
            self.header_blocks.append(frame)
        if len(self.header_blocks) > self.CONTINUATION_BACKLOG:
            raise ValueError('too many continuation frames.')
        self.data = self.data[9+length:]
        return frame if frame is not None else self.__next__()


# h2连接对象，同时用于管理整个流
class H2Connection(object):
    # 对端默认最大帧payload长度
    DEFAULT_MAX_OUTBOUND_FRAME_SIZE = 65535
    # 本端默认最大帧payload长度
    DEFAULT_MAX_INBOUND_FRAME_SIZE = 2 ** 24
    HIGHEST_ALLOWED_STREAM_ID = 2 ** 31 - 1
    DEFAULT_MAX_HEADER_LIST_SIZE = 2 ** 16
    # 最大窗口限制
    MAX_FLOW_CONTROL_WINDOW = 2 ** 31 - 1

    status = ConnectionState.IDLE

    def __init__(self, local_settings=None):
        super(H2Connection, self).__init__()
        self.encoder = Encoder()
        self.decoder = Decoder()
        self.streams = {}
        self.local_settings = Settings(local_settings)
        self.remote_settings = Settings()
        # 接收数据窗口
        self.inbound_flow_control_window = self.local_settings.initial_window_size

        self.inbound_window_manager = WindowManager(self.local_settings.initial_window_size)
        # 发送数据窗口（根据对端接受能力，取决于对端设置）
        self.outbound_flow_control_window = self.remote_settings.initial_window_size
        self.__set_encoder()
        self.__set_decoder()
        # 接收数据缓冲区
        self.inbound_buffer = FrameBuffer(self.local_settings.max_frame_size)
        # 待发送的数据缓冲区
        self._data_to_send = b''

        self.__dispatch_table = {
            SettingsFrame: self._receive_settings_frame,
            HeadersFrame: self._receive_headers_frame,
            DataFrame: self._receive_data_frame,
            WindowUpdateFrame: self.receive_window_update_frame,
            GoAwayFrame: self.receive_goaway_frame,
            RstStreamFrame: self._receive_rst_stream_frame,
            PingFrame: self._receive_ping_frame
        }

    def initiate_connection(self):
        pre_message = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'
        logging.info('initiate connection. ')
        f = SettingsFrame(0)
        for setting, value in self.local_settings.items():
            f.settings[setting] = value
        logging.info('stream_id:0 send settings frame.(%s)' % f.settings)
        self._data_to_send += pre_message + f.serialize()


    def send_headers(self, stream_id, headers,
                     end_stream=False,
                     padded=False,
                     padded_length=0,
                     priority=False,
                     exclusive=False,
                     stream_dependency=0x0,
                     weight=16):
        if stream_id < 1 or stream_id > self.HIGHEST_ALLOWED_STREAM_ID:
            raise ValueError('the stream id is out of valid range. ')
        if stream_id % 2 != 1:
            raise ValueError('the stream id is not a client id (it should be an odd number). ')
        stream = self._get_stream_from_id(stream_id)
        if not stream:
            stream = self._create_stream(stream_id)
        frames = stream.send_headers(headers,self.encoder,
                                     end_stream,
                                     padded,
                                     padded_length,
                                     priority,
                                     exclusive,
                                     stream_dependency,
                                     weight)
        logging.info('stream_id:%s send headers frame. ' % stream.stream_id)
        self._prepare_for_send(frames)

    # 接受到settings帧，解析它并进行配置更新
    def _receive_settings_frame(self, frame:SettingsFrame):
        # 根据接收到的是否为ACK帧进行判断处理
        assert frame.stream_id == 0, 'settings frame stream id should be 0. '
        if 'ACK' in frame.flags:
            logging.info('stream_id:%s receive settings ACK frame. ' % frame.stream_id)
            pass
        else:
            logging.info('stream_id:%s receive settings frame.(%s) ' % (frame.stream_id,frame.settings))
            for setting, value in frame.settings.items():
                if setting in self.remote_settings:
                    self.remote_settings[setting] = value
            ack_frame = SettingsFrame(frame.stream_id)
            self._prepare_for_send([ack_frame])
            logging.info('stream_id:%s send settings ACK frame. ' % ack_frame.stream_id)
        return []
    # def receive_data(self, data):
    #     # 总的数据接收入口
    #     pass
    def _receive_headers_frame(self, frame):

        stream = self._get_stream_from_id(frame.stream_id)
        if not stream:
            stream = self._create_stream(frame.stream_id)
        event = stream.receive_headers(frame, self.decoder)
        logging.info('stream_id:%s receive headers frame. ' % stream.stream_id)
        return [event]

    def _receive_continuation_frame(self, frame):
        logging.info('stream_id:%s receive continuation frame. ' % frame.stream_id)

    def _receive_data_frame(self, frame:DataFrame):

        stream = self._get_stream_from_id(frame.stream_id)
        # print(frame.body_len,self.inbound_window_manager.current_window_size)
        self.inbound_window_manager.current_window_reduce(frame.body_len)
        if not stream:
            stream = self._create_stream(frame.stream_id)
        event = stream.receive_data(frame)

        logging.info('stream_id:%s receive data frame(end stream:%s). ' % (stream.stream_id, event.end_stream))
        # if event.end_stream:
        #     end_stream_frame = DataFrame(event.stream_id)
        #     end_stream_frame.add_flag('END_STREAM')
        #     self._prepare_for_send([end_stream_frame])
        return [event]

    def ack_data_received(self, received_size, stream_id=None):
        # 表示数据已接收，通知流窗口管理器
        # print(self.inbound_window_manager.current_window_size)
        frames = []
        increment = self.inbound_window_manager.process_bytes(received_size)
        # print('conn increment:%s,current size:%s'%(increment,self.inbound_window_manager.current_window_size))
        if increment:
            wf = WindowUpdateFrame(0,increment)
            logging.info('stream_id:%s send window update(%s)'%(0,increment))
            frames.append(wf)

        if stream_id:
            stream = self._get_stream_from_id(stream_id)
            if stream:
                wf = stream.ack_data_received(received_size)
                if wf:
                    frames.append(wf)
                    logging.info('stream_id:%s send window update(%s)' % (stream.stream_id, wf.increment))

        self._prepare_for_send(frames)

    def _receive_rst_stream_frame(self, frame):

        stream = self._get_stream_from_id(frame.stream_id)
        if not stream:
            stream = self._create_stream(frame.stream_id)
        if stream.status == StreamState.IDLE:
            raise ValueError('IDLE stream receive rst_stream frame. ')
        event = stream.receive_rst_stream(frame)
        logging.info('stream_id:%s receive reset stream. ' % stream.stream_id)
        return [event]

    def receive_goaway_frame(self, frame:GoAwayFrame):

        event = GoawayReceived()
        event.stream_id = frame.stream_id
        event.error_code = frame.error_code
        event.error_message = frame.error_message
        self.status = ConnectionState.CLOSED
        logging.info('stream_id:%s receive goaway frame. ' % frame.stream_id)
        return [event]

    def receive_window_update_frame(self, frame:WindowUpdateFrame):
        # 暂时未实现流控完整性
        increment = frame.increment
        if self.outbound_flow_control_window + increment > 2**31 - 1:
            raise ValueError('outbound window should not more than 2**31 - 1.')
        self.outbound_flow_control_window += increment
        logging.info('stream_id:%s receive window update frame(%d). ' % (frame.stream_id, increment))
        return []

    def _receive_ping_frame(self, frame:PingFrame):
        events = []
        if 'ACK' in frame.flags:
            e = PingReceived()
            e.ACK = True
            e.stream_id = frame.stream_id
            e.data = frame.data
            logging.info('stream_id:%s received ping frame(ACK:%s). ' % (frame.stream_id,
                                                                         e.ACK))
            events.append(e)
        else:
            p_ack = PingFrame(0, frame.data, ('ACK',))
            e = PingReceived()
            e.stream_id = frame.stream_id
            e.data = frame.data
            logging.info('stream_id:%s send ping frame(ACK:%s). ' % (frame.stream_id,
                                                                         e.ACK))
            events.append(e)
            self._prepare_for_send([p_ack])

        return events

    def _get_stream_from_id(self, stream_id) -> H2Stream:

        stream = self.streams.get(stream_id, None)
        return stream

    # 注意：stream_id的合法性还没有进行验证，
    # 流id的管理功能还未实现，
    def _create_stream(self, stream_id):
        # 默认作为客户端创建流，且不接受推送
        if stream_id < 0 or stream_id > 2**31 - 1:
            raise ValueError('stream id is out of range.')
        if stream_id < self.max_current_stream_id:
            raise ValueError('new stream id must be higher than %s'
                             % self.max_current_stream_id)
        if stream_id % 2 != 1:
            raise ValueError('Invalid client stream id. ')
        for sid, stream in self.streams.items():
            if stream.status == StreamState.CLOSED:
                self.streams.pop(sid)
        stream = H2Stream(stream_id,
                          self.outbound_flow_control_window,
                          self.inbound_flow_control_window,
                          self.remote_settings.max_frame_size,
                          self.local_settings.max_frame_size)
        self.streams[stream_id] = stream
        return stream

    def get_next_available_stream(self):
        # 返回下一个可开启的id
        for sid, stream in self.streams.items():
            if stream.status == StreamState.CLOSED:
                self.streams.pop(sid)
        if self.streams:
            current_highest_id = max(self.streams.keys())
        else:
            current_highest_id = 0
        if current_highest_id % 2 == 1:
            available_id = current_highest_id + 2
        else:
            available_id = current_highest_id + 1
        if available_id > (2**31 - 1):
            return None
        return available_id

    @property
    def max_current_stream_id(self):
        # 当前已打开的最大流id
        # 更新并返回最大id
        for sid, stream in self.streams.items():
            if stream.status == StreamState.CLOSED:
                self.streams.pop(sid)
        return max(self.streams.keys(), default=0)

    def _prepare_for_send(self, frames):
        for frame in frames:
            self._data_to_send += frame.serialize()

    def data_to_send(self):
        # 返回需要发送的数据，并清空缓存区
        data = self._data_to_send
        self._data_to_send = b''
        return data

    # 根据配置设置hpack编码参数
    def __set_encoder(self):
        self.encoder.max_header_list_size = self.remote_settings.max_header_list_size
        self.encoder.header_table_size = self.remote_settings.header_table_size

    # 根据配置设置hpack解码参数
    def __set_decoder(self):
        self.decoder.max_header_list_size = self.local_settings.max_header_list_size
        self.decoder.header_table_size = self.local_settings.header_table_size

    def send_data(self, stream_id, data):
        # 封帧
        pass

    def receive_data(self, data):
        events = []
        self.inbound_buffer.add(data)
        for frame in self.inbound_buffer:
            event = self.__dispatch_table[frame.__class__](frame)
            events.extend(event)
        return events

    def close_connection(self, last_stream_id=None,
                         error_code=0,
                         error_message=b''):
        _last_stream_id = (last_stream_id if last_stream_id
                           else self.max_current_stream_id)
        gf = GoAwayFrame(0,_last_stream_id, error_code,error_message)
        logging.info('stream_id:%s send goaway frame. ' % gf.stream_id)
        self._prepare_for_send([gf])

    def send_rst_stream(self,stream_id, error_code=0):

        rf = RstStreamFrame(stream_id, error_code)
        stream = self._get_stream_from_id(stream_id)
        if not stream:
            raise ValueError('there is not stream_id_%s to send rst_frame.')
        stream.status = StreamState.CLOSED
        logging.info('stream_id:%s send reset stream frame. ' % rf.stream_id)
        self._prepare_for_send([rf])

    def send_ping(self, opaque_data=b''):

        pf = PingFrame(0, opaque_data)
        logging.info('stream_id:%s send ping frame. ' % pf.stream_id)
        self._prepare_for_send([pf])

    def send_window_update(self, increment, stream_id=0):
        wf = WindowUpdateFrame(stream_id, increment)
        self._prepare_for_send([wf])


if __name__ == '__main__':

    s = H2Connection()
