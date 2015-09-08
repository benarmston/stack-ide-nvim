import os
import subprocess

try:
    from stack_ide.api import *
    from stack_ide.process import *
    from stack_ide.session import *
except:
    from api import *
    from process import *
    from session import *


def stack_ide_api_for(project_root, target, stack_yaml, debug):
    stack_ide_process = boot_stack_ide_process(project_root, target, stack_yaml, debug)
    async_session = AsyncSession(stack_ide_process, debug)
    session = Session(async_session, debug)
    stack_ide_process.launch()
    api = StackIdeApi(session)
    return api


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
