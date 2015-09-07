from collections import deque
import json
import sys
import threading
import traceback


class Session(object):
    def __init__(self, async_session, debug):
        self._response_handler = async_session._response_handler
        async_session._response_handler = self._handle_response
        self._async_session = async_session
        self._debug = debug
        self._command_queue = deque()


    def send_request(self, tag, contents):
        event = threading.Event()
        self._command_queue.append([tag, contents, event])
        if len(self._command_queue) == 1:
            self._send_next_request()
        event.wait()


    def clear_command_queue(self):
        # Get everything back to a consistent state.
        for [_, _, event] in self._command_queue:
            event.set()
        self._command_queue.clear()


    def _send_next_request(self):
        if len(self._command_queue) > 0:
            [tag, contents, event] = self._command_queue[0]
            if not self._async_session.send_request(tag, contents):
                event.set()


    def _handle_response(self, tag, contents):
        if len(self._command_queue) > 0:
            [_, _, event] = self._command_queue[0]
        else:
            event = None
        try:
            resp = self._response_handler(tag, contents)
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



class AsyncSession(object):
    """
    Asynchronous session for a given stack ide process.
    """
    def __init__(self, stack_ide_process, response_handler, debug):
        self.process = stack_ide_process
        self._response_handler = response_handler
        self._debug = debug
        self.process._on_stderr = self._on_stderr
        self.process._on_stdout = self._on_stdout


    def send_request(self, tag, contents):
        if self.process.is_running:
            request = {"tag": tag, "contents": contents}
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

        self._response_handler(tag, contents)
