""" List of formats supported by Lyncs IO """

__all__ = [
    "register",
    "formats",
]

import pickle
import numpy
from .format import Format

formats = []


def register(name, *args, **kwargs):
    if name in formats:
        raise ValueError("A format with the same name already exists")
    formats.append(Format(name, *args, **kwargs))


def swap(fnc):
    return lambda fname, data, *args, **kwargs: fnc(data, fname, *args, **kwargs)


register(
    "pickle",
    extensions=["pkl"],
    modules={
        "pickle": pickle,
        "dill": "dill",
    },
    description="Python's pickle file format",
)

register(
    "lime",
    extensions=["lime"],
    modules={
        "lime": "lime",
        "clime": "lyncs_clime",
    },
    description="LQCD lime format",
    encapsulated=True,
)

register(
    "ascii",
    extensions=["txt"],
    modules={
        "numpy": {"load": numpy.loadtxt, "save": swap(numpy.savetxt)},
    },
    description="ASCII format. Not recommended!",
)

register(
    "hdf5",
    extensions=["h5", "hdf5"],
    modules={
        "h5py": "h5py",
    },
    description="HDF5 file format",
    encapsulated=True,
)

register(
    "numpy",
    extensions=["npy"],
    modules={
        "numpy": {"load": numpy.load, "save": swap(numpy.save)},
    },
    description="Numpy binary format",
)