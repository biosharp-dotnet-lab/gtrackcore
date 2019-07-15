# cython: infer_types=True
# cython: profile=True

import numpy

from gtrackcore.util.CommonConstants import BINARY_MISSING_VAL
from gtrackcore.util.CustomExceptions import InvalidFormatError

import pyximport; pyximport.install(setup_args={"include_dirs":numpy.get_include()},
                                    reload_support=True, language_level=2)

from input.core.CythonGenomeElement import CythonGenomeElement
from input.core.CythonGenomeElementSource import CythonGenomeElementSource

class BedGraphGenomeElementSource(CythonGenomeElementSource):
    _VERSION = '1.5'
    FILE_SUFFIXES = ['bedgraph']
    FILE_FORMAT_NAME = 'bedGraph'

    def __init__(self, fn, *args, **kwArgs):
        CythonGenomeElementSource.__init__(self, fn, *args, **kwArgs)

        f = open(fn)
        trackDef = f.readline()
        if trackDef.startswith('track type=bedGraph'):
            numHeaderLines = 1
        else:
            numHeaderLines = 0

        headerLine = f.readline()
        while headerLine.startswith('#'):
            numHeaderLines += 1
            headerLine = f.readline()

        self._numHeaderLines = numHeaderLines

    def _next(self, line):
        cols = line.split('\t')

        ge = CythonGenomeElement(self._genome)
        ge.chr = self._checkValidChr(cols[0])
        ge.start = int(cols[1])
        ge.end = int(cols[2])
        self._parseVal(ge, cols[3])

        return ge

    def _parseVal(self, ge, valStr):
        ge.val = numpy.float(self._handleNan(valStr))

class BedGraphTargetControlGenomeElementSource(BedGraphGenomeElementSource):
    _VERSION = '1.6'
    FILE_SUFFIXES = ['targetcontrol.bedgraph']
    FILE_FORMAT_NAME = 'target/control bedGraph'


    def _parseVal(self, ge, valStr):
        if self._handleNan(valStr) == 'nan':
            ge.val = BINARY_MISSING_VAL
        elif valStr == '0':
            ge.val = False
        elif valStr == '1':
            ge.val = True
        else:
            raise InvalidFormatError('Could not parse value: ' + valStr + ' as target/control.')

    def getValDataType(self):
        return 'int8'