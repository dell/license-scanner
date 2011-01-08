#!/usr/bin/python
# vim:tw=0:expandtab:autoindent:tabstop=4:shiftwidth=4:filetype=python:
"""%prog [options]
    This is the basic_cli module which has some helper functions to make writing cli progs easier. If you run it from the CLI as a program, it runs in unit test mode.
"""

import csv
import sys
import logging
import logging.config
import ConfigParser
from optparse import OptionParser, OptionGroup
from trace_decorator import decorate, traceLog, getLog

__VERSION__="1.0"

moduleLog = getLog()
moduleLogVerbose = getLog(prefix="verbose.")

class CLIError(Exception): pass

def get_basic_parser(usage=None, version=None):
    kwargs = {}
    if usage is not None:
        kwargs["usage"] = usage
    if version is not None:
        kwargs["version"] = version
    parser = OptionParser(**kwargs)
    parser.add_option("-c", "--config-file", action="store", dest="configfile", help="specify configuration file", default=None)

    group = OptionGroup(parser, "Verbosity")
    group.add_option("-q", "--quiet", action="store_const", const=0, dest="verbosity", help="Silence all non-critical program output", default=1)
    group.add_option("-v", "--verbose", action="count", dest="verbosity", help="Increase program verbosity")
    group.add_option("-t", "--trace", action="store_true", dest="trace", help="Globally enable function tracing", default=False)
    group.add_option("--module-trace", action="append", dest="tracemodules", help="Enable function tracing only for specified modules", default=[])
    parser.add_option_group(group)

    group = OptionGroup(parser, "Config Inputs")
    parser.add_option("--signoff-file", action="append", dest="signoff_fns", help="File with license signoffs", default=[])
    parser.add_option("--license-compat-file", action="append", dest="license_compat_fns", help="File with license compatibility information", default=[])
    parser.add_option_group(group)

    return parser

def command_parse(parser=None, validate_fn=None):
    if parser is None:
        parser = get_basic_parser()
    (opts, args) = parser.parse_args()

    if opts.configfile is not None:
        opts.conf = ConfigParser.ConfigParser()
        opts.conf.read(opts.configfile)

    __validate_args(opts, args)
    if validate_fn is not None:
        validate_fn(opts, args)

    return (opts, args)


# only used for example purposes and unit testing
def __validate_args(opts, args):
    # do stuff here to validate that the options given are valid
    opts.signoff = {}
    for csvfile in opts.signoff_fns:
        try:
            csvdict = csv.DictReader(CommentedFile(open(csvfile, "rb")))
            create_library_xref(csvdict, opts.signoff)
        except IOError, e:
            pass # dont care if file doesnt exist

    opts.license_compat = {}
    for csvfile in opts.license_compat_fns:
        try:
            csvdict = csv.DictReader(CommentedFile(open(csvfile, "rb")))
            create_library_xref(csvdict, opts.license_compat)
        except IOError, e:
            pass # dont care if file doesnt exist



class CommentedFile:
    def __init__(self, f, commentstring="#"):
        self.f = f
        self.commentstring = commentstring

    def next(self):
        line = self.f.next()
        while (line[0] in self.commentstring) or line == "":
            line = self.f.next()
        return line

    def __iter__(self):
        return self

def create_license_compat_xref(csvdict, xref):
    for line in csvdict:
        try:
            d = xref.get(line["LICENSE"], [])
            d.append(line["COMPAT_LICENSE"])
            xref[line["LICENSE"]] = d
        except Exception, e:
            sys.stderr.write("="*79 + "\n")
            sys.stderr.write("Ignoring parsing error in CSV file:")
            traceback.print_exc()
            sys.stderr.write("="*79 + "\n")
    return xref

