from collections import deque
import json
import sys
import threading
import traceback
import uuid


class Session(object):
    def __init__(self, async_session, debug):
        self._async_session = async_session
        self._debug = debug
        self._command_queue = deque()


    def send_request(self, tag, contents, handler=None):
        event = threading.Event()
        self._command_queue.append([tag, contents, event, handler])
        if len(self._command_queue) == 1:
            self._send_next_request()
        event.wait()


    def clear_command_queue(self):
        # Get everything back to a consistent state.
        for [_, _, event, _] in self._command_queue:
            event.set()
        self._command_queue.clear()


    def _send_next_request(self):
        if len(self._command_queue) > 0:
            [tag, contents, event, _] = self._command_queue[0]
            if not self._async_session.send_request(tag, contents, self._handle_response):
                event.set()


    def _handle_response(self, tag, contents):
        if len(self._command_queue) > 0:
            [_, _, event, handler] = self._command_queue[0]
        else:
            handler = None
            event = None
        self._debug("{0}".format(handler))

        if handler is None:
            return 'done'

        try:
            resp = handler(tag, contents)
        except:
            exc = traceback.format_exception(*sys.exc_info())
            self._debug("+ Session handler raised. Clearing command_queue. {0}".format(exc))
            self.clear_command_queue()
        else:
            self._debug("+ got response {0}".format(resp))
            if resp == 'cont':
                # The response_handler has not yet completed processing. We need
                # to wait for more data.
                pass
            elif resp == 'done':
                # The response_handler has finished processing the response. We
                # can let the calling thread continue.
                if event is not None:
                    self._command_queue.popleft()
                    event.set()
                self._send_next_request()
            elif resp == 'error':
                self._debug("+ Session got error response. Clearing command_queue")
                self.clear_command_queue()

            return resp



class AsyncSession(object):
    """
    Asynchronous session for a given stack ide process.
    """
    def __init__(self, stack_ide_process, debug):
        self.process = stack_ide_process
        self._debug = debug
        self.process._on_stderr = self._on_stderr
        self.process._on_stdout = self._on_stdout
        self.conts = {}


    def send_request(self, tag, contents, on_response):
        if self.process.is_running:
            seq = str(uuid.uuid4())
            self.conts[seq] = on_response
            request = {"tag": tag, "contents": contents, "seq": seq}
            encodedString = json.JSONEncoder().encode(request) + "\n"
            return self.process.send_input(encodedString)
        else:
            self._debug("+ Couldn't send request, no process!")
            return False


    def end(self):
        """
        Ask stack-ide to shut down.
        """
        self.send_request("RequestShutdownSession", [])


    def _on_stderr(self, error):
        pass


    def _on_stdout(self, line):
        """
        Process each line of standard output.
        """
        data = json.loads(line)
        tag = data.get("tag")
        contents = data.get("contents")
        seq = data.get("seq")

        if seq is not None:
            response_handler = self.conts.get(seq)
            if response_handler is not None:
                resp = response_handler(tag, contents)
                if resp == 'cont':
                    # The handler wants more data.
                    pass
                else:
                    del self.conts[seq]
