#!/usr/bin/python

import os
import sqlobject
from optparse import OptionGroup

import pygtk
pygtk.require("2.0")
import gtk

# our stuff
from trace_decorator import decorate, traceLog, getLog
import basic_cli
import license_db
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

class QueryWrapper(object):
    def __init__(self, query):
        self.q = query
        self.iter = iter(self.q)
        self.current = self.iter.next()

    def next(self):
        try:
            self.current = self.iter.next()
        except StopIteration:
            self.current = None
            raise
        return self.current

    def __getattr__(self, name):
        return getattr(self.iter, name)

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
        p = path
        c = q.count()
        return {"query":q, "path": p, "count": c}

    decorate(traceLog())
    def on_get_path(self, rowref):
        return rowref["path"]

    decorate(traceLog())
    def on_get_value(self, rowref, column):
        q = rowref["query"]
        p = rowref["path"][0]
        filedata = q[p:p+1].getOne()
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
        rowref["path"] = (rowref["path"][0]+1,)
        if rowref["path"][0] < rowref["count"]:
            return rowref
        

    decorate(traceLog())
    def on_iter_children(self, rowref):
        if rowref:
            return None
        return self.on_get_iter((0,))

    decorate(traceLog())
    def on_iter_has_child(self, rowref):
        return False

    decorate(traceLog())
    def on_iter_n_children(self, rowref):
        if rowref:
            return 0
        return self.fd.select().count()

    decorate(traceLog())
    def on_iter_nth_child(self, parent, n):
        if parent:
            return None
        return self.on_get_iter( (n,) )
        
        
    decorate(traceLog())
    def on_iter_parent(self, rowref):
        return None


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
