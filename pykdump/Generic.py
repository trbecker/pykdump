#
#  Code that does not depend on whether we use embedded API or PTY
#
# Time-stamp: <07/10/16 09:23:45 alexs>
#
import string
import pprint

import os
import tempfile
import copy

from StringIO import StringIO

pp = pprint.PrettyPrinter(indent=4)

#import wrapcrash as d
d = None

# GLobals used my this module


# The standard hex() appends L for longints
def hexl(l):
    return "0x%x" % l


def unsigned16(l):
    return l & 0xffff

def unsigned32(l):
    return l & 0xffffffff

# A helper class to implement lazy attibute computation. It calls the needed
# function only once and adds the result as an attribute so that next time
# we will not try to compute it again

class LazyEval(object):
    def __init__(self, name, meth):
        self.name = name
        self.meth = meth
    def __get__(self, obj, objtype):
        # Switch 
        #print " ~~lazy~~ ", self.name, '\t', obj.fname
        val = self.meth(obj)
        setattr(obj, self.name, val)
        #obj.__setattr__(self.name, val)
        return val

# A dict-like container
class Bunch(dict):
    def __init__(self, d = {}):
        dict.__init__(self, d)
        self.__dict__.update(d)
    def __setattr__(self, name, value):
        dict.__setitem__(self, name, value)
        object.__setattr__(self, name, value) 
    def __setitem__(self, name, value):
        dict.__setitem__(self, name, value)
        object.__setattr__(self, name, value)
    def copy(self):
        return Bunch(dict.copy(self))
    def __str__(self):
        prn = StringIO()
        keys = self.keys()
        keys.sort()
        for k in keys:
            print >> prn, "  ", k.ljust(12), self[k]
        rc = prn.getvalue()
        prn.close()
        return rc

# Memoize methods with one simple arg  
class MemoizeTI(type):
    __cache = {}
    def __call__(cls, *args):
        sname = args[0]
        try:
            return MemoizeTI.__cache[sname]
        except KeyError:
            rc =  super(MemoizeTI, cls).__call__(*args)
            MemoizeTI.__cache[sname] = rc
            return rc

class MemoizeSU(type):
    __cache = {}
    def __call__(cls, *args):
        sname = args[0]
        try:
            return MemoizeSU.__cache[sname]
        except KeyError:
            rc =  super(MemoizeSU, cls).__call__(*args)
            MemoizeSU.__cache[sname] = rc
            return rc




# INTTYPES = ('char', 'short', 'int', 'long', 'signed', 'unsigned',
#             '__u8', '__u16', '__u32', '__u64',
#              'u8', 'u16', 'u32', 'u64',
#             )
# EXTRASPECS = ('static', 'const', 'volatile')

# Representing types. Here is how we do it:

# 1. basetype or 'target type' - a symbolic name after removing * and
# arrays. For example, for 'struct test **a[2]' this will be 'struct test'.
#
# 2. type of basetype: integer/float/struct/union/func etc.
#    for integers: signed/unsigned and size
#
# 3. Numbers of stars (ptrlev) or None
#
# 4. Dimensions as a list or None

class TypeInfo(object):
    X__metaclass__ = MemoizeTI
    def __init__(self, stype, gdbinit = True ):
        self.stype = stype
        self.size = -1
        self.dims = None
        self.ptrlev = None
        self.typedef = None
        self.details = None
        # For integer types
        self.integertype = None
        if (gdbinit):
            d.update_TI_fromgdb(self, stype)

    def getElements(self):
        if (self.dims):
            elements = reduce(lambda x, y: x*y, self.dims)
        else:
            elements = 1
        return elements

    # Get target info for arrays/pointers - i.e. the same type
    # but without ptrlev or dims
    def getTargetType(self):
        return TypeInfo(self.stype)
        

    def fullname(self):
        out = []
        if (self.ptrlev != None):
            out.append('*' * self.ptrlev)

        # Here we will insert the varname
        pref = string.join(out, '')
        
        out = []
        if (self.dims != None):
            for i in self.dims:
                out.append("[%d]" % i)
        suff = string.join(out, '')
        return (self.stype, pref,suff)
  
        
    # A full form with embedded structs unstubbed
    def fullstr(self, indent = 0):
        stype, pref, suff = self.fullname()
        if (self.details):
            rc = self.details.fullstr(indent)+ ' ' + pref + \
                 suff + ';'
        else:
            rc =  ' ' * indent + "%s %s%s;" % \
                 (stype, pref, suff)
        return rc
     
    def __repr__(self):
        stype, pref, suff = self.fullname()
        out = "TypeInfo <%s %s%s> size=%d" % (stype, pref, suff, self.size)
        return out
    elements = LazyEval("elements", getElements)




