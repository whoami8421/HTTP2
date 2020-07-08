
class Event(object):
    # 内部事件基类，留作扩展
    stream_id = None

class HeadersReceived(Event):


    def __init__(self,):
        self.headers = None
        self.end_stream = False

    def __repr__(self):
        return '<HeadersReceived stream_id:%s, headers:%s, end_stream:%s>' % (
            self.stream_id,
            self.headers,
            self.end_stream)

class DataReceived(Event):


    def __init__(self):
        self.data = None
        self.end_stream = False
        # 标记已消耗的窗口
        self.flow_window_length = None

    def __repr__(self):
        return '<DataReceived stream_id:%s, end_stream:%s, data:%s>' % (
            self.stream_id,
            self.end_stream,
            self.data[0:50]+b'...' if self.data else None
        )


class SettingsReceived(Event):


    def __init__(self):
        self.settings = None

    def __repr__(self):
        return '<SettingsReceived stream_id:%s, settings:%s>' % (
            self.stream_id,
            self.settings
        )


class GoawayReceived(Event):

    # 整个连接的结束
    def __init__(self):
        self.error_code = None
        self.error_message = None

    def __repr__(self):
        return '<GoawayReceived stream_id:%s, error_code:%s, error_message:%s>' % (
            self.stream_id,
            self.error_code,
            self.error_message
        )


class RstStreamReceived(Event):

    # 流的结束
    def __init__(self):
        self.error_code = None

    def __repr__(self):
        return '<RstStreamReceived stream_id:%s, error_code:%s>' % (
            self.stream_id,
            self.error_code)


class PingReceived(Event):

    def __init__(self):
        self.ACK = False
        self.data = None

    def __repr__(self):

        return '<PingReceived stream_id:%s, data:%s>' % (self.stream_id, self.data)

