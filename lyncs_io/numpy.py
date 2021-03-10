"""
Customizing support for numpy-z
"""

__all__ = [
    "head",
    "load",
    "save",
    "loadtxt",
    "savetxt",
    "headz",
    "loadz",
    "savez",
]

from io import UnsupportedOperation
from functools import wraps
import numpy
from numpy.lib.npyio import NpzFile
from numpy.lib.format import (
    read_magic,
    _check_version,
    _read_array_header,
    header_data_from_array_1_0,
)
from lyncs_utils import is_keyword
from .archive import split_filename, Data, Loader, Archive
from .header import Header
from .utils import swap, open_file
from .mpi_io import MpiIO

loadtxt = numpy.loadtxt
savetxt = swap(numpy.savetxt)


@wraps(numpy.load)
def load(filename, chunks=None, comm=None, **kwargs):
    """
    chunks = number of chunks per dir
    comm = cartesian MPI_Comm
    """
    from mpi4py import MPI

    if comm is None or comm.size == 1:
        return numpy.load(filename, **kwargs)

    metadata = head(filename)
    mpiio = MpiIO(comm, filename)

    mpiio.file_open(MPI.MODE_RDONLY)
    local_array = mpiio.load(
        metadata["shape"], metadata["dtype"], "C", metadata["_offset"]
    )
    mpiio.file_close()

    return local_array


@wraps(numpy.save)
def save(array, filename, comm=None, **kwargs):

    if comm is None or comm.size == 1:
        return numpy.save(filename, array, **kwargs)

    mpiio = MpiIO(comm, filename)
    mpiio.file_open(mpiio.MPI.MODE_CREATE | mpiio.MPI.MODE_WRONLY)

    global_shape, _, _ = mpiio.decomposition.compose(array.shape)

    if mpiio.rank == 0:
        header = header_data_from_array_1_0(array)
        header["shape"] = tuple(global_shape)  # needs to be tuple

        _write_array_header(mpiio.handler, header)

    mpiio.save(array)
    mpiio.file_close()


def _get_offset(npy):
    try:
        return npy.tell()
    except UnsupportedOperation:
        return None


def _get_head(npy):
    "Returns the header of a numpy file"
    version = read_magic(npy)
    _check_version(version)
    shape, fortran_order, dtype = _read_array_header(npy, version)

    return Header(
        {
            "shape": shape,
            "dtype": dtype,
            "_offset": _get_offset(npy),
            "_numpy_version": version,
            "_fortran_order": fortran_order,
        }
    )


head = open_file(_get_head)


def _get_headz(npz, key):
    "Reads the header of a numpy file"

    with npz.zip.open(key + ".npy") as npy:
        return _get_head(npy)


def _write_array_header(fp, d, version=None):
    """Write the header for an array and returns the version used
    Parameters
    ----------
    fp : filelike object
    d : dict
        This has the appropriate entries for writing its string representation
        to the header of the file.
    version: tuple or None
        None means use oldest that works
        explicit version will raise a ValueError if the format does not
        allow saving this data.  Default: None
    """
    import struct
    from numpy.lib import format as fmt

    header = ["{"]
    for key, value in sorted(d.items()):
        # Need to use repr here, since we eval these when reading
        header.append("'%s': %s, " % (key, repr(value)))
    header.append("}")
    header = "".join(header)
    header = numpy.compat.asbytes(fmt._filter_header(header))

    hlen = len(header) + 1  # 1 for newline
    padlen_v1 = fmt.ARRAY_ALIGN - (
        (fmt.MAGIC_LEN + struct.calcsize("<H") + hlen) % fmt.ARRAY_ALIGN
    )
    padlen_v2 = fmt.ARRAY_ALIGN - (
        (fmt.MAGIC_LEN + struct.calcsize("<I") + hlen) % fmt.ARRAY_ALIGN
    )

    # Which version(s) we write depends on the total header size; v1 has a max of 65535
    if hlen + padlen_v1 < 2 ** 16 and version in (None, (1, 0)):
        version = (1, 0)
        header_prefix = fmt.magic(1, 0) + struct.pack("<H", hlen + padlen_v1)
        topad = padlen_v1
    elif hlen + padlen_v2 < 2 ** 32 and version in (None, (2, 0)):
        version = (2, 0)
        header_prefix = magic(2, 0) + struct.pack("<I", hlen + padlen_v2)
        topad = padlen_v2
    else:
        msg = "Header length %s too big for version=%s"
        msg %= (hlen, version)
        raise ValueError(msg)

    # Pad the header with spaces and a final newline such that the magic
    # string, the header-length short and the header are aligned on a
    # ARRAY_ALIGN byte boundary.  This supports memory mapping of dtypes
    # aligned up to ARRAY_ALIGN on systems like Linux where mmap()
    # offset must be page-aligned (i.e. the beginning of the file).
    header = header + b" " * topad + b"\n"

    fp.Write(header_prefix)
    fp.Write(header)
    return version


def headz(filename, key=None, **kwargs):
    "Numpy-z head function"

    filename, key = split_filename(filename, key)

    with numpy.load(filename, **kwargs) as npz:
        assert isinstance(npz, NpzFile), "Broken support for Numpy-z"
        if key:
            return _get_headz(npz, key.lstrip("/"))
        return Archive({key: _get_headz(npz, key) for key in npz})


def loadz(filename, key=None, **kwargs):
    "Numpy-z load function"

    filename, key = split_filename(filename, key)

    loader = Loader(loadz, filename, kwargs=kwargs)

    with numpy.load(filename, **kwargs) as npz:
        assert isinstance(npz, NpzFile), "Broken support for Numpy-z"
        if key:
            return npz[key.lstrip("/")]
        return Archive({key: Data(_get_headz(npz, key)) for key in npz}, loader=loader)


def savez(data, filename, key=None, compressed=False, **kwargs):
    "Numpy-z save function"

    # TODO: numpy overwrites files. Support to numpy-z should be done through zip format
    filename, key = split_filename(filename, key)

    _savez = numpy.savez if not compressed else numpy.savez_compressed

    if key:
        if not is_keyword(key):
            raise ValueError("Numpy-z supports only keys that are a valid keyword")
        return _savez(filename, **{key: data}, **kwargs)
    return _savez(filename, data, **kwargs)