# A global Variable or a struct/union field
# This is TypeInfo plus name plus addr.
# For SU we add manually two attributes: offset and parent

class VarInfo(object):
     def __init__(self,  name = None, addr = -1):
         self.name = name
         self.addr = addr
         self.bitsize = None
         self.ti = None
     # A short form for printing inside struct
     def shortstr(self, indent = 0):
         stype, pref, suff = self.ti.fullname()
         rc =  ' ' * indent + "%s %s%s%s;" % \
              (stype, pref, self.name, suff)
         return rc

     # A full form with embedded structs unstubbed
     def fullstr(self, indent = 0):
         stype, pref, suff = self.ti.fullname()
         details =self.ti.details
         if (self.bitsize != None):
             suff +=":%d" % self.bitsize

         if (self.ti.details):
             rc = self.ti.details.fullstr(indent)+ ' ' + pref + \
                  self.name + suff + ';'
         else:
             rc =  ' ' * indent + "%s %s%s%s;" % \
                  (stype, pref, self.name, suff)
         #return rc
         # Add offset etc.
         size = self.ti.size * self.ti.elements
         return rc + ' | off=%d size=%d' % (self.offset, size)

     # Return a dereferencer for this varinfo (PTR type)
     def getDereferencer(self):
         ti = self.ti
         tti = ti.getTargetType()
         nvi = VarInfo()
         nvi.ti = tti
         self.tsize = tti.size
         #print "Creating a dereferencer for", self
         return nvi.getReader()
     # Return a reader for this varinfo
     def getReader(self, ptrlev = None):
         ti = self.ti
         codetype = ti.codetype
         if (codetype == 7):
             return d.intReader(self)
         elif (codetype == 3 or codetype == 4):
             # Struct/Union
             return d.suReader(self)
         elif (codetype == 1):
             #print "getReader", id(self), self
             # Pointer
             if (ptrlev == None):
                 ptrlev = ti.ptrlev
             return d.ptrReader(self, ptrlev)
         else:
             raise TypeError, "don't know how to read codetype "+str(codetype)


     def __repr__(self):
         stype, pref, suff = self.ti.fullname()
         out = "VarInfo <%s%s %s%s> addr=0x%x" % (stype, pref,
                                                 self.name, suff, self.addr)
         return out

     def getPtrlev(self):
         return self.ti.ptrlev

     # Backwards compatibility
     def getBaseType(self):
         return self.ti.stype

     def getSize(self):
         return self.ti.size * self.ti.elements

     def getArray(self):
         dims = self.ti.dims
         if (len(dims) == 1):
             return dims[0]
         else:
             return dims
    
     reader = LazyEval("reader", getReader)
     dereferencer = LazyEval("dereferencer", getDereferencer)

     # Backwards compatibility
     basetype = LazyEval("basetype", getBaseType)
     size = LazyEval("size", getSize)
     array = LazyEval("array", getArray)
     ptrlev = LazyEval("ptrlev", getPtrlev)


    

