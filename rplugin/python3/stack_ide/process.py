import subprocess
import sys
import threading
import traceback


def boot_stack_ide_process(project_root, target, stack_yaml_path, debug):
    """
    Return a Process object for starting a stack ide session.

    The process has not been launched.
    """
    msg = "+ Launching stack-ide instance in {0} for target {1} using config {2}".format(
            project_root, target, stack_yaml_path)
    debug(msg)

    process = Process(
            name="stack ide",
            process_args=["stack", "--stack-yaml", stack_yaml_path, "ide", "start", target],
            cwd=project_root,
            debug=debug
            )
    return process


class Process(object):
    """
    Manages a single process.

    - Deals with startup and shutdown.
    - Provides low-level method for making requests.
    - Calls given response_handler with result.
    """
    def __init__(self, name, process_args, cwd, debug):
        self._name = name
        self._process_args = process_args
        self._cwd = cwd
        self._debug = debug


    def run(self, on_stdout_line, on_stderr_line):
        """
        Start a subprocess and threads to consume its stdout and stderr.
        """
        self._on_stdout_line = on_stdout_line
        self._on_stderr_line = on_stderr_line
        msg = "+ Launching process {0} as {1}".format(self._name, self._process_args)
        self._debug(msg)

        self._process = subprocess.Popen(
                self._process_args,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self._cwd
                )

        self.stdoutThread = threading.Thread(target=self._read_stdout)
        self.stdoutThread.start()

        self.stderrThread = threading.Thread(target=self._read_stderr)
        self.stderrThread.start()


    def send(self, encodedString):
        if self._process:
            self._debug("> {0}".format(encodedString))
            self._process.stdin.write(bytes(encodedString, 'UTF-8'))
            self._process.stdin.flush()
            return True
        else:
            self._debug("+ Couldn't send request, no process!")
            return False


    def is_running(self):
        self._process is not None and self._process.poll() is None


    def terminate(self):
        self._process.terminate()
        self._process = None


    def _read_stderr(self):
        """
        Read and dispatch any errors.
        """
        while self._process.poll() is None:
            try:
                error = self._process.stderr.readline().decode('UTF-8')
                self._debug(error)
                if self._on_stderr_line is not None:
                    self._on_stderr_line(error)
            except:
                self._debug("+ Process {0} ending due to exception: {1}".format(self._name, sys.exc_info()))
                return
        self._debug("+ Process {0} ended.".format(self._name))


    def _read_stdout(self):
        """
        Reads lines from stack-ide's output and dispatches them.
        """
        while self._process.poll() is None:
            try:
                line = self._process.stdout.readline().decode('UTF-8')
                if not line:
                    return
                self._debug("< {0}".format(line))
                if self._on_stdout_line is not None:
                    self._on_stdout_line(line)
            except:
                exc = traceback.format_exception(*sys.exc_info())
                self._debug("+ Process {0} ending due to exception: {1}".format(self._name, exc))
                self.terminate()
                return
        self._debug("+ Process {0} ended.".format(self._name))


    def __del__(self):
        if self._process and (self._process.poll() is None):
            self.terminate()
