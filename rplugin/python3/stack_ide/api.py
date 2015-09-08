class StackIdeApi(object):
    """
    API for making requests to a stack-ide process.
    """
    def __init__(self, stack_ide_session):
        self._session = stack_ide_session


    def get_exp_types(self, source_span, handler):
        self.send_request("RequestGetExpTypes", source_span, handler)


    def get_span_info(self, source_span, handler):
        self.send_request("RequestGetSpanInfo", source_span, handler)


    def send_request(self, tag, contents=None, handler=None):
        if contents is None:
            contents = []
        try:
            contents.to_stack_ide_contents
        except AttributeError:
            pass
        else:
            contents = contents.to_stack_ide_contents()
        self._session.send_request(tag, contents, handler)
