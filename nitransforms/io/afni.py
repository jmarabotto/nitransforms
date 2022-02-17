"""Read/write AFNI's transforms."""
from math import pi
import numpy as np
from nibabel.affines import (
    apply_affine,
    obliquity,
    voxel_sizes,
)

from .base import (
    BaseLinearTransformList,
    DisplacementsField,
    LinearParameters,
    TransformFileError,
)

LPS = np.diag([-1, -1, 1, 1])
OBLIQUITY_THRESHOLD_DEG = 0.01


class AFNILinearTransform(LinearParameters):
    """A string-based structure for AFNI linear transforms."""

    def __str__(self):
        """Generate a string representation."""
        param = self.structarr["parameters"]
        return "\t".join(["%g" % p for p in param[:3, :].reshape(-1)])

    def to_string(self, banner=True):
        """Convert to a string directly writeable to file."""
        string = "%s\n" % self
        if banner:
            string = "\n".join(
                ("# 3dvolreg matrices (DICOM-to-DICOM, row-by-row):", string)
            )
        return string % self

    @classmethod
    def from_ras(cls, ras, moving=None, reference=None):
        """Create an AFNI affine from a nitransform's RAS+ matrix."""
        # swapaxes is necessary, as axis 0 encodes series of transforms
        parameters = np.swapaxes(LPS @ ras @ LPS, 0, 1)

        tf = cls()
        tf.structarr["parameters"] = parameters.T
        return tf

    @classmethod
    def from_string(cls, string):
        """Read the struct from string."""
        tf = cls()
        sa = tf.structarr
        lines = [
            line
            for line in string.splitlines()
            if line.strip()
            and not (line.startswith("#") or "3dvolreg matrices" in line)
        ]

        if not lines:
            raise TransformFileError

        parameters = np.vstack(
            (
                np.genfromtxt([lines[0].encode()], dtype="f8").reshape((3, 4)),
                (0.0, 0.0, 0.0, 1.0),
            )
        )
        sa["parameters"] = parameters
        return tf

    def to_ras(self, moving=None, reference=None):
        """Return a nitransforms internal RAS+ matrix."""
        # swapaxes is necessary, as axis 0 encodes series of transforms
        return LPS @ np.swapaxes(self.structarr["parameters"].T, 0, 1) @ LPS


class AFNILinearTransformArray(BaseLinearTransformList):
    """A string-based structure for series of AFNI linear transforms."""

    _inner_type = AFNILinearTransform

    def to_ras(self, moving=None, reference=None):
        """Return a nitransforms' internal RAS matrix."""
        return np.stack(
            [xfm.to_ras(moving=moving, reference=reference) for xfm in self.xforms]
        )

    def to_string(self):
        """Convert to a string directly writeable to file."""
        strings = []
        for i, xfm in enumerate(self.xforms):
            lines = [
                line.strip()
                for line in xfm.to_string(banner=(i == 0)).splitlines()
                if line.strip()
            ]
            strings += lines
        return "\n".join(strings)

    @classmethod
    def from_ras(cls, ras, moving=None, reference=None):
        """Create an ITK affine from a nitransform's RAS+ matrix."""
        _self = cls()
        _self.xforms = [
            cls._inner_type.from_ras(ras[i, ...], moving=moving, reference=reference)
            for i in range(ras.shape[0])
        ]
        return _self

    @classmethod
    def from_string(cls, string):
        """Read the struct from string."""
        _self = cls()

        lines = [
            line.strip()
            for line in string.splitlines()
            if line.strip() and not line.startswith("#")
        ]
        if not lines:
            raise TransformFileError("Input string is empty.")

        _self.xforms = [cls._inner_type.from_string(line) for line in lines]
        return _self


class AFNIDisplacementsField(DisplacementsField):
    """A data structure representing displacements fields."""

    @classmethod
    def from_image(cls, imgobj):
        """Import a displacements field from a NIfTI file."""
        hdr = imgobj.header.copy()
        shape = hdr.get_data_shape()

        if len(shape) != 5 or shape[-2] != 1 or not shape[-1] in (2, 3):
            raise TransformFileError(
                'Displacements field "%s" does not come from AFNI.'
                % imgobj.file_map["image"].filename
            )

        field = np.squeeze(np.asanyarray(imgobj.dataobj))
        field[..., (0, 1)] *= -1.0

        return imgobj.__class__(field, imgobj.affine, hdr)


def _is_oblique(affine, thres=OBLIQUITY_THRESHOLD_DEG):
    """
    Determine whether the dataset is oblique.

    Examples
    --------
    >>> _is_oblique(np.eye(4))
    False

    >>> _is_oblique(nb.affines.from_matvec(
    ...     nb.eulerangles.euler2mat(x=0.9, y=0.001, z=0.001),
    ...     [4.0, 2.0, -1.0],
    ... ))
    True

    """
    return (obliquity(affine).min() * 180 / pi) > thres


def _afni_warpdrive(oblique, shape, forward=True, ras=False):
    """
    Calculate AFNI's ``WARPDRIVE_MATVEC_FOR_000000`` (de)obliquing affine.

    Parameters
    ----------
    oblique : 4x4 numpy.array
        affine that is not aligned to the cardinal axes.
    plumb : 4x4 numpy.array
        corresponding affine that is aligned to the cardinal axes.
    forward : :obj:`bool`
        Returns the forward transformation if True, i.e.,
        the matrix to convert an oblique affine into an AFNI's plumb (if ``True``)
        or viceversa plumb -> oblique (if ``false``).

    Returns
    -------
    plumb_to_oblique : 4x4 numpy.array
        the matrix that pre-pended to the plumb affine rotates it
        to be oblique.

    """
    shape = np.array(shape[:3])
    plumb_r = oblique[:3, :3] / np.abs(oblique[:3, :3]).max(0)
    plumb_r[np.abs(plumb_r) < 1.0] = 0
    plumb_r *= voxel_sizes(oblique)
    plumb = np.eye(4)
    plumb[:3, :3] = plumb_r
    obliq_c = oblique @ np.hstack((0.5 * shape, 1.0))
    plumb_c = plumb @ np.hstack((0.5 * shape, 1.0))
    plumb[:3, 3] = -plumb_c[:3] + obliq_c[:3]
    R = plumb @ np.linalg.inv(oblique)

    if not ras:
        # Change sign to match AFNI's warpdrive_matvec signs
        R = LPS @ R @ LPS

    return R if forward else np.linalg.inv(R)


def _afni_header(nii, field="WARPDRIVE_MATVEC_FOR_000000", to_ras=False):
    from lxml import etree
    root = etree.fromstring(nii.header.extensions[0].get_content().decode())
    retval = np.fromstring(
        root.find(f".//*[@atr_name='{field}']").text,
        sep="\n",
        dtype="float32"
    )
    if retval.size == 12:
        retval = np.vstack((retval.reshape((3, 4)), (0, 0, 0, 1)))
        if to_ras:
            retval = LPS @ retval @ LPS

    return retval
