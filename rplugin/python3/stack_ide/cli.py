import sys
import json

from common import *

def logger(tag, content):
    print("Handling tag", tag)
    print("Content:", json.JSONEncoder().encode(content))


def main(argv):
    target = argv[1]
    if target == None:
        print("Usage: stack-ide.py TARGET")
        sys.exit(255)
    try:
        manager = None
        def mk_signal_handler(manager):
            def signal_handler(signal, frame):
                manager.end()
            return signal_handler
        import signal

        manager = StackIdeManager(target, logger, print)
        signal.signal(signal.SIGINT, mk_signal_handler(manager))
        api = StackIdeApi(manager)
        api.get_source_errors()
        api.get_loaded_modules()
    except:
        if manager:
            manager.end()


if __name__ == '__main__':
    main(sys.argv)