def create_library_xref(csvdict, xref):
    for line in csvdict:
        try:
            d = xref.get(line["LIBRARY"], {})
            d[line["APPLICABLE"]] = line
            xref[line["LIBRARY"]] = d
        except Exception, e:
            sys.stderr.write("="*79 + "\n")
            sys.stderr.write("Ignoring parsing error in CSV file:")
            traceback.print_exc()
            sys.stderr.write("="*79 + "\n")
    return xref



# only used for unit testing
decorate(traceLog())
def __activate_warp(warp_speed=100):
    moduleLog.debug(         "moduleLog         debug")
    moduleLog.info(          "moduleLog         info")
    moduleLog.warning(       "moduleLog         warning")
    getLog("trace.warp").info("trace.warp info msg")
    moduleLog.warning("Activating Warp Drive! Speed=%s" % warp_speed) 
    moduleLogVerbose.debug(  "moduleLog verbose debug")
    moduleLogVerbose.info(   "moduleLog verbose info")
    moduleLogVerbose.warning("moduleLog verbose warning")

# unit test
# basically just cut and paste all this into your code, replacing the "__" functions
def main(): 
    parser = get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    group = OptionGroup(parser, "Warp Drive Control")
    group.add_option("--activate_warp", action="count", dest="warp", default=4, help="Activate warp drive")
    group.add_option("--deactivate_warp", action="store_const", const=0, dest="warp", help="Disable warp drive")
    parser.add_option_group(group)
    opts, args = command_parse(parser, validate_fn=__validate_args)
    # do no logging calls before this line
    setupLogging(opts)

    __activate_warp(opts.warp)


# A null sink for loggers that may not be turned on
class NullHandler(logging.Handler):
    def emit(self, record):
            pass

# for the *default* configuration, you can use logging like the following:
#   moduleLog.debug("message")          # only shown with verbosity >= 3 (-vv)
#   moduleLog.info("message")           # shown by default, but not if quiet
#   moduleLog.warning("message")        # shown by default
#   moduleLogVerbose.debug("message")   # only shown with verbosity >= 3 (-vv)
#   moduleLogVerbose.info("message")    # shown with verbosity >= 2 (-v)
#   moduleLogVerbose.warning("message") # shown with verbosity >= 2 (-v)
# 
# of course, if the user specifies a config file, then this may change
def setupLogging(opts):
    # set up logging
    if opts.configfile:
        logging.config.fileConfig(opts.configfile)
    else:
        logging.basicConfig( format="%(message)s", stream=sys.stdout, level=logging.NOTSET )
        for hdlr in logging.getLogger().handlers:
            hdlr.setLevel(logging.INFO)

    root_log    = logging.getLogger()
    verbose_log = logging.getLogger("verbose")

    if opts.verbosity >= 0:
        root_log.setLevel(logging.WARNING)
        verbose_log.propagate = 0
        verbose_log.addHandler(NullHandler()) # in case we are not verbose, add a null sink
    if opts.verbosity >= 1:
        root_log.setLevel(logging.INFO)
    if opts.verbosity >= 2:
        verbose_log.propagate = 1
    if opts.verbosity >= 3:
        root_log.setLevel(logging.NOTSET)
        for hdlr in root_log.handlers:
            hdlr.setLevel(logging.DEBUG)

    stderrStream = logging.StreamHandler()
    stderrStream.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(message)s")
    stderrStream.setFormatter(formatter)

    trace_log = logging.getLogger("trace")
    trace_log.propagate = 0
    trace_log.addHandler(NullHandler()) # in case we are not tracing, add a null sink
    if opts.trace:
        trace_log.setLevel(logging.DEBUG)
        trace_log.addHandler(stderrStream)

    for mod in opts.tracemodules:
        trace_log   = logging.getLogger("trace.%s" % mod)
        trace_log.setLevel(logging.DEBUG)
        if not opts.trace:
            trace_log.addHandler(stderrStream)



if __name__ == "__main__":
    try:
        sys.exit(main())
    except CLIError, e:
        print "Problem parsing CLI args: %s" % e


