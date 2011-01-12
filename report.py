#!/usr/bin/python
# vim:tw=0:expandtab:autoindent:tabstop=4:shiftwidth=4:filetype=python:

"""%prog [options]
    program which reads output from readelf dumps and prints a link tree
"""

import csv
import sys
import os
import re
import traceback
import subprocess
import copy
import shutil
import fnmatch
import logging
import sqlobject
import multiprocessing
import Queue
import rpm
import time
from optparse import OptionGroup
from trace_decorator import decorate, traceLog, getLog

# our stuff
import basic_cli
import license_db
import gather

__VERSION__="1.0"

global global_error_list
global_error_list = {}

moduleLog = getLog()
moduleLogVerbose = getLog(prefix="verbose.")

class PrereqError(Exception): pass

def validate_args(opts, args):
    #if opts.inputdir: opts.inputdir = os.path.realpath(opts.inputdir)
    if opts.database_dir: opts.database_dir = os.path.realpath(opts.database_dir)
    if opts.database_dir is None:
        raise basic_cli.CLIError("Database directory is required.")

    opts.dbpath = os.path.join(opts.database_dir, "sqlite.db")
    if not os.path.exists(opts.dbpath):
        raise basic_cli.CLIError("DB doesnt exist.")


def add_cli_options(parser):
    group = OptionGroup(parser, "General Options")
    parser.add_option("-d", "--database-directory", action="store", dest="database_dir", help="specify input directory", default=None)
    parser.add_option("--text-output", action="store_const", const="text", dest="output_fmt", help="specify text output format (default)", default="text")
    parser.add_option("--html-output", action="store_const", const="html", dest="output_fmt", help="specify html output format")
    parser.add_option_group(group)

    #group = OptionGroup(parser, "General Options")
    #parser.add_option_group(group)


decorate(traceLog())
def connect(opts):
    moduleLogVerbose.info("Connecting to db at %s" % opts.dbpath)
    sqlobject.sqlhub.processConnection = sqlobject.connectionForURI('sqlite://%s' % opts.dbpath)

def main():
    parser = basic_cli.get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    add_cli_options(parser)
    opts, args = basic_cli.command_parse(parser, validate_fn=validate_args)
    # DO NOT LOG BEFORE THIS CALL:
    basic_cli.setupLogging(opts)

    moduleLogVerbose.debug("Connecting to database.")
    connect(opts)

    format_strings = { "html": {
            "prefix": "<html><head></head><body><ol>",
            "suffix": "</ol></body>",
            "increase_level": "<ol>",
            "decrease_level": "</ol>",
            "fmt_incompatible": "<li><font color='darkred'>{basename}    **(({license}))</font></li>",
            "fmt_culprit":      "<li><font color='red'>{basename}    -->(({license}))</font></li>",
            "fmt_ok":           "<li>{basename}    [{license}]</li>"
        },
        "text": {
            "prefix": None,
            "suffix": None,
            "increase_level": None,
            "decrease_level": None,
            "fmt_incompatible": "{level}{basename}\t**(({license}))",
            "fmt_culprit":      "{level}{basename}\t-->(({license}))",
            "fmt_ok":           "{level}{basename}\t    [{license}]",
            "post_per_exe": "",
        }}

    str_list = format_strings[opts.output_fmt]

    def log_if_not_empty(s, *args, **kargs):
        msg = str_list.get(s, None)
        if msg is not None:
            moduleLog.warning(msg.format(*args, **kargs))

    log_if_not_empty("prefix")
    for fname in license_db.Filedata.select():
        level = 0
        log_if_not_empty("pre_per_exe")
        for info in reversed(list(license_db.iter_over_dt_needed(opts, fname))):
            interpolate = {}
            interpolate["basename"] = info["filedata"].basename
            interpolate["license"]  = license_db.get_license(info["filedata"])
            interpolate["level"]  = "    "*info["level"]

            while info["level"] > level:
                level = level + 1
                log_if_not_empty("increase_level")

            while info["level"] < level:
                level = level - 1
                log_if_not_empty("decrease_level")

            if not info["compatible"]:
                fmtstring = "fmt_incompatible"
            elif info["culprit"]:
                fmtstring = "fmt_culprit"
            else:
                fmtstring = "fmt_ok"

            log_if_not_empty(fmtstring, **interpolate)
        while level > 0:
            level = level - 1
            log_if_not_empty("decrease_level")
        log_if_not_empty("post_per_exe")
    log_if_not_empty("suffix")

    sqlobject.sqlhub.processConnection.close()

    # Print out collected error list global global_error_list
    if len(global_error_list.values()):
        sys.stderr.write("Here are all the problems I found:\n")
        keys = global_error_list.keys()
        keys.sort()
        for err in keys:
            sys.stderr.write(global_error_list[err] + "\n")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except basic_cli.CLIError, e:
        print "Problem parsing CLI args: %s" % e


