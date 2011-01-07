#!/usr/bin/python

import os
import sqlobject
import copy
from optparse import OptionGroup

import pygtk
pygtk.require("2.0")
import gtk

# our stuff
from trace_decorator import decorate, traceLog, getLog
import basic_cli
import license_db
import gather
import report

__VERSION__="1.0"

global global_error_list
global_error_list = {}

moduleLog = getLog()
moduleLogVerbose = getLog(prefix="verbose.")

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

class MyTreeModel(gtk.GenericTreeModel):
                    # File, License, Signoff, Comment
    _column_types = [str, str, str, str]
    _model_data = [('row %i'%n, 'string %i'%n, "string %i"%n, "string %i"%n) for n in range(10)]

    def __init__(self, *args, **kargs):
        gtk.GenericTreeModel.__init__(self)
        self.fd = license_db.Filedata 

    decorate(traceLog())
    def on_get_flags(self):
        return 0
        #return gtk.TREE_MODEL_LIST_ONLY | gtk.TREE_MODEL_ITERS_PERSIST

    decorate(traceLog())
    def on_get_n_columns(self):
        return len(self._column_types)

    decorate(traceLog())
    def on_get_column_type(self, index):
        return self._column_types[index]

    decorate(traceLog())
    def on_get_iter(self, path):
        q = self.fd.select()
        retval = {"query": q, "path": path, "count": q.count()}
        pathcopy = copy.copy(path)
        # iterate while there are children and there are path elements left
        while retval["count"] and len(pathcopy)>1:
            # progressively chop off parts of the path to traverse down
            p = pathcopy[0]
            pathcopy = pathcopy[1:]
            try:
                row = q[p:p+1].getOne()
            except sqlobject.main.SQLObjectNotFound, e:
                break

            # set the query to the list of children
            from license_db import DtNeededList
            q = DtNeededList.select( DtNeededList.q.Filedata == row.id ).throughTo.Soname.throughTo.has_soname
            retval = {"query": q, "path": path, "count": q.count()}

        if retval is not None and retval["count"]:
            return retval
        else:
            return None

    decorate(traceLog())
    def on_get_path(self, rowref):
        return rowref["path"]

    decorate(traceLog())
    def on_get_value(self, rowref, column):
        q = rowref["query"]
        p = rowref["path"][-1]
        try:
            filedata = q[p:p+1].getOne()
        except sqlobject.main.SQLObjectNotFound, e:
            #should never happen
            return "nonexistent row: %s" % repr(rowref["path"])

        if column == 0:
            return filedata.basename
        elif column == 1:
            return report.get_license(filedata)
        elif column == 2:
            try:
                return report.tags_matching(filedata, "SIGNOFF").next()
            except StopIteration, e:
                return ""
        elif column == 3:
            try:
                return report.tags_matching(filedata, "COMMENT").next()
            except StopIteration, e:
                return ""

    decorate(traceLog())
    def on_iter_next(self, rowref):
        # increment last element
        rowref["path"] = rowref["path"][:-1] + (rowref["path"][-1]+1,)
        if rowref["path"][-1] < rowref["count"]:
            return rowref

    decorate(traceLog())
    def on_iter_children(self, rowref):
        # degenerate case:
        if not rowref:
            return self.on_get_iter((0,))

        return self.on_get_iter( rowref["path"] + (0,) )

    decorate(traceLog())
    def on_iter_has_child(self, rowref):
        rowref = self.on_get_iter( rowref["path"] + (0,) )
        if rowref is not None:
            return True
        return False

    decorate(traceLog())
    def on_iter_n_children(self, rowref):
        rowref = self.on_get_iter( rowref["path"] + (0,) )
        return rowref["count"]

    decorate(traceLog())
    def on_iter_nth_child(self, parent, n):
        # degenerate case:
        if not parent:
            return self.on_get_iter( (n,) )

        return self.on_get_iter( parent["path"] + (n,) )
        
        
    decorate(traceLog())
    def on_iter_parent(self, rowref):
        parent = rowref["path"][:-1]
        if not parent:
            parent = (0,)
        return self.on_get_iter(parent)


class LicenseScanApp(object):       
    def __init__(self):
        builder = gtk.Builder()
        builder.add_from_file("gui.glade")
        builder.connect_signals(self)

        # get main objects
        self.window = builder.get_object("window")
        self.statusbar = builder.get_object("treestore")
        self.treestore = builder.get_object("treestore")
        self.treeview = builder.get_object("treeview")

        # 
        self.listmodel = MyTreeModel()
        self.treeview.set_model(model=self.listmodel)

        self.window.show()

    def file_quit(self, widget, data=None):
        gtk.main_quit()

    def on_window_destroy(self, widget, data=None):
        gtk.main_quit()

if __name__ == "__main__":
    parser = basic_cli.get_basic_parser(usage=__doc__, version="%prog " + __VERSION__)
    add_cli_options(parser)
    opts, args = basic_cli.command_parse(parser, validate_fn=validate_args)
    # DO NOT LOG BEFORE THIS CALL:
    basic_cli.setupLogging(opts)

    moduleLogVerbose.debug("Connecting to database.")
    connect(opts)

    app = LicenseScanApp()

    # we'll add some test data now - 4 rows with 3 child rows each
    for parent in range(4):
        piter = app.treestore.append(None, ['parent %i' % parent, "license", "signoff", "comment"])
        for child in range(3):
            app.treestore.append(piter, ['child %i of parent %i' %
                                          (child, parent), "license", "signoff", "comment"])

    gtk.main()
