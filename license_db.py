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
    basename  = sqlobject.StringCol()
    full_path = sqlobject.StringCol(alternateID=True)
    dt_needed = sqlobject.RelatedJoin('Soname', joinColumn='filedata_id', otherColumn='soname_id', intermediateTable='dt_needed_list', addRemoveName='DtNeeded')
    soname = sqlobject.RelatedJoin('Soname', joinColumn='filedata_id', otherColumn='soname_id', intermediateTable='soname_list', addRemoveName='Soname')
    license  = sqlobject.RelatedJoin('License', joinColumn='filedata_id', otherColumn='license_id', intermediateTable='filedata_license', addRemoveName='License')
    tags      = sqlobject.MultipleJoin('Tag')

# for ELF libraries with SONAME, this table will list the soname of the lib (by related join)
# for ELF libraries/executables, this table will list the DT_NEEDED entries (by related join)
class Soname(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    soname = sqlobject.StringCol(alternateID=True)
    needed_by = sqlobject.RelatedJoin('Filedata', otherColumn='filedata_id', joinColumn='soname_id', intermediateTable='dt_needed_list', addRemoveName='FileThatRequires')
    has_soname = sqlobject.RelatedJoin('Filedata', otherColumn='filedata_id', joinColumn='soname_id', intermediateTable='soname_list', addRemoveName='FileWithSoname')

class DtNeededList(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    Soname = sqlobject.ForeignKey('Soname', cascade=True)
    Filedata = sqlobject.ForeignKey('Filedata', cascade=True)

class SonameList(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    Soname = sqlobject.ForeignKey('Soname', cascade=True)
    Filedata = sqlobject.ForeignKey('Filedata', cascade=True)

class License(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    license = sqlobject.StringCol(alternateID=True)
    license_type = sqlobject.StringCol()
    filesWith  = sqlobject.RelatedJoin('License', otherColumn='filedata_id', joinColumn='license_id', intermediateTable='filedata_license', addRemoveName='FileWith')

class FiledataLicense(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    License = sqlobject.ForeignKey('License', cascade=True)
    Filedata = sqlobject.ForeignKey('Filedata', cascade=True)

class Tag(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    filedata = sqlobject.ForeignKey('Filedata', cascade=True)
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


