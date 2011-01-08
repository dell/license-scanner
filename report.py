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
    group = OptionGroup(parser, "Scan control")
    parser.add_option("-d", "--database-directory", action="store", dest="database_dir", help="specify input directory", default=None)
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
def get_license(filedata, preferred=None):
    if preferred is None: preferred = ["MANUAL", "RPM" ]
    for pref in preferred:
        for l in filedata.license:
            if l.license_type == pref:
                return l.license
    # if we get here, there are no "preferred" licenses,
    # so just return the first one
    for l in filedata.license:
        return l.license
    return "NOT_FOUND_FD"

decorate(traceLog())
def get_license_soname(soname, preferred=None):
    # try checking things with actual SONAME first
    for fd in soname.needed_by:
        lic = get_license(fd, preferred)
        if lic != "NOT_FOUND_FD":
            return lic

    # then match just basename
    from license_db import Filedata
    moduleLogVerbose.debug("query by soname failed for %s." % soname.soname)
    for fd in Filedata.select( Filedata.q.basename == soname.soname ):
        moduleLogVerbose.debug("try to get license by %s" % fd.full_path)
        lic = get_license(fd, preferred)
        if lic != "NOT_FOUND_FD":
            return lic

    return "NOT_FOUND_LIB"

def license_is_compatible(opts, lic1, lic2):
    if lic1 == lic2:
        return True
    if lic2 in opts.license_compat.get(lic1, []):
        return True
    return False


def get_stuff(opts, filedata, myfault=0):
    from license_db import DtNeededList
    q = DtNeededList.select( DtNeededList.q.Filedata == filedata.id ).throughTo.Soname.throughTo.has_soname
    retlist = []
    compatible = True

    for soname in q:
        culprit = False
        # check license compatibility of all direct, first-level children
        if not license_is_compatible(opts, get_license(filedata), get_license(soname)):
            compatible = False
            culprit = True
        # now flip our bit to false if any of our children has incompatibilities
        for deps in get_stuff(opts, soname, culprit):
            if not deps["compatible"]:
                compatible = False

            deps["level"] = deps["level"] + 1
            retlist.append(deps)

    yield {
        "level": 0,
        "culprit": myfault,
        "compatible": compatible,
        "filedata": filedata,
        }
    for i in retlist:
        yield i

def main():
    parser = basic_cli.get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    add_cli_options(parser)
    opts, args = basic_cli.command_parse(parser, validate_fn=validate_args)
    # DO NOT LOG BEFORE THIS CALL:
    basic_cli.setupLogging(opts)

    moduleLogVerbose.debug("Connecting to database.")
    connect(opts)

    for fname in license_db.Filedata.select():
        for info in get_stuff(opts, fname):
            compat = "%s[%s] %s"
            if not info["compatible"]:
                compat = "%s**((%s)) %s"
            elif info["culprit"]:
                compat = "%s-->((%s)) %s"

            moduleLog.warning(compat % ("    "*info["level"], get_license(info["filedata"]), info["filedata"].basename))

#    for fname in license_db.Filedata.select():
#        moduleLog.warning("%s" % fname.basename)
#        for soname in fname.dt_needed:
#            moduleLog.warning("\t[%s] %s" % (get_license_soname(soname), soname.soname))

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


