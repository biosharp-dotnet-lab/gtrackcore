import pyparsing as pp


class CommandParser():
    def __init__(self, operations, btrack):
        self._operations = operations
        self._btrack = btrack

    def parse(self, expr):
        lPar = pp.Literal("(").suppress()
        rPar = pp.Literal(")").suppress()

        literalTrue = pp.Keyword('true', caseless=True)
        literalTrue.setParseAction(pp.replaceWith(True))
        literalFalse = pp.Keyword('false', caseless=True)
        literalFalse.setParseAction(pp.replaceWith(False))
        booleanLiteral = literalTrue | literalFalse
        literal = pp.quotedString ^ pp.pyparsing_common.number ^ booleanLiteral

        identifier = pp.Word(pp.alphas, pp.alphanums + "_").setName('identifier')
        trackName = pp.Group(identifier + pp.ZeroOrMore(pp.Literal(':') + identifier))
        trackName = trackName.setParseAction(self.trackNameAction)

        functionCall = pp.Forward()
        expression = (trackName ^ literal ^ functionCall).setName('expression')
        assignment = pp.Group(trackName + pp.Literal('=') + functionCall)
        assignment = assignment.setParseAction(self.assignmentAction)

        kwargValue = functionCall | literal
        kwarg = pp.Group(identifier + pp.Literal('=') + kwargValue)
        kwarg.setParseAction(self.kwArgAction)

        func_arg = kwarg | expression
        functionCall << pp.Group(identifier + lPar + pp.Optional(pp.delimitedList(func_arg)) + rPar)
        functionCall = functionCall.setParseAction(self.functionCallAction)
        statement = assignment ^ functionCall

        parsedStatement = statement.parseString(expr)
        if isinstance(parsedStatement[0], FunctionCall):
            funcCallObj = self._evalExpression(parsedStatement[0])

            return funcCallObj
        elif isinstance(parsedStatement[0], Assignment):
            assignment = (parsedStatement[0].name, self._evalExpression(parsedStatement[0].value))

            return assignment

    def _evalExpression(self, expr):
        if isinstance(expr, str):
            if expr[0] in '"\'':  # string literal
                return expr[1:-1]  # remove quotes
            else:
                "Unrecognized element - can't evaluate"
        elif isinstance(expr, FunctionCall):
            a = []
            kw = {}
            for arg in expr.args:
                if isinstance(arg, TrackName):
                    trackContents = self._btrack.getTrackContentsByTrackNameAsString(arg.name).getTrackContents()
                    a.append(trackContents)
                elif isinstance(arg, KwArg):  # kw arg
                    kw[arg.name] = arg.value
                else:  # func or literal
                    a.append(self._evalExpression(arg))
            return self._operations[expr.name](*a, **kw)
        else:  # number
            return expr

    def kwArgAction(self, tokens):
        kwArg = KwArg(tokens[0][0], tokens[0][2])

        return kwArg

    def functionCallAction(self, tokens):
        functionCall = FunctionCall(tokens[0][0], tokens[0][1:])

        return functionCall

    def trackNameAction(self, tokens):
        trackName = TrackName(''.join(tokens[0]))

        return trackName

    def assignmentAction(self, tokens):
        if isinstance(tokens[0][0], TrackName):
            name = tokens[0][0].name
        else:
            name = tokens[0][0]
        assignment = Assignment(name, tokens[0][2])

        return assignment


class KwArg():
    def __init__(self, name, value):
        self.name = name
        self.value = value


class FunctionCall():
    def __init__(self, name, args):
        self.name = name
        self.args = args


class TrackName():
    def __init__(self, name):
        self.name = name


class Assignment():
    def __init__(self, name, value):
        self.name = name
        self.value = value