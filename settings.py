try:
    from .frame import SettingsFrame
except:
    from frame import SettingsFrame

class Settings(dict):
    # 默认配置

    def __init__(self,settings_dict = None):
        super(Settings, self).__init__()
        self.__settings = {
            # 允许发送者通知远端，
            # 用于解码首部块的首部压缩表的最大大小，
            # 以字节位单位。编码器可以可以选择任何等于或小于这个值的大小，
            # 初始值是4096字节。
            SettingsFrame.HEADER_TABLE_SIZE: 4096,
            # 是否允许服务器推送，仅用于爬虫的话默认关闭推送（个人建议）
            SettingsFrame.ENABLE_PUSH: 0,
            # 允许的最大的并发流个数。这个限制是有方向的：
            # 它应用于发送者允许接收者创建的流的个数。
            # 初始时，这个值没有限制。建议这个值不要小于100，
            # 以便于不要不必要地限制了并发性。
            SettingsFrame.MAX_CONCURRENT_STREAMS: 100,
            # 初始流控窗口,初始值为2^16 - 1 (65,535)字节。
            SettingsFrame.INITIAL_WINDOW_SIZE: 65535,
            # 最大frame size在 2**14 至 2**24-1 之间，初始值2**14
            SettingsFrame.MAX_FRAME_SIZE: 16384,
            # 这个建议性的设置通知对端发送者准备接受的首部列表的最大大小，
            # 以字节为单位。这个值是基于首部字段未压缩的大小来计算的，
            # 包括名字和值以字节为单位的长度，
            # 再为每个首部字段加上32字节。
            # 对于任何给定的请求，可以实施小于宣告的限制的值。
            # 这个设置项的初始值没有限制。暂时设置为65535
            SettingsFrame.MAX_HEADER_LIST_SIZE: 65535,
        }

        # 使用自定义参数，传入配置字典
        if settings_dict != None:
            if not isinstance(settings_dict,dict):
                raise ValueError('settings dict must be a dict.')
            for k, v in settings_dict.items():
                if k in self.__settings:
                    self.__settings[k] = v
        # 使用默认配置参数
        else:
            pass

    def items(self):
        return self.__settings.items()

    def __contains__(self, item):
        return self.__settings.__contains__(item)

    def __iter__(self):
        return self.__settings.__iter__()

    def __repr__(self):
        return '<class %s, settings: %s>' % (self.__class__, self.__settings)
    @property
    def initial_window_size(self):
        return self.__settings[SettingsFrame.INITIAL_WINDOW_SIZE]

    @initial_window_size.setter
    def initial_window_size(self, value):
        self.__settings[SettingsFrame.INITIAL_WINDOW_SIZE] = value

    @property
    def max_frame_size(self):
        return self.__settings[SettingsFrame.MAX_FRAME_SIZE]

    @max_frame_size.setter
    def max_frame_size(self, value):
        self.__settings[SettingsFrame.MAX_FRAME_SIZE] = value

    @property
    def max_concurrent_streams(self):
        return self.__settings[SettingsFrame.MAX_CONCURRENT_STREAMS]

    @max_concurrent_streams.setter
    def max_concurrent_streams(self, value):
        self.__settings[SettingsFrame.MAX_CONCURRENT_STREAMS] = value

    @property
    def header_table_size(self):
        return self.__settings[SettingsFrame.HEADER_TABLE_SIZE]

    @header_table_size.setter
    def header_table_size(self, value):
        self.__settings[SettingsFrame.HEADER_TABLE_SIZE] = value

    @property
    def enable_push(self):
        return self.__settings[SettingsFrame.ENABLE_PUSH]

    @enable_push.setter
    def enable_push(self, value):
        self.__settings[SettingsFrame.ENABLE_PUSH] = value

    @property
    def max_header_list_size(self):
        return self.__settings[SettingsFrame.MAX_HEADER_LIST_SIZE]

    @max_header_list_size.setter
    def max_header_list_size(self, value):
        self.__settings[SettingsFrame.MAX_HEADER_LIST_SIZE] = value

    @property
    # 实质上是把initial_window_size当作最大窗口值
    def max_window_size(self):
        return self.__settings[SettingsFrame.INITIAL_WINDOW_SIZE]




