import json
import sys
import traceback
import uuid


class AsyncSession(object):
    """
    Asynchronous session for a given stack ide process.
    """
    def __init__(self, json_stream, debug):
        self._json_stream = json_stream
        self._debug = debug
        self._pending_requests = {}


    def run(self, default_handler):
        self._default_handler = default_handler
        self._json_stream.run(self._on_message)


    def send_request(self, tag, contents, on_response):
        seq = str(uuid.uuid4())
        self._pending_requests[seq] = on_response
        request = {"tag": tag, "contents": contents, "seq": seq}
        return self._json_stream.send(request)


    def end(self):
        """
        Ask stack-ide to shut down.
        """
        self.send_request("RequestShutdownSession", [])


    def _on_message(self, msg):
        """
        Process each message from the JSON stream.
        """
        tag = msg.get("tag")
        contents = msg.get("contents")
        seq = msg.get("seq")

        if seq is None:
            self._run_handler(self._default_handler, tag, contents)
        else:
            handler = self._pending_requests.get(seq)

            if handler is not None:
                resp = self._run_handler(handler, tag, contents)
                if resp != 'partial':
                    # The handler has completed processing (or errored).
                    # Either way were done with this request.
                    del self._pending_requests[seq]


    def _run_handler(self, handler, tag, contents):
        try:
            return handler(tag, contents)
        except:
            exc = traceback.format_exception(*sys.exc_info())
            self._debug("+ Response handler raised. {0}".format(exc))
            return 'error'
