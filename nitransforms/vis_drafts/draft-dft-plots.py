import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from pathlib import Path

from nitransforms.base import TransformError
from nitransforms.linear import Affine
from nitransforms.nonlinear import DenseFieldTransform

class PlotDenseField():
    """
    NotImplented: description of class object here
    """

    __slots__ = ('_path_to_file')

    def __init__(self, path_to_file):
         self._path_to_file = path_to_file

    def plot_densefield(self, is_deltas=True, scaling=1, index=10000, save_to_path=None):
        """
        Plot output field from DenseFieldTransform class.

        Parameters
        ----------
        is_deltas : :obj:`bool`
            Whether this is a displacements (deltas) field (default: is_deltas=True), or deformations (is_deltas=False).
        save_to_path: :obj:`str`
            Path to which the output plot is to be saved.
        scaling: :obj:`float`
            Fraction by which the quiver plot arrows are to be scaled (default: 1)
        index: :obj:`float`
            Indexing for plotting (default: index=100). The index defines the interval to be used when selecting datapoints, such that are only plotted elements [0::index]

        Example
        -------
        >>> plot = Vis(
        ...     test_dir / "someones_displacement_field.nii.gz"
        ... ).plot_densefield()

        >>> plot = Vis(
        ...     test_dir / "someones_displacement_field.nii.gz"
        ... ).plot_densefield(
        ...     is_deltas = True #deltas field
                scaling = 0.25 #arrow scaling = 4 times true length
                index = 100 #plot 1/100 data points, using indexing [0::10]
        ...     save_to_path = test_dir / "plot_of_someones_displacement_field.nii.gz" #save figure
        ... )
        """

        xfm = DenseFieldTransform(
             self._path_to_file,
             is_deltas=is_deltas,
        )

        if xfm._field.shape[-1] != xfm.ndim:
            raise TransformError(
                "The number of components of the field (%d) does not match "
                "the number of dimensions (%d)" % (xfm._field.shape[-1], xfm.ndim)
            )

        x, y, z, u, v, w = self.map_coords(xfm, index)

        magnitude = np.sqrt(u**2 + v**2 + w**2)
        clr_xy = np.hypot(u, v)
        clr_xz = np.hypot(u, w)
        clr3d = plt.cm.viridis(magnitude/magnitude.max())

        """Plot"""
        axes = self.format_fig(figsize=(15, 8), gs_rows=2, gs_cols=3, gs_wspace=1/4, gs_hspace=1/2.5)

        self.format_axes(axes[0], "x-y projection", "x", "y")
        q1 = axes[0].quiver(x, y, u, v, clr_xy, cmap='viridis', angles='xy', scale_units='xy', scale=scaling)
        plt.colorbar(q1)

        self.format_axes(axes[1], "x-z projection", "x", "z")
        q2 = axes[1].quiver(x, z, u, w, clr_xz, cmap='viridis', angles='xy', scale_units='xy', scale=scaling)
        plt.colorbar(q2)

        self.format_axes(axes[2], "3D projection", "x", "y", "z")
        q3 = axes[2].quiver(x, y, z, u, v, w, colors=clr3d, length=2/scaling)
        plt.colorbar(q3)

        if save_to_path is not None:
            plt.savefig(str(save_to_path), dpi=300)
            assert os.path.isdir(os.path.dirname(save_to_path))
        else:
            pass
        plt.show()

    def map_coords(self, xfm, index):
        """Calculate vector components of the field using the reference coordinates"""
        x = xfm.reference.ndcoords[0][0::index]
        y = xfm.reference.ndcoords[1][0::index]
        z = xfm.reference.ndcoords[2][0::index]

        u = xfm._field[...,0].flatten()[0::index] - x
        v = xfm._field[...,1].flatten()[0::index] - y
        w = xfm._field[...,2].flatten()[0::index] - z
        return x, y, z, u, v, w

    def format_fig(self, figsize, gs_rows, gs_cols, gs_wspace, gs_hspace):
        fig = plt.figure(figsize=figsize) #(12, 6) for gs(2,3)
        fig.suptitle(str("Non-Linear DenseFieldTransform field"), fontsize='20', weight='bold')
        gs = GridSpec(gs_rows, gs_cols, figure=fig, wspace=gs_wspace, hspace=gs_hspace)

        axes = [fig.add_subplot(gs[0,0]), fig.add_subplot(gs[1,0]), fig.add_subplot(gs[:,1:], projection='3d')]
        return axes

    def format_axes(self, axis, title=None, xlabel="x", ylabel="y", zlabel="z", rotate_3dlabel=False, labelsize=16, ticksize=14):
        '''Format the figure axes. For 2D plots, zlabel and zticks parameters are None.'''
        axis.tick_params(labelsize=ticksize)

        axis.set_title(title, weight='bold')
        axis.set_xlabel(xlabel, fontsize=labelsize)
        axis.set_ylabel(ylabel, fontsize=labelsize)

        '''if 3d projection plot'''
        try:
            axis.set_zlabel(zlabel, fontsize=labelsize+4)
            axis.xaxis.set_rotate_label(rotate_3dlabel)
            axis.yaxis.set_rotate_label(rotate_3dlabel)
            axis.zaxis.set_rotate_label(rotate_3dlabel)
        except:
            pass
        return
    
    def format_ticks(self, axis, xticks, yticks, zticks):
        axis.set_xticks((xticks))
        axis.set_yticks((yticks))
        try:
            axis.set_zticks((zticks))
        except:
            pass

#Example:
path_to_file = Path("../tests/data/ds-005_sub-01_from-OASIS_to-T1_warp_fsl.nii.gz")
save_to_dir = Path("/Users/julienmarabotto/workspace/Neuroimaging/plots/quiver")

plot = PlotDenseField(path_to_file).plot_densefield(is_deltas=True, scaling=0.25, save_to_path=(save_to_dir / "example_dense_field.jpg"), index=10000)