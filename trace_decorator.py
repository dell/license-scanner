# vim:expandtab:autoindent:tabstop=4:shiftwidth=4:filetype=python:textwidth=0:
# License: GPL2 or later see COPYING
# Written by Michael Brown
# Copyright (C) 2007 Michael E Brown <mebrown@michaels-house.net>

import logging
import os
import string
import sys
import types

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

# use python-decoratortools if it is installed, otherwise use our own local
# copy. Imported this locally because it doesnt appear to be available on SUSE
# and the fedora RPM doesnt appear to compile cleanly on SUSE
try:
    from peak.util.decorators import rewrap, decorate
except ImportError:
    from _peak_util_decorators import rewrap, decorate

def makePrintable(s):
    printable = 1
    for ch in s:
        if ch not in string.printable:
            printable=0

    if printable:
        return s

    else:
        retstr=""
        i = 0
        for ch in s:
            i = i+1
            retstr = retstr + "0x%02x" % ord(ch)
        return retstr

# defaults to module verbose log
# does a late binding on log. Forwards all attributes to logger.
# works around problem where reconfiguring the logging module means loggers
# configured before reconfig dont output.
class getLog(object):
    def __init__(self, name=None, prefix="", *args, **kargs):
        if name is None:
            frame = sys._getframe(1)
            name = frame.f_globals["__name__"]

        self.name = prefix + name

    def __getattr__(self, name):
        logger = logging.getLogger(self.name)
        return getattr(logger, name)

# emulates logic in logging module to ensure we only log
# messages that logger is enabled to produce.
def doLog(logger, level, *args, **kargs):
    if logger.manager.disable >= level:
        return
    if logger.isEnabledFor(level):
        try:
            logger.handle(logger.makeRecord(logger.name, level, *args, **kargs))
        except TypeError:
            del(kargs["func"])
            logger.handle(logger.makeRecord(logger.name, level, *args, **kargs))

def traceLog(log = None):
    def decorator(func):
        def trace(*args, **kw):
            # default to logger that was passed by module, but
            # can override by passing logger=foo as function parameter.
            # make sure this doesnt conflict with one of the parameters
            # you are expecting

            filename = os.path.normcase(func.func_code.co_filename)
            func_name = func.func_code.co_name
            lineno = func.func_code.co_firstlineno

            l2 = kw.get('logger', log)
            if l2 is None:
                l2 = logging.getLogger("trace.%s" % func.__module__)
            if isinstance(l2, basestring):
                l2 = logging.getLogger(l2)

            message = "ENTER %s(" % func_name
            for arg in args:
                message = message + repr(arg) + ", "
            for k,v in kw.items():
                message = message + "%s=%s" % (k,repr(v))
            message = message + ")"

            frame = sys._getframe(2)
            doLog(l2, logging.INFO, os.path.normcase(frame.f_code.co_filename), frame.f_lineno, message, args=[], exc_info=None, func=frame.f_code.co_name)
            try:
                result = "Bad exception raised: Exception was not a derived class of 'Exception'"
                try:
                    result = func(*args, **kw)
                except (KeyboardInterrupt, Exception), e:
                    result = "EXCEPTION RAISED"
                    doLog(l2, logging.INFO, filename, lineno, "EXCEPTION: %s\n" % e, args=[], exc_info=sys.exc_info(), func=func_name)
                    raise
            finally:
                doLog(l2, logging.INFO, filename, lineno, "LEAVE %s --> %s\n" % (func_name, repr(result)), args=[], exc_info=None, func=func_name)

            return result
        return rewrap(func, trace)
    return decorator

# helper function so we can use back-compat format but not be ugly
def decorateAllFunctions(module, logger=None):
    methods = [ method for method in dir(module)
            if isinstance(getattr(module, method), types.FunctionType)
            ]
    for i in methods:
        setattr(module, i, traceLog(logger)(getattr(module,i)))

# unit tests...
if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING,
                    format='%(name)s %(levelname)s %(filename)s, %(funcName)s, Line: %(lineno)d:  %(message)s',)
    log = getLog("foobar.bubble")
    root = getLog(name="")
    log.setLevel(logging.WARNING)
    root.setLevel(logging.DEBUG)

    log.debug(" --> debug")
    log.error(" --> error")

    decorate(traceLog(log))
    def testFunc(arg1, arg2="default", *args, **kargs):
        return 42

    testFunc("hello", "world", logger=root)
    testFunc("happy", "joy", name="skippy")
    testFunc("hi")

    decorate(traceLog(root))
    def testFunc22():
        return testFunc("archie", "bunker")

    testFunc22()

    decorate(traceLog(root))
    def testGen():
        yield 1
        yield 2

    for i in testGen():
        log.debug("got: %s" % i)

    decorate(traceLog())
    def anotherFunc(*args):
        return testFunc(*args)

    anotherFunc("pretty")

    getLog()
