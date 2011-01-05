import sqlobject
import os
import inspect
from trace_decorator import decorate, traceLog, getLog

moduleLog = getLog()
moduleLogVerbose = getLog(prefix="verbose.")

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


# centralized place to set common sqlmeta class details
class myMeta(sqlobject.sqlmeta):
    lazyUpdate = False

class Filedata(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    basename = sqlobject.StringCol()
    full_path = sqlobject.StringCol()
    dt_needed = sqlobject.MultipleJoin('LibraryRef')
    licenses = sqlobject.MultipleJoin('License')
    tags = sqlobject.MultipleJoin('Tag')

class LibraryRef(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    filedata = sqlobject.ForeignKey('Filedata')
    soname = sqlobject.StringCol()

class License(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    filedata = sqlobject.ForeignKey('Filedata')
    license = sqlobject.StringCol()
    license_type = sqlobject.StringCol()

class Tag(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    filedata = sqlobject.ForeignKey('Filedata')
    tagname = sqlobject.StringCol()
    tagvalue = sqlobject.StringCol()

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


