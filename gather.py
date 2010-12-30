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
import inspect
from optparse import OptionGroup
from trace_decorator import decorate, traceLog, getLog

# our stuff
import basic_cli

__VERSION__="1.0"

global global_error_list
global_error_list = {}

moduleLog = getLog()
moduleLogVerbose = getLog(prefix="verbose.")

class PrereqError(Exception): pass

def validate_args(opts, args):
    #if opts.inputdir: opts.inputdir = os.path.realpath(opts.inputdir)
    if opts.outputdir: opts.outputdir = os.path.realpath(opts.outputdir)
    if opts.inputdir is None:
        raise basic_cli.CLIError("Input directory is required when gathering data.")
    if opts.outputdir is None:
        raise basic_cli.CLIError("Output directory is required.")

    opts.dbpath = os.path.join(opts.outputdir, "sqlite.db")

    opts.signoff = {}
    for csvfile in opts.signoff_fns:
        try:
            csvdict = csv.DictReader(CommentedFile(open(csvfile, "rb")))
            create_library_xref(csvdict, opts.signoff)
        except IOError, e:
            pass # dont care if file doesnt exist


def add_cli_options(parser):
    group = OptionGroup(parser, "Scan control")
    parser.add_option("-i", "--input-directory", action="store", dest="inputdir", help="specify input directory", default=None)
    parser.add_option("-o", "--output-directory", action="store", dest="outputdir", help="specify output directory", default=None)
    parser.add_option("-s", "--signoff-file", action="append", dest="signoff_fns", help="specify the signoff file", default=[])
    parser.add_option_group(group)

    group = OptionGroup(parser, "General Options")
    parser.add_option("--initdb", action="store_true", dest="initdb", help="Initialize storage Database", default=False)
    parser.add_option_group(group)

    group = OptionGroup(parser, "Replace CMD defaults")
    group.add_option("--cmd-file", action="store", dest="cmd_file", help="specify file command", default="file")
    group.add_option("--cmd-find", action="store", dest="cmd_find", help="specify find command", default="find")
    group.add_option("--cmd-rpm", action="store", dest="cmd_rpm", help="specify rpm command", default="rpm")
    group.add_option("--cmd-objdump", action="store", dest="cmd_objdump", help="specify objdump command", default="objdump")
    group.add_option("--cmd-nm", action="store", dest="cmd_nm", help="specify nm command", default="nm")
    group.add_option("--cmd-scanelf", action="store", dest="cmd_scanelf", help="specify scanelf command", default="scanelf")
    parser.add_option_group(group)

def check_prereqs(opts):
    for cmd in [opts.cmd_find, opts.cmd_file, opts.cmd_rpm, opts.cmd_nm, opts.cmd_objdump, opts.cmd_scanelf]:
        ret = redirect_call(['which', cmd], stdout_fn="/dev/null", stderr_fn="/dev/null", stdin_fn="/dev/null",)
        if ret != 0:
            raise PrereqError( "COULD NOT FIND PREREQUISITE: %s" % cmd )


decorate(traceLog())
def connect(opts):
    if not os.path.exists(opts.dbpath):
        opts.initdb = True

    if opts.initdb:
        if os.path.exists(opts.dbpath):
            moduleLogVerbose.info("unlinking old db: %s" % opts.dbpath)
            os.unlink(opts.dbpath)

        if os.path.dirname(opts.dbpath) and not os.path.exists(os.path.dirname(opts.dbpath)):
            os.makedirs(os.path.dirname(opts.dbpath))

    moduleLogVerbose.info("Connecting to db at %s" % opts.dbpath)
    sqlobject.sqlhub.processConnection = sqlobject.connectionForURI('sqlite://%s' % opts.dbpath)

    if opts.initdb:
        createTables()

def gather_data(opts, dirpath, filename):
    File(full_path=os.path.join(dirpath, filename), filename=filename)


def main(): 
    parser = basic_cli.get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    add_cli_options(parser)
    opts, args = basic_cli.command_parse(parser, validate_fn=validate_args)
    # DO NOT LOG BEFORE THIS CALL:
    basic_cli.setupLogging(opts)

    check_prereqs(opts)
    connect(opts)

    # Make Cache, gather data
    if not os.path.exists(opts.outputdir):
        os.makedirs(opts.outputdir)

    for dirpath, dirnames, filenames in os.walk(opts.inputdir):
        for filename in filenames:
            outpath = os.path.join(opts.outputdir, dirpath)
            if not os.path.exists(outpath):
                os.makedirs(outpath)
            gather_data(opts, dirpath, filename)

    #print_license_report(opts)

    # Print out collected error list global global_error_list
    if len(global_error_list.values()):
        sys.stderr.write("Here are all the problems I found:\n")
        keys = global_error_list.keys()
        keys.sort()
        for err in keys:
            sys.stderr.write(global_error_list[err] + "\n")


# centralized place to set common sqlmeta class details
class myMeta(sqlobject.sqlmeta):
    lazyUpdate = False

class File(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    full_path = sqlobject.StringCol()
    filename = sqlobject.StringCol()
    tags = sqlobject.MultipleJoin('Tags')

class Tags(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    full_path = sqlobject.ForeignKey('File')
    tag = sqlobject.StringCol()
    info = sqlobject.StringCol()

def createTables():
    # fancy pants way to grab all classes in this file
    # that are descendents of SQLObject and run .createTable() on them.
    toCreate = [ value for key, value in globals().items()
            if     inspect.isclass(value)
               and value.__module__==__name__
               and issubclass(value, sqlobject.SQLObject)
         ]

    for clas in toCreate:
        clas.createTable(ifNotExists=True, createJoinTables=False)


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

def redirect_call(*args, **kwargs):
    close_stdout=0
    close_stderr=0
    close_stdin=0

    if kwargs.get("stdout_fn"):
        kwargs["stdout"] = open(kwargs.get("stdout_fn"), "w+")
        del(kwargs["stdout_fn"])
        close_stdout=1

    if kwargs.get("stderr_fn"):
        kwargs["stderr"] = open(kwargs.get("stderr_fn"), "w+")
        del(kwargs["stderr_fn"])
        close_stderr=1

    if kwargs.get("stdin_fn"):
        kwargs["stdin"] = open(kwargs.get("stdin_fn"), "r")
        del(kwargs["stdin_fn"])
        close_stdin=1

    ret = subprocess.call(*args, **kwargs)

    if close_stdout:
        kwargs["stdout"].close()
    if close_stderr:
        kwargs["stderr"].close()
    if close_stdin:
        kwargs["stdin"].close()

    return ret


if __name__ == "__main__":
    try:
        sys.exit(main())
    except basic_cli.CLIError, e:
        print "Problem parsing CLI args: %s" % e


