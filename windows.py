
# h2窗口流控制管理

LARGEST_FLOW_CONTROL_WINDOW = 2**31 - 1

class WindowManager(object):

    def __init__(self, max_window_size):
        # 当前窗口最大量
        self.max_window_size = max_window_size
        # 当前窗口量
        self.current_window_size = max_window_size
        # 已处理的字节数
        self.bytes_processed = 0

    def current_window_add(self, size):
        # 窗口增加
        self.current_window_size += size
        if self.current_window_size > LARGEST_FLOW_CONTROL_WINDOW:
            raise ValueError('current windows is up 2**31-1. ')

    def current_window_reduce(self, size):
        # 窗口减少
        self.current_window_size -= size
        #print(size,self.current_window_size)
        if self.current_window_size < 0:
            raise ValueError('current windows below 0. ')

    def process_bytes(self, size):
        # 已处理的字节数
        self.bytes_processed += size
        return self._maybe_window_increment()

    def _maybe_window_increment(self):
        if not self.bytes_processed:
            return None
        increment = 0
        # 处理字节达到最大值的1/2时，将当前窗口恢复至最大窗口
        if self.bytes_processed > (self.max_window_size // 2):
            if self.bytes_processed + self.current_window_size > self.max_window_size:
                increment = self.max_window_size - self.current_window_size
            else:
                increment = self.bytes_processed
            self.bytes_processed = 0
        # 否则不更新当前窗口
        self.current_window_size += increment
        return increment

    def change_max_window(self, max_window_size):
        # 用于接收到settings帧将窗口限制值进行修改（一般只有减小）
        self.max_window_size = max_window_size




