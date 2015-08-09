import json
from collections import deque
import os
import subprocess
import sys
import threading
import traceback


# XXX Improve this to load the list of targets from the stack
# configuration file. If there is only one, there is no need to ask the
# user. If there is more than one, we could ask the user to select from a
# list.
def guess_stack_target(filename, project_root, stack_yaml):
    target = None
    for d in walkup(os.path.dirname(os.path.realpath(filename))):
        cabal_files = [ f for f in os.listdir(d) if f.endswith('.cabal') ]
        if len(cabal_files) > 0:
            cabal_file = cabal_files[0] if len(cabal_files) > 0 else None
            target = cabal_file.rstrip('.cabal')
            break
    return target


def get_stack_path(path_type, cwd):
    return subprocess.check_output(
            ["stack", "path", "--{0}".format(path_type)],
            universal_newlines=True,
            timeout=2,
            cwd=cwd
            ).rstrip()


def walkup(path): 
    """Yield the given path and each of its parent directories"""
    at_top = False 
    while not at_top: 
        yield path 
        parent_path = os.path.dirname(path) 
        if parent_path == path: 
            at_top = True 
        else: 
            path = parent_path 

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


class BlockingIntercepter(object):
    def __init__(self, manager, debug):
        self.response_handler = manager.response_handler
        manager.response_handler = self.handle_response
        self.manager = manager
        self.debug = debug
        self.command_queue = deque()


    def send_request(self, tag, contents):
        event = threading.Event()
        self.command_queue.append([tag, contents, event])
        if len(self.command_queue) == 1:
            self.send_next_request()
        event.wait()


    def send_next_request(self):
        if len(self.command_queue) > 0:
            [tag, contents, event] = self.command_queue[0]
            if not self.manager.send_request(tag, contents):
                event.set()


    def handle_response(self, tag, contents):
        if len(self.command_queue) > 0:
            [_, _, event] = self.command_queue[0]
        else:
            event = None
        resp = self.response_handler(tag, contents)
        if resp == 'cont':
            # The response_handler has not yet completed processing. We need
            # to wait for more data.
            pass
        elif resp == 'done':
            # The response_handler has finished processing the response. We
            # can let the calling thread continue.
            if event is not None:
                self.command_queue.popleft()
                event.set()
            self.send_next_request()
        elif resp == 'error':
            # Get everything back to a consistent state.
            self.debug("+ BlockingIntercepter got error response. Clearing command_queue")
            if event is not None:
                event.set()
            for e in self.command_queue:
                e.set()
            self.command_queue.clear()



class StackIdeManager(object):
    """
    Manages a single stack ide process.
    """
    def __init__(self, project_root, target, stack_yaml_path, response_handler, debug):
        self.project_root = project_root
        self.target = target
        self.stack_yaml_path = stack_yaml_path
        self.response_handler = response_handler
        self.debug = debug


    def boot_ide_backend(self):
        """
        Start a stack-ide subprocess for the target, and a thread to consume its stdout.
        """
        msg = "+ Launching stack-ide instance in {0} for target {1} using config {2}".format(
                self.project_root, self.target, self.stack_yaml_path)
        self.debug(msg)

        self.process = ProcessManager(
                name="stack ide",
                process_args=["stack", "--stack-yaml", self.stack_yaml_path, "ide", self.target],
                on_stdout=self.on_stdout,
                on_stderr=self.on_stderr,
                cwd=self.project_root,
                debug=self.debug
                )
        self.process.launch()


    def on_stderr(self, error):
        pass


    def on_stdout(self, line):
        """
        Process each line of standard output.
        """
        data = json.loads(line)
        tag = data.get("tag")
        contents = data.get("contents")

        self.response_handler(tag, contents)


    def end(self):
        """
        Ask stack-ide to shut down.
        """
        self.send_request("RequestShutdownSession", [])


    def send_request(self, tag, contents):
        if self.process.is_running:
            request = {"tag": tag, "contents": contents}
            encodedString = json.JSONEncoder().encode(request) + "\n"
            return self.process.send_input(encodedString)
        else:
            self.debug("+ Couldn't send request, no process!")
            return False


    def __del__(self):
        if self.process:
            self.process.terminate()
            self.process = None



class ProcessManager(object):
    """
    Manages a single process.

    - Deals with startup and shutdown.
    - Provides low-level method for making requests.
    - Calls given response_handler with result.
    """
    def __init__(self, name, process_args, on_stdout, on_stderr, cwd, debug):
        self.name = name
        self.process_args = process_args
        self.on_stdout = on_stdout
        self.on_stderr = on_stderr
        self.cwd = cwd
        self.debug = debug


    def launch(self):
        """
        Start a subprocess and threads to consume its stdout and stderr.
        """
        msg = "+ Launching process {0}".format(self.name)
        self.debug(msg)

        self.process = subprocess.Popen(
                self.process_args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self.cwd
                )

        self.stdoutThread = threading.Thread(target=self.read_stdout)
        self.stdoutThread.start()

        self.stderrThread = threading.Thread(target=self.read_stderr)
        self.stderrThread.start()


    def read_stderr(self):
        """
        Read and process any errors.
        """
        while self.process.poll() is None:
            try:
                error = self.process.stderr.readline().decode('UTF-8')
                self.debug(error)
            except:
                self.debug("+ Process {0} ending due to exception: {1}".format(self.name, sys.exc_info()))
                return
        self.debug("+ Process {0} ended.".format(self.name))


    def read_stdout(self):
        """
        Reads JSON responses from stack-ide and dispatch them.
        """
        while self.process.poll() is None:
            try:
                line = self.process.stdout.readline().decode('UTF-8')
                if not line:
                    return
                self.debug("< {0}".format(line))
                self.on_stdout(line)
            except:
                exc = traceback.format_exception(*sys.exc_info())
                self.debug("+ Process {0} ending due to exception: {1}".format(self.name, exc))
                self.terminate()
                return
        self.debug("+ Process {0} ended.".format(self.name))


    def send_input(self, encodedString):
        if self.process:
            self.debug("> {0}".format(encodedString))
            self.process.stdin.write(bytes(encodedString, 'UTF-8'))
            self.process.stdin.flush()
            return True
        else:
            self.debug("+ Couldn't send request, no process!")
            return False


    def is_running(self):
        self.process is not None and self.process.poll() is None


    def terminate(self):
        self.process.terminate()
        self.process = None


    def __del__(self):
        if self.process and (self.process.poll() is None):
            self.terminate()