# This is unstubbed struct representation - showing all its fields.
# Each separate field is represented as SFieldInfo and access to fields
# is possible both via attibutes and dictionary
class SUInfo(dict):
    __metaclass__ = MemoizeSU
    def __init__(self, sname, gdbinit = True):
        #print "Creating SUInfo", sname
        #self.parentstype = None
        #dict.__init__(self, {})
        object.__setattr__(self, "PYT_sname", sname)
        object.__setattr__(self, "PYT_body",  []) # For printing only
        if (gdbinit):
            d.update_SUI_fromgdb(self, sname)

    def __setitem__(self, name, value):
        dict.__setitem__(self, name, value)
        object.__setattr__(self, name, value)

    def append(self, name, value):
        self.PYT_body.append(name)
        self[name] = value
        
    def fullstr(self, indent = 0):
        inds = ' ' * indent
        out = []
        out.append(inds + self.PYT_sname + " {")
        for fn in self.PYT_body:
            out.append(self[fn].fullstr(indent+4))
        out.append(inds+ "}")
        return string.join(out, "\n")

    def __repr__(self):
        return self.fullstr()
    
    def __str__(self):
        out = ["<SUInfo>"]
        out.append(self.PYT_sname + " {")
        for fn in self.PYT_body:
            out.append("    " + self[fn].shortstr())
        out.append("}")
        return string.join(out, "\n")


class ArtStructInfo(SUInfo):
    def __init__(self, sname):
        SUInfo.__init__(self, sname, False)
        self.size = self.PYT_size = 0
    def append(self, ftype, fname):
        vi = VarInfo(fname)
        vi.ti = TypeInfo(ftype)
        vi.offset = self.PYT_size
        vi.bitoffset = vi.offset * 8

        SUInfo.append(self, fname, vi)
        # Adjust the size
        self.PYT_size += vi.size
        self.size = self.PYT_size
    # Inline an already defined SUInfo adding its fields and
    # adjusting their offsets
    def inline(self, si):
        osize = self.PYT_size
        for f in si.PYT_body:
            vi = copy.copy(si[f])
            vi.offset += osize
            vi.bitoffset += 8 *osize
            SUInfo.append(self, vi.name, vi)
            
        # Adjust the size
        self.PYT_size += si.PYT_size
        self.size += si.PYT_size
            
        
        
        

            
# If 'flags' integer variable has some bits set and we assume their
# names/values are in a dict-like object, return a string. For example,
# decoding interface flags we will print "UP|BROADCAST|RUNNING|MULTICAST"

def dbits2str(flags, d, offset = 0):
    out = ""
    for name, val in d.items():
        if (val and (flags & val)):
            if (out == ""):
                out = name[offset:]
            else:
                out += "|" + name[offset:]
    return out


# Join left and right panels, both as multiline strings
def print2columns(left,right):
    left = left.split("\n")
    right = right.split("\n")
    for l, r in map(None, left, right):
        if (l == None):
            l = ""
        if (r == None):
            r = ""
        print l.ljust(38), r

class PYT_tmpfiles:
    def __init__(self):
        self.tempdir = tempfile.mkdtemp("pycrash")
        self.flist = []
    def mkfifo(self):
        fifoname = self.tempdir + "/" + "PYT_fifo"
        try:
            os.mkfifo(fifoname)
        except OSError, (err, errstr):
            if (err == errno.EEXIST):
                # Check whether it's FIFO and writable
                st_mode = os.stat(fifoname)[0]
                if (not stat.S_ISFIFO(st_mode)):
                    print "FATAL: %s is not a FIFO" % fifoname
                    fifoname = None             # To prevent cleanup
                    sys.exit(1)
            else:
                print "FATAL: cannot mkfifo %s in the current directory" % fifoname
                sys.exit(1)
        self.flist.append(fifoname)
        return fifoname
    
    def cleanup(self):
        for f in self.flist:
            try:
                os.unlink(f)
                #print "unlinking", f
            except:
                pass
        os.rmdir(self.tempdir)
        #print "rmdir", self.tempdir

    def mkfile(self):
        fd, fname = tempfile.mkstemp('', '', self.tempdir)
        self.flist.append(fname)
        return os.fdopen(fd, "w"), fname
