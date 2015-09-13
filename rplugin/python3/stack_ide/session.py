import threading

class Session(object):
    def __init__(self, async_session, debug):
        self._async_session = async_session
        self._debug = debug


    def send_request(self, tag, contents, handler=None):
        event = threading.Event()
        result = []

        def handle_cb(tag, contents):
            if handler is None:
                result.extend([[tag, contents]])
                event.set()
                return 'done'
            try:
                resp = handler(tag, contents)
            except:
                event.set()
                raise
            else:
                if resp != 'partial':
                    # The handler has finished processing the response. We can
                    # let the calling thread continue.
                    event.set()
                return resp

        if self._async_session.send_request(tag, contents, handle_cb):
            event.wait()

        if len(result) == 0:
            return None
        else:
            return result[0]
