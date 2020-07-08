try:
    from .frame import *
except:
    from frame import *

try:
    from .events import *
except:
    from events import *
from enum import Enum
import logging, logconfig
from windows import WindowManager

# 流管理器（暂定，实际处理应该在h2connection中）
# 以及流对象的创建

# 流状态
class StreamState(Enum):
    IDLE = 0
    RESERVED_REMOTE = 1
    RESERVED_LOCAL = 2
    OPEN = 3
    HALF_CLOSED_REMOTE = 4
    HALF_CLOSED_LOCAL = 5
    CLOSED = 6


# 流行为
class StreamActions(Enum):
    SEND_HEADERS = 0
    SEND_PUSH_PROMISE = 1
    SEND_RST_STREAM = 2
    SEND_DATA = 3
    SEND_WINDOW_UPDATE = 4
    SEND_END_STREAM = 5
    RECV_HEADERS = 6
    RECV_PUSH_PROMISE = 7
    RECV_RST_STREAM = 8
    RECV_DATA = 9
    RECV_WINDOW_UPDATE = 10
    RECV_END_STREAM = 11
    RECV_CONTINUATION = 12
    SEND_INFORMATIONAL_HEADERS = 13
    RECV_INFORMATIONAL_HEADERS = 14
    SEND_ALTERNATIVE_SERVICE = 15
    RECV_ALTERNATIVE_SERVICE = 16
    UPGRADE_CLIENT = 17


# 流的状态转换表
#                          +--------+
#                  send PP |        | recv PP
#                 ,--------|  idle  |--------.
#                /         |        |         \
#               v          +--------+          v
#        +----------+          |           +----------+
#        |          |          | send H /  |          |
# ,------| reserved |          | recv H    | reserved |------.
# |      | (local)  |          |           | (remote) |      |
# |      +----------+          v           +----------+      |
# |          |             +--------+             |          |
# |          |     recv ES |        | send ES     |          |
# |   send H |     ,-------|  open  |-------.     | recv H   |
# |          |    /        |        |        \    |          |
# |          v   v         +--------+         v   v          |
# |      +----------+          |           +----------+      |
# |      |   half   |          |           |   half   |      |
# |      |  closed  |          | send R /  |  closed  |      |
# |      | (remote) |          | recv R    | (local)  |      |
# |      +----------+          |           +----------+      |
# |           |                |                 |           |
# |           | send ES /      |       recv ES / |           |
# |           | send R /       v        send R / |           |
# |           | recv R     +--------+   recv R   |           |
# | send R /  `----------->|        |<-----------'  send R / |
# | recv R                 | closed |               recv R   |
# `----------------------->|        |<----------------------'
#                          +--------+
#    send:   发送这个frame的终端
#    recv:   接受这个frame的终端
#
#    H:  HEADERS帧 (隐含CONTINUATION帧)
#    PP: PUSH_PROMISE帧 (隐含CONTINUATION帧)
#    ES: END_STREAM标记
#    R:  RST_STREAM帧
_transitions = {
    # IDLE
    (StreamState.IDLE, StreamActions.SEND_HEADERS): StreamState.OPEN,
    (StreamState.IDLE, StreamActions.RECV_HEADERS): StreamState.OPEN,
    (StreamState.IDLE, StreamActions.SEND_PUSH_PROMISE): StreamState.RESERVED_LOCAL,
    (StreamState.IDLE, StreamActions.RECV_PUSH_PROMISE): StreamState.RESERVED_REMOTE,
    # OPEN
    (StreamState.OPEN, StreamActions.SEND_END_STREAM): StreamState.HALF_CLOSED_LOCAL,
    (StreamState.OPEN, StreamActions.RECV_END_STREAM): StreamState.HALF_CLOSED_REMOTE,
    (StreamState.OPEN, StreamActions.SEND_RST_STREAM): StreamState.CLOSED,
    (StreamState.OPEN, StreamActions.RECV_RST_STREAM): StreamState.CLOSED,
    # RESERVED_LOCAL
    (StreamState.RESERVED_LOCAL, StreamActions.SEND_HEADERS): StreamState.HALF_CLOSED_REMOTE,
    (StreamState.RESERVED_LOCAL, StreamActions.SEND_RST_STREAM): StreamState.CLOSED,
    (StreamState.RESERVED_LOCAL, StreamActions.RECV_RST_STREAM): StreamState.CLOSED,
    # HALF_CLOSED_REMOTE
    (StreamState.HALF_CLOSED_REMOTE, StreamActions.SEND_END_STREAM): StreamState.CLOSED,
    (StreamState.HALF_CLOSED_REMOTE, StreamActions.SEND_RST_STREAM): StreamState.CLOSED,
    (StreamState.HALF_CLOSED_REMOTE, StreamActions.RECV_RST_STREAM): StreamState.CLOSED,
    # RESERVED_REMOTE
    (StreamState.RESERVED_REMOTE, StreamActions.RECV_HEADERS): StreamState.HALF_CLOSED_LOCAL,
    (StreamState.RESERVED_REMOTE, StreamActions.SEND_RST_STREAM): StreamState.CLOSED,
    (StreamState.RESERVED_REMOTE, StreamActions.RECV_RST_STREAM): StreamState.CLOSED,
    # HALF_CLOSED_LOCAL
    (StreamState.HALF_CLOSED_LOCAL, StreamActions.RECV_HEADERS): StreamState.HALF_CLOSED_LOCAL,
    (StreamState.HALF_CLOSED_LOCAL, StreamActions.RECV_END_STREAM): StreamState.CLOSED,
    (StreamState.HALF_CLOSED_LOCAL, StreamActions.SEND_RST_STREAM): StreamState.CLOSED,
    (StreamState.HALF_CLOSED_LOCAL, StreamActions.RECV_RST_STREAM): StreamState.CLOSED,

}


