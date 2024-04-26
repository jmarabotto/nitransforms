"""Tests of the base module."""
import numpy as np
import nibabel as nb
import pytest
import h5py

from ..base import SpatialReference, SampledSpatialData, ImageGrid, TransformBase
from .. import linear as nitl, nonlinear as nitnl


def test_SpatialReference(testdata_path):
    """Ensure the reference factory is working properly."""
    obj1 = testdata_path / "someones_anatomy.nii.gz"
    obj2 = testdata_path / "sub-200148_hemi-R_pial.surf.gii"
    obj3 = testdata_path / "func.nii.gz"

    assert isinstance(SpatialReference.factory(obj1), ImageGrid)
    assert isinstance(SpatialReference.factory(str(obj1)), ImageGrid)
    assert isinstance(SpatialReference.factory(nb.load(str(obj1))), ImageGrid)
    assert isinstance(SpatialReference.factory(obj2), SampledSpatialData)
    assert isinstance(SpatialReference.factory(str(obj2)), SampledSpatialData)
    assert isinstance(SpatialReference.factory(nb.load(str(obj2))), SampledSpatialData)
    assert isinstance(SpatialReference.factory(obj3), ImageGrid)
    assert isinstance(SpatialReference.factory(str(obj3)), ImageGrid)
    assert isinstance(SpatialReference.factory(nb.load(str(obj3))), ImageGrid)

    func_ref = SpatialReference.factory(obj3)
    assert func_ref.ndim == 3
    assert func_ref.shape == (96, 96, 56)
    assert func_ref.npoints == np.prod(func_ref.shape)


@pytest.mark.parametrize("image_orientation", ["RAS", "LAS", "LPS", "oblique"])
def test_ImageGrid(get_testdata, image_orientation):
    """Check the grid object."""
    im = get_testdata[image_orientation]

    img = ImageGrid(im)
    assert np.allclose(img.affine, np.linalg.inv(img.inverse))

    # Test ras2vox and vox2ras conversions
    ijk = [[10, 10, 10], [40, 4, 20], [0, 0, 0], [s - 1 for s in im.shape[:3]]]
    xyz = [img._affine.dot(idx + [1])[:-1] for idx in ijk]

    assert np.allclose(img.ras(ijk[0]), xyz[0])
    assert np.allclose(np.round(img.index(xyz[0])), ijk[0])
    assert np.allclose(img.ras(ijk), xyz)
    assert np.allclose(np.round(img.index(xyz)), ijk)

    # nd index / coords
    idxs = img.ndindex
    coords = img.ndcoords
    assert len(idxs.shape) == len(coords.shape) == 2
    assert idxs.shape[0] == coords.shape[0] == img.ndim == 3
    assert idxs.shape[1] == coords.shape[1] == img.npoints == np.prod(im.shape)

    img2 = ImageGrid(img)
    assert img2 == img
    assert (img2 != img) is False


def test_ImageGrid_utils(tmpdir, testdata_path, get_testdata):
    """Check that images can be objects or paths and equality."""
    tmpdir.chdir()

    im1 = get_testdata["RAS"]
    im2 = testdata_path / "someones_anatomy.nii.gz"

    ig = ImageGrid(im1)
    assert ig == ImageGrid(im2)
    assert ig.shape is not None

    with h5py.File("xfm.x5", "w") as f:
        ImageGrid(im1)._to_hdf5(f.create_group("Reference"))


def test_TransformBase(monkeypatch, testdata_path, tmpdir):
    """Check the correctness of TransformBase components."""
    tmpdir.chdir()

    def _fakemap(klass, x, inverse=False, index=0):
        return x

    def _to_hdf5(klass, x5_root):
        return None

    monkeypatch.setattr(TransformBase, "map", _fakemap)
    monkeypatch.setattr(TransformBase, "_to_hdf5", _to_hdf5)
    fname = testdata_path / "someones_anatomy.nii.gz"

    img = nb.load(fname)
    imgdata = np.asanyarray(img.dataobj, dtype=img.get_data_dtype())

    # Test identity transform
    xfm = TransformBase()
    xfm.reference = fname
    with pytest.raises(TypeError):
        _ = xfm.ndim
    moved = xfm.apply(fname, order=0)
    assert np.all(
        imgdata == np.asanyarray(moved.dataobj, dtype=moved.get_data_dtype())
    )

    # Test identity transform - setting reference
    xfm = TransformBase()
    xfm.reference = fname
    with pytest.raises(TypeError):
        _ = xfm.ndim
    moved = xfm.apply(str(fname), reference=fname, order=0)
    assert np.all(
        imgdata == np.asanyarray(moved.dataobj, dtype=moved.get_data_dtype())
    )

    #Test ndim returned by affine
    assert nitl.Affine().ndim == 3
    assert nitl.LinearTransformsMapping(
        [nitl.Affine(), nitl.Affine()]
    ).ndim == 4

    # Test applying to Gifti
    gii = nb.gifti.GiftiImage(
        darrays=[
            nb.gifti.GiftiDataArray(
                data=xfm.reference.ndcoords.astype("float32"),
                intent=nb.nifti1.intent_codes["pointset"],
            )
        ]
    )
    giimoved = xfm.apply(fname, reference=gii, order=0)
    assert np.allclose(giimoved.reshape(xfm.reference.shape), moved.get_fdata())

    # Test to_filename
    xfm.to_filename("data.x5")


def test_SampledSpatialData(testdata_path):
    """Check the reference generated by cifti files."""
    gii = testdata_path / "sub-200148_hemi-R_pial.surf.gii"

    ssd = SampledSpatialData(gii)
    assert ssd.npoints == 249277
    assert ssd.ndim == 3
    assert ssd.ndcoords.shape == (249277, 3)
    assert ssd.shape is None

    ssd2 = SampledSpatialData(ssd)
    assert ssd2.npoints == 249277
    assert ssd2.ndim == 3
    assert ssd2.ndcoords.shape == (249277, 3)
    assert ssd2.shape is None

    # check what happens with an empty gifti
    with pytest.raises(TypeError):
        gii = nb.gifti.GiftiImage()
        SampledSpatialData(gii)


def test_concatenation(testdata_path):
    """Check concatenation of affines."""
    aff = nitl.Affine(reference=testdata_path / "someones_anatomy.nii.gz")
    x = [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (-1.0, -1.0, -1.0)]
    assert np.all((aff + nitl.Affine())(x) == x)
    assert np.all((aff + nitl.Affine())(x, inverse=True) == x)
