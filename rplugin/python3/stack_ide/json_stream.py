import json


class JsonStream(object):

    """JSON stream that wraps a byte stream.

    This wraps an interface for reading/writing bytes and exposes an interface
    for reading/writing JSON messages.
    """

    def __init__(self, stack_ide_process, debug):
        self._process = stack_ide_process
        self._debug = debug


    def run(self, on_message):
        self._on_message = on_message
        self._process.run(self._on_stdout_line, self._on_stderr_line)


    def send(self, request):
        if self._process.is_running:
            encodedString = json.JSONEncoder().encode(request) + "\n"
            return self._process.send(encodedString)
        else:
            self._debug("+ Couldn't send request, no process!")
            return False


    def _on_stderr_line(self, error_line):
        pass


    def _on_stdout_line(self, line):
        """
        Process each line from the byte stream.
        """
        try:
            msg = json.loads(line)
        except:
            self._debug("+ reponse not valid JSON. Ignoring")
        else:
            self._on_message(msg)
