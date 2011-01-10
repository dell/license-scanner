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

class MyTreeModel(gtk.GenericTreeModel):
                    # File, License, Signoff, Comment, STOCK_ID
    _column_types = [str, str, str, str, str ]
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
    def get_filedata_from_rowref_iter(self, rowref):
        q = rowref["query"]
        p = rowref["path"][-1]
        try:
            return q[p:p+1].getOne()
        except sqlobject.main.SQLObjectNotFound, e:
            #should never happen
            return None

    decorate(traceLog())
    def on_get_value(self, rowref, column):
        filedata = self.get_filedata_from_rowref_iter(rowref)
        if filedata is None:
            return "nonexistent row: %s" % repr(rowref["path"])

        if column == 0:
            return filedata.basename
        elif column == 1:
            return license_db.get_license(filedata)
        elif column == 2:
            try:
                return license_db.tags_matching(filedata, "SIGNOFF").next()
            except StopIteration, e:
                return ""
        elif column == 3:
            try:
                return license_db.tags_matching(filedata, "COMMENT").next()
            except StopIteration, e:
                return ""
        elif column == 4:
            # iter, but will only ever return one record
            for info in license_db.iter_over_dt_needed(opts, filedata, get_all=False, iter_direction=license_db.iter_bottomup, break_on_incompatible=1):
                if info["compatible"]:
                    return gtk.STOCK_YES
                return gtk.STOCK_NO

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
    def __init__(self, opts):
        # save config data/cli opts
        self.opts = opts

        # initialize from glade
        builder = gtk.Builder()
        builder.add_from_file("gui.glade")
        builder.connect_signals(self)

        # get main objects
        self.window = builder.get_object("window")
        self.statusbar = builder.get_object("treestore")
        self.treestore = builder.get_object("treestore")
        self.treeview = builder.get_object("treeview")
        self.popup    = builder.get_object("popup_menu")

        # Set up model
        self.listmodel = MyTreeModel()
        self.treeview.set_model(model=self.listmodel)

        # actions
        self.global_actions = builder.get_object("global_actions")
        self.action_quit = builder.get_object("action_quit")
        self.action_save = builder.get_object("action_save")
        for action in (self.action_quit, self.action_save):
            self.global_actions.add_action(action)

        self.window.show()

    def add_license_compatibility_activate_cb(self, *args, **kargs):
        selection = self.treeview.get_selection()
        model, selected = selection.get_selected_rows()
        #print "args: %s  kargs: %s" % (repr(args), repr(kargs))
        for path in selected:
            print "add_license_compat: %s" % repr(path)
            rowref = model.on_get_iter(path)
            parent_path = path[:-1]
            parent_rowref = model.on_get_iter(parent_path)
            filedata = model.get_filedata_from_rowref_iter(rowref)
            parent_filedata = model.get_filedata_from_rowref_iter(parent_rowref)

            compat = self.opts.license_compat.get(license_db.get_license(parent_filedata), [])
            compat.append(license_db.get_license(filedata))
            self.opts.license_compat[license_db.get_license(parent_filedata)] = compat

    def on_treeview_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            time = event.time
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None and len(pthinfo[0]) > 1:
                path, col, cellx, celly = pthinfo
                print "PATH: %s" % repr(path)
                treeview.grab_focus()
                treeview.set_cursor( path, col, 0)
                self.popup.popup( None, None, None, event.button, time)
            return True

    def on_window_destroy(self, *args, **kargs):
        self.action_quit.activate()

    def on_action_quit_activate(self, *args, **kargs):
        gtk.main_quit()

    def on_action_save_activate(self, *args, **kargs):
        print "SAVE!"
        import csv
        fd = open("OUTFILE.csv", "wb+")
        fd.write('LICENSE,COMPAT_LICENSE\n')
        fd.flush()
        writer = csv.writer(fd, ("LICENSE", "COMPAT_LICENSE"))
        for lic, compat_licenses in self.opts.license_compat.items():
            for row in compat_licenses:
                writer.writerow((lic, row))
        fd.close()

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

    app = LicenseScanApp(opts)

    gtk.main()

    sqlobject.sqlhub.processConnection.close()
