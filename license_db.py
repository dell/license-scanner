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
    moduleLogVerbose.debug("query by soname failed for %s." % soname.soname)
    for fd in Filedata.select( Filedata.q.basename == soname.soname ):
        moduleLogVerbose.debug("try to get license by %s" % fd.full_path)
        lic = get_license(fd, preferred)
        if lic != "NOT_FOUND_FD":
            return lic

    return "NOT_FOUND_LIB"

decorate(traceLog())
def license_is_compatible(opts, lic1, lic2):
    if lic1 == lic2:
        return True
    if lic2 in opts.license_compat.get(lic1, []):
        return True
    return False

def iter_over_dt_needed_nonrecursive(opts, filedata, parent=None):
    from license_db import DtNeededList
    q = DtNeededList.select( DtNeededList.q.filedata == filedata.id ).throughTo.soname.throughTo.has_soname
    for soname in q:
        yield soname

decorate(traceLog())
def iter_over_dt_needed(opts, filedata, parent=None, myfault=0, get_all=True, break_on_incompatible=0, recurse_level=0, seen=None):
    from license_db import DtNeededList
    q = DtNeededList.select( DtNeededList.q.filedata == filedata.id ).throughTo.soname.throughTo.has_soname
    retlist = []
    inforec = { "level": 0, "culprit": myfault, "compatible": True, "filedata": filedata, 'incompat_licenses':[] }

    def uniq_add(*args):
        for l in args:
            if l not in  inforec["incompat_licenses"]:
                inforec["incompat_licenses"].append(l)

    filedata_license = get_license(filedata)
    indent = "  " * recurse_level
    recurse_level = recurse_level + 1

    if seen is None: seen={}
    if seen.get(filedata.id) is not None:
        moduleLogVerbose.debug("%s  --already-seen--> **%s" % (indent, filedata.basename))
        inforec["compatible"] = seen.get(filedata.id)["compatible"]
        inforec["incompat_licenses"] = seen.get(filedata.id)["incompat_licenses"]
        yield inforec
        raise StopIteration()

    # check license compatibility of all direct, first-level children
    for soname in q:
        moduleLogVerbose.debug("%s  --> %s seen(%s)" % (indent, soname.basename, seen.keys()))
        if break_on_incompatible > 2:
            break
        culprit = False
        # check child license compatibility
        soname_license = get_license(soname)
        if not license_is_compatible(opts, filedata_license, soname_license):
            inforec["compatible"] = False
            uniq_add(soname_license)
            culprit = True
            if break_on_incompatible:
                break

        # tell our kid if he is the source of the license incompatibility (using 'culprit' param)
        for dep in iter_over_dt_needed(opts, soname, filedata, culprit, get_all, break_on_incompatible, recurse_level, seen):
            # now flip our bit to false if any of our children has incompatibilities
            if not dep["compatible"]:
                inforec["compatible"] = False
                #uniq_add(*dep["incompat_licenses"])
                if break_on_incompatible:
                    break_on_incompatible = 2
                    break

            # we have to check license compatility with all descendents, too
            dep_license = get_license(dep["filedata"])
            if not license_is_compatible(opts, filedata_license, dep_license):
                inforec["compatible"] = False
                uniq_add(dep_license)
                dep["culprit"] = True
                if break_on_incompatible:
                    break_on_incompatible = 2
                    break

            # dont recurse more than 32 levels
            if get_all and dep["level"] < 32:
                # increase level of our children
                dep["level"] = dep["level"] + 1
                yield dep

    seen[inforec["filedata"].id] = inforec
    yield inforec


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
    filedata = sqlobject.ForeignKey('Filedata', cascade=True)
    soname = sqlobject.ForeignKey('Soname', cascade=True)

class SonameList(sqlobject.SQLObject):
    class sqlmeta(myMeta): pass
    soname = sqlobject.ForeignKey('Soname', cascade=True)
    filedata = sqlobject.ForeignKey('Filedata', cascade=True)

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


