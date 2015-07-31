import json
import os
import subprocess

import neovim

try:
    from stack_ide.common import *
except:
    from common import *

class ExpTypesHandler(object):
    def __init__(self, vim, debug):
        self.vim = vim
        self.debug = debug

        self.match_nums = []
        self.types = None
        self.types_index = 0


    def __call__(self, types):
        """
        Highlight the first expression type provided and echo the type to the status bar.
        """
        if types:
            self.types = types
            self.types_index = 0

            # XXX Make sure that this is being done in the correct buffer.
            self.echo_type()
            self.clear_highlight()
            self.highlight_type()
        else:
            pass


    def echo_type(self):
        [type_string, _span] = self.types[self.types_index]
        self.vim.command("echomsg '{0}'".format(type_string))


    def clear_highlight(self):
        for match_num in self.match_nums:
            self.vim.eval("matchdelete({0})".format(match_num))
        self.match_nums.clear()


    def reset_exp_types(self):
        self.clear_highlight()
        # Set the index to one less than the start value as expand_exp_types
        # will increment it before doing anything.
        self.types_index = - 1


    def highlight_type(self):
        [_type_string, span] = self.types[self.types_index]
        [from_line, to_line, from_column, to_column] = unpack_span(span)
        if (from_line == to_line):
            length = to_column - from_column
            positions = ["[[{0}, {1}, {2}]]".format(from_line, from_column, length)]
        else:
            first_line_length = len(self.vim.current.buffer[from_line - 1])
            highlight_length = first_line_length - from_column + 1
            first_line_pos = "[{0}, {1}, {2}]".format(from_line, from_column, highlight_length)
            last_line_pos  = "[{0}, 0, {1}]".format(to_line, to_column)
            other_line_pos = []
            for i in range(from_line + 1, to_line):
                other_line_pos.append("[{0}]".format(i))
            lines = [first_line_pos] + other_line_pos + [last_line_pos]
            # Vim's matchaddpos can only take 8 positions, so we need to work
            # around that.
            chunk_size = 8
            if len(lines) > chunk_size:
                chunked_lines = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
                positions = []
                for l in chunked_lines:
                    positions.append("[{0}]".format(",".join(l)))
            else:
                positions = ["[{0}]".format(",".join(lines))]
        for pos in positions:
            self.match_nums.append(self.vim.eval("matchaddpos('Visual', {0})".format(pos)))


    def expand_exp_types(self):
        if self.types is not None:
            self.types_index += 1
            if self.types_index >= len(self.types):
                self.types_index = 0
            self.echo_type()
            self.clear_highlight()
            self.highlight_type()


def unpack_span(span):
    if span == None:
        return None
    from_line    = span.get("spanFromLine")
    from_column  = span.get("spanFromColumn")
    to_line      = span.get("spanToLine")
    to_column    = span.get("spanToColumn")
    return from_line, to_line, from_column, to_column


class DebugHandler(object):
    def __init__(self, vim):
        self.vim = vim
        self.log_file = open('/tmp/stack_ide_debug.txt', 'w')

    def __call__(self, msg):
        if msg.endswith("\n"):
            self.log_file.write(msg)
        else:
            self.log_file.write("{0}\n".format(msg))
        self.log_file.flush()
        #self.vim.session.threadsafe_call(self.update, msg)

    #def update(self, msg):
    #    self.vim.command("echomsg '{0}'".format(msg))


@neovim.plugin
class StackIde(object):
    """
    Expose Stack IDE API to NeoVim.

    Makes requests to Stack IDE API and dispatches reponses to handler
    callables.
    """
    def __init__(self, vim):
        self.vim = vim
        self.debug = DebugHandler(vim)

        # Map of (project_root, target) to stack-ide API.
        self.apis = {}

        # Callables to handle updating vim.
        #
        # Pulling these out of this class allows them to maintain state
        # without having to worry about name clashes.
        self.exp_types_handler = ExpTypesHandler(vim, self.debug)


    def api_for_current_buffer(self):
        buffer = self.vim.current.buffer
        target = buffer.vars['stack_ide_target']
        project_root = buffer.vars['stack_ide_project_root']
        return self.apis[(project_root, target)]


    def initialize_buffer(self, filename):
        target, project_root, stack_yaml = self.determine_stack_ide_vars(filename)

        api = self.apis.get((project_root, target))
        if api is None:
            manager = StackIdeManager(project_root, target, stack_yaml, self, self.debug)
            api = StackIdeApi(manager)
            self.apis[(project_root, target)] = api


    def determine_stack_ide_vars(self, filename):
        buffer = self.vim.current.buffer
        target = buffer.vars.get('stack_ide_target')
        project_root = buffer.vars.get('stack_ide_project_root')
        stack_yaml = buffer.vars.get('stack_ide_stack_yaml')

        if project_root is None or stack_yaml is None:
            proc = subprocess.Popen(["stack", "path"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=os.path.dirname(os.path.realpath(filename))
                    )
            outs, errs = proc.communicate(timeout=1)
            lines = outs.decode('UTF-8').split("\n")

            if project_root is None:
                project_root = [
                        l.lstrip('project-root:').lstrip()
                        for l in lines
                        if l.startswith('project-root:')
                        ][0]
                buffer.vars['stack_ide_project_root'] = project_root 

            if stack_yaml is None:
                stack_yaml = [
                        l.lstrip('config-location:').lstrip()
                        for l in lines
                        if l.startswith('config-location:')
                        ][0]
                buffer.vars['stack_ide_stack_yaml'] = stack_yaml

        # target is the entry in the stack.yml configuration file. If there is
        # only one entry it is not needed. If there are multiple we must
        # specify one.
        #
        # XXX Improve this to load the list of targets from the stack
        # configuration file. If there is only one, there is no need to ask
        # the user. If there is more than one, we could ask the user to select
        # from a list.
        if target is None:
            target = self.vim.eval('input("Specify taget for stack-ide: ")')
            buffer.vars['stack_ide_target'] = target

        return target, project_root, stack_yaml


    @neovim.autocmd('BufNewFile,BufRead', pattern='*.hs', eval='expand("<afile>")',
                    sync=True)
    def autocmd_handler(self, filename):
        self.initialize_buffer(filename)


    @neovim.command('GetSourceErrors', sync=True)
    def get_source_errors(self):
        self.api_for_current_buffer().get_source_errors()


    @neovim.command('GetLoadedModules', sync=True)
    def get_loaded_modules(self):
        self.api_for_current_buffer().get_loaded_modules()


    @neovim.command('ExpandExpTypes', sync=True)
    def expand_exp_types(self):
        self.exp_types_handler.expand_exp_types()


    @neovim.command('ClearExpTypesHighlight', sync=True)
    def clear_exp_types_highlight(self):
        self.exp_types_handler.reset_exp_types()


    @neovim.command('GetExpTypes', sync=True)
    def get_exp_types(self):
        project_root = self.vim.current.buffer.vars['stack_ide_project_root']
        s = 'substitute(expand("%:p"), "{0}" . "/", "", "")'.format(project_root)
        filename = self.vim.eval(s)

        [line, col] = self.vim.current.window.cursor
        source_span = SourceSpan(filename, line, line, col+1, col+2)
        self.api_for_current_buffer().get_exp_types(source_span)


    def __call__(self, tag, contents):
        self.vim.session.threadsafe_call(self.dispatch, tag, contents)


    def dispatch(self, tag, contents):
        if tag == 'ResponseGetExpTypes':
            self.exp_types_handler(contents)


    def __del__(self):
        self.manager.terminate()
