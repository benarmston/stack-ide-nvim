import json
import os
import subprocess
import sys
import threading

#
# API for making requests to a stack-ide process.
#
class StackIdeApi(object):
    def __init__(self, stack_ide_manager):
        self.stack_ide = stack_ide_manager


    # def update_session(self, update_sessions):
    #     self.send_request('RequestUpdateSession', update_sessions)


    def get_loaded_modules(self):
        self.send_request('RequestGetLoadedModules')


    def get_source_errors(self):
        self.send_request('RequestGetSourceErrors')


    def get_exp_types(self, source_span):
        self.send_request("RequestGetExpTypes", source_span)


    def send_request(self, tag, contents=None):
        if contents is None:
            contents = []
        try:
            contents.to_stack_ide_contents
        except AttributeError:
            pass
        else:
            contents = contents.to_stack_ide_contents()
        self.stack_ide.send_request(tag, contents)


class SourceSpan(object):
    def __init__(self, file_path, from_line, to_line, from_column, to_column):
        self.file_path = file_path
        self.from_line = from_line
        self.to_line = to_line
        self.from_column = from_column
        self.to_column = to_column


    def to_stack_ide_contents(self):
        return {
                "spanFilePath": self.file_path,
                "spanFromLine": self.from_line,
                "spanToLine": self.to_line,
                "spanFromColumn": self.from_column,
                "spanToColumn": self.to_column
                }


#
# Manager for a stack-ide process.
#
# Deals with startup and shutdown.
# Provides low-level method for making requests.
# Calls given response_handler with result.
#
class StackIdeManager(object):
    def __init__(self, project_root, target, stack_yaml_path, response_handler, debug):
        self.project_root = project_root
        self.target = target
        self.stack_yaml_path = stack_yaml_path
        self.response_handler = response_handler
        self.debug = debug
        self.boot_ide_backend()


    def boot_ide_backend(self):
        """
        Start a stack-ide subprocess for the target, and a thread to consume its stdout.
        """
        msg = "Launching stack-ide instance in {0} for target {1} using config {2}".format(
                self.project_root, self.target, self.stack_yaml_path)
        self.debug(msg)

        self.process = subprocess.Popen(
                ["stack", "--stack-yaml", self.stack_yaml_path, "ide", self.target],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self.project_root
                )

        self.stdoutThread = threading.Thread(target=self.read_stdout)
        self.stdoutThread.start()

        self.stderrThread = threading.Thread(target=self.read_stderr)
        self.stderrThread.start()


    def read_stderr(self):
        """
        Reads any errors from the stack-ide process.
        """
        while self.process.poll() is None:
            try:
                error = self.process.stderr.readline().decode('UTF-8')
                self.debug("Stack-IDE error: {0}".format(error))
            except:
                self.debug("Stack-IDE stderr process ending due to exception: {0}".format(sys.exc_info()))
                return;
        self.debug("Stack-IDE stderr process ended.")


    def read_stdout(self):
        """
        Reads JSON responses from stack-ide and dispatch them.
        """
        while self.process.poll() is None:
            try:
                raw = self.process.stdout.readline().decode('UTF-8')
                if not raw:
                    return

                data = json.loads(raw)
                response = data.get("tag")
                contents = data.get("contents")

                self.debug("< {0}".format(raw))
                self.response_handler(response, contents)

            except:
                self.debug("Stack-IDE stdout process ending due to exception: {0}".format(sys.exc_info()))
                self.process.terminate()
                self.process = None
                return;
        self.debug("Stack-IDE stdout process ended.")


    def end(self):
        """
        Ask stack-ide to shut down.
        """
        self.send_request("RequestShutdownSession", [])


    def send_request(self, tag, contents):
        if self.process:
            request = {"tag": tag, "contents": contents}
            encodedString = json.JSONEncoder().encode(request) + "\n"
            self.debug("> {0}".format(encodedString))
            self.process.stdin.write(bytes(encodedString, 'UTF-8'))
            self.process.stdin.flush()
        else:
            self.debug("Couldn't send request, no process!")



    def __del__(self):
        if self.process and (self.process.poll() is None):
            self.process.terminate()
            self.process = None
