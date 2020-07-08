from collections import namedtuple


# settings帧支持的flag
SettingsFlags = namedtuple('SettingFlags',['ACK'])
SettingsFlags.ACK = 0x01

# headers帧支持的flag
HeadersFlags = namedtuple('HeadersFlags',[ 'END_STREAM','END_HEADERS','PADDED','PRIORITY'])
HeadersFlags.END_STREAM = 0x01
HeadersFlags.END_HEADERS = 0x04
HeadersFlags.PADDED = 0x08
HeadersFlags.PRIORITY = 0x20

# data帧支持的flag
DataFlags = namedtuple('DataFlags',['END_STREAM','PADDED'])
DataFlags.END_STREAM = 0x01
DataFlags.PADDED = 0x08

Flag = namedtuple("Flag", ["name", "bit"])


class Flags(set):
    """
    A simple MutableSet implementation that will only accept known flags as
    elements.

    Will behave like a regular set(), except that a ValueError will be thrown
    when .add()ing unexpected flags.
    """
    def __init__(self, defined_flags):
        super(Flags,self).__init__()
        self._valid_flags = set(flag.name for flag in defined_flags)
        self._flags = set()

    def __contains__(self, x):
        return self._flags.__contains__(x)

    def __iter__(self):
        return self._flags.__iter__()

    def __len__(self):
        return self._flags.__len__()

    def discard(self, value):
        return self._flags.discard(value)

    def add(self, value):
        if value not in self._valid_flags:
            # print(f'value = {value}')
            raise ValueError(
                "Unexpected flag: {}. Valid flags are: {}".format(
                    value, self._valid_flags
                )
            )
        return self._flags.add(value)

    def __repr__(self):
        return ' '.join(self._flags)

if __name__ == '__main__':
    defined_flags = [
        Flag('END_STREAM', 0x01),
        Flag('END_HEADERS', 0x04),
        Flag('PADDED', 0x08),
        Flag('PRIORITY', 0x20)
    ]
    flags = Flags(defined_flags)
    for n, b in defined_flags:
        print(f'name = {n}, bit = {b}')