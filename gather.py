#!/usr/bin/python
# vim:tw=0:expandtab:autoindent:tabstop=4:shiftwidth=4:filetype=python:

"""%prog [options]
    program which reads output from readelf dumps and prints a link tree
"""

## TODO
# query DB before insert to prevent duplicates

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
    parser.add_option("-i", "--input-directory", action="append", dest="inputdir", help="specify input directory", default=[])
    parser.add_option("-o", "--output-directory", action="store", dest="outputdir", help="specify output directory", default=None)
    parser.add_option("-s", "--signoff-file", action="append", dest="signoff_fns", help="specify the signoff file", default=[])
    parser.add_option_group(group)

    group = OptionGroup(parser, "General Options")
    parser.add_option("--initdb", action="store_true", dest="initdb", help="Initialize storage Database", default=False)
    parser.add_option("--worker-threads", action="store", type="int", dest="worker_threads", help="Set number of worker threads to use", default=None) # None autodetects # of threads based on # of CPUs
    parser.add_option("--commit-interval", action="store", type="float", dest="commit_interval", help="Set database commit interval in seconds (0 to commit after every operation)", default=1.0) # None autodetects # of threads based on # of CPUs
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
def get_license(opts, full_path):
    ts = rpm.TransactionSet()
    headers = ts.dbMatch('basenames', full_path)
    for h in headers:
        return ("LICENSE_RPM", h['license'])

decorate(traceLog())
def gather_data(opts, dirpath, basename):
    moduleLog.info("Gather: %s" % os.path.join(dirpath,basename))
    full_path=os.path.join(dirpath, basename)
    data = {"full_path": full_path, "basename": basename}
    data["FILE"] = call_output( ["file", "-b", full_path] ).strip()
    data["DT_NEEDED"] = [ s for s in call_output([opts.cmd_scanelf, '-qF', '#F%n', full_path]).strip().split(",") if s ]

    license_data = get_license(opts, full_path)
    if license_data:
        data[license_data[0]] = license_data[1]

    return data

decorate(traceLog())
def insert_data(data):
    moduleLogVerbose.debug("Inserting: %s" % data["basename"])
    f = license_db.Filedata(full_path=data["full_path"], basename=data["basename"])

    for lib in data.get("DT_NEEDED", []):
        t = license_db.LibraryRef(filedata=f, soname=lib)

    for license in data.get("LICENSE_RPM", []):
        t = license_db.License(filedata=f, license=license, license_type="RPM")

    skip_list = ("LICENSE_RPM", "DT_NEEDED", "full_path", "basename")
    for key, value in data.items():
        if key in skip_list: continue
        t = license_db.Tag(filedata=f, tagname=key, tagvalue=value)

    moduleLogVerbose.info("Inserted : %s" % data["basename"])

def main():
    parser = basic_cli.get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    add_cli_options(parser)
    opts, args = basic_cli.command_parse(parser, validate_fn=validate_args)
    # DO NOT LOG BEFORE THIS CALL:
    basic_cli.setupLogging(opts)

    moduleLogVerbose.debug("Ensuring prerequisite programs are present.")
    check_prereqs(opts)

    moduleLogVerbose.debug("setting up multiprocessing worker pool.")
    task_queue = multiprocessing.Queue()
    done_queue = multiprocessing.Queue()
    def worker(input, output):
        for func, args, kwargs in iter(input.get, 'STOP'):
            result = func(*args, **kwargs)
            output.put(result)
    if opts.worker_threads is None: opts.worker_threads=1
    for i in range(opts.worker_threads):
            multiprocessing.Process(target=worker, args=(task_queue, done_queue)).start()

    moduleLogVerbose.debug("Connecting to database.")
    license_db.connect(opts)

    # Make Cache, gather data
    if not os.path.exists(opts.outputdir):
        moduleLog.warning("Output directory (%s) does not exist, creating." % opts.outputdir)
        os.makedirs(opts.outputdir)

    moduleLog.info("Starting gather run.")
    connection = sqlobject.sqlhub.processConnection
    trans = sqlobject.sqlhub.processConnection.transaction()
    sqlobject.sqlhub.processConnection = trans

    start_time = time.time()
    for dir_to_process in opts.inputdir:
        for dirpath, dirnames, filenames in os.walk(dir_to_process):
            for basename in filenames:
                task_queue.put((gather_data, [opts, dirpath, basename], {}))
                try:
                    insert_data(done_queue.get(block=False))
                except Queue.Empty, e:
                    pass

                if time.time() - start_time > opts.commit_interval:
                    moduleLogVerbose.info("==== Committing transaction ====================================")
                    start_time = time.time()
                    trans.commit()

    moduleLogVerbose.info("Stopping worker threads.")
    for i in range(opts.worker_threads):
        task_queue.put('STOP')

    while done_queue.qsize() or task_queue.qsize():
        insert_data(done_queue.get())

    moduleLog.info("Gather done")

    #print_license_report(opts)

    trans.commit()

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

decorate(traceLog())
def call_output(*args, **kwargs):
    null = open("/dev/null", "w")
    try:
        p = subprocess.Popen(*args, stderr=null, stdout=subprocess.PIPE, stdin=null, **kwargs)
        ret = p.communicate()
        moduleLogVerbose.debug("ret: %s" % (ret,))
    finally:
        null.close()
    return ret[0]

decorate(traceLog())
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


