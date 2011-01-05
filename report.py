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

    opts.signoff = {}
    for csvfile in opts.signoff_fns:
        try:
            csvdict = csv.DictReader(CommentedFile(open(csvfile, "rb")))
            create_library_xref(csvdict, opts.signoff)
        except IOError, e:
            pass # dont care if file doesnt exist


def add_cli_options(parser):
    group = OptionGroup(parser, "Scan control")
    parser.add_option("-d", "--database-directory", action="store", dest="database_dir", help="specify input directory", default=None)
    parser.add_option("-s", "--signoff-file", action="append", dest="signoff_fns", help="specify the signoff file", default=[])
    parser.add_option_group(group)

    group = OptionGroup(parser, "General Options")
    parser.add_option_group(group)


decorate(traceLog())
def connect(opts):
    moduleLogVerbose.info("Connecting to db at %s" % opts.dbpath)
    sqlobject.sqlhub.processConnection = sqlobject.connectionForURI('sqlite://%s' % opts.dbpath)

decorate(traceLog())
def tags_matching(fileobj, tagname):
    for t in fileobj.tags:
        if t.tagname == tagname:
            yield t

decorate(traceLog())
def tags_matching_any(fileobj, taglist):
    for t in fileobj.tags:
        if t.tagname in taglist:
            yield t

decorate(traceLog())
def get_license_soname(filedata, soname):
    for fd in soname.needed_by:
        pass
        #return fd.
    return "NOT_FOUND"

def main():
    parser = basic_cli.get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    add_cli_options(parser)
    opts, args = basic_cli.command_parse(parser, validate_fn=validate_args)
    # DO NOT LOG BEFORE THIS CALL:
    basic_cli.setupLogging(opts)

    moduleLogVerbose.debug("Connecting to database.")
    connect(opts)

    for fname in license_db.Filedata.select():
        moduleLog.warning("%s" % fname.basename)
        for soname in fname.dt_needed:
            moduleLog.warning("\t[%s] %s" % (get_license_soname(fname, soname), soname.soname))

    # Print out collected error list global global_error_list
    if len(global_error_list.values()):
        sys.stderr.write("Here are all the problems I found:\n")
        keys = global_error_list.keys()
        keys.sort()
        for err in keys:
            sys.stderr.write(global_error_list[err] + "\n")


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

if __name__ == "__main__":
    try:
        sys.exit(main())
    except basic_cli.CLIError, e:
        print "Problem parsing CLI args: %s" % e