class H2Stream(object):

    status = StreamState.IDLE
    # outbound_window_size: 发送的数据的流动窗口大小
    # inbound_window_size: 接收数据的流动窗口大小
    def __init__(self,
                 stream_id,
                 outbound_window_size,
                 inbound_window_size,
                 max_outbound_frame_size,
                 max_inbound_frame_size):
        self.stream_id = stream_id
        self.outbound_window_size = outbound_window_size
        self.inbound_window_size = inbound_window_size
        self.inbound_window_manager = WindowManager(inbound_window_size)
        # max_outbound_frame_size: 本端发送帧的最大payload长度，
        # 即对端接收帧的最大payload长度（根据对端的Settings帧以及WindowUpdate帧进行设置）
        # max_inbound_frame_size:  本端接收帧的最大payload长度（由本端需求进行配置）
        self.max_outbound_frame_size = max_outbound_frame_size
        self.max_inbound_frame_size = max_inbound_frame_size

    def send_headers(self, headers: dict,
                     encoder,
                     end_stream=False,
                     padded=False,
                     padded_length=0,
                     priority=False,
                     exclusive=False,
                     stream_dependency=0x0,
                     weight=16):

        # 将headers数据按照大小限制进行格式化封帧返回
        # 返回包含headers帧和continuation帧的列表
        headers_flags = set()
        frames = []
        others_length = 0
        if end_stream:
            headers_flags.add('END_STREAM')
        if padded:
            headers_flags.add('PADDED')
            others_length += (1 + padded_length)
        if priority:
            headers_flags.add('PRIORITY')
            others_length += 5
        if others_length > self.max_outbound_frame_size:
            raise ValueError(f'others_length is to long or '
                             f'stream({self.stream_id}).max_outbound_frame_size is not enough. ')
        place = self.max_outbound_frame_size - others_length
        headers_flags = tuple(headers_flags)
        headers_payload = encoder.encode(headers)
        first_block = headers_payload[0:place]
        continuation_blocks = []
        if place < len(headers_payload):
            continuation_payload = headers_payload[place:]
            i = 0
            continuation_blocks = [
                continuation_payload[i:i + self.max_outbound_frame_size]
                for i in range(i, len(continuation_payload), self.max_outbound_frame_size)
            ]
        hf = HeadersFrame(stream_id=self.stream_id,
                          header_data=first_block,
                          flags=headers_flags,
                          padded_length=padded_length,
                          exclusive=exclusive,
                          stream_dependency=stream_dependency,
                          weight=weight
                          )
        frames.append(hf)
        for block in continuation_blocks[1:]:
            cf = ContinuationFrame(self.stream_id, block)
            frames.append(cf)
        frames[-1].add_flag('END_HEADERS')
        old_status = self.status
        self.status = _transitions[(old_status, StreamActions.SEND_HEADERS)]
        if end_stream:
            old_status = self.status
            self.status = _transitions[(old_status, StreamActions.SEND_END_STREAM)]
        return frames

    def receive_headers(self, frame, decoder):

        # 客户端默认接收到的是服务器的响应头
        event = HeadersReceived()
        event.stream_id = self.stream_id
        event.headers = decoder.decode((frame.data))
        if 'END_STREAM' in frame.flags:
            event.end_stream = True
        old_status = self.status
        self.status = _transitions[old_status, StreamActions.RECV_HEADERS]
        return event

    def receive_data(self, frame: DataFrame):
        event = DataReceived()
        event.stream_id = frame.stream_id
        event.data = frame.data
        event.flow_window_length = frame.body_len
        if 'END_STREAM' in frame.flags:
            event.end_stream = True
        self.inbound_window_manager.current_window_reduce(frame.body_len)
        return event

    def ack_data_received(self,received_size):
        increment = self.inbound_window_manager.process_bytes(received_size)
        #print('stream increment:%s,current size:%s'%(increment,self.inbound_window_manager.current_window_size))
        if increment:
            wf = WindowUpdateFrame(self.stream_id, increment)
            return wf
        return []

    def receive_rst_stream(self, frame: RstStreamFrame):

        event = RstStreamReceived()
        event.stream_id = frame.stream_id
        event.error_code = frame.error_code
        old_status = self.status
        self.status = _transitions[(old_status, StreamActions.RECV_RST_STREAM)]
        return event
