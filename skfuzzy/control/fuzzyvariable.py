"""
fuzzyvariable.py : Contains base fuzzy variable class.
"""
import numpy as np
import matplotlib.pyplot as plt

from skfuzzy import defuzz, interp_membership
from ..membership import trimf
from .visualization import FuzzyVariableVisualizer

try:
    from collections import OrderedDict
except ImportError:
    from .ordereddict import OrderedDict


class FuzzyVariableTerm(object):
    """
    An term and associated member function for a fuzzy varaible.
    For example, if one were creating a FuzzyVariable with a simple three-point
    liker scale, three `FuzzyVariableTerm` would be created: poor, average,
    and good.
    """

    def __init__(self, label, membership_function):
        self.label = label
        self.mf = membership_function

        self.parent_variable = None
        self.membership_value = None

    @property
    def full_label(self):
        """Term with parent.  Ex: velocity['fast']"""
        if self.parent_variable is None:
            raise ValueError("This term must be bound to a parent first")
        return self.parent_variable.label + "[" + self.label + "]"

    def __repr__(self):
        return self.full_label

    def view(self, *args, **kwargs):
        """""" + FuzzyVariableVisualizer.view.__doc__
        viz = FuzzyVariableVisualizer(self.parent_variable)
        viz.view(*args, **kwargs)

        # Emphasize my membership function
        viz.plots[self.label][0].set_linewidth(3)
        viz.fig.show()


class FuzzyVariable(object):
    """
    Base class containing universe variable & associated membership functions.

    Parameters
    ----------
    universe : array-like
        Universe variable. Must be 1-dimensional and convertible to a NumPy
        array. Required.
    label : string
        Name of the universe variable. Optional.

    Methods
    -------

    Notes
    -----
    This class is designed as the base class underlying the Antecedent and
    Consequent classes, not for individual use.
    """
    def __init__(self, universe, label, defuzzify_method='centroid'):
        """
        Initialization of fuzzy variable

        Parameters
        ----------
        universe : array-like
            Universe variable. Must be 1-dimensional and convertible to a NumPy
            array.
        label : string
            Unique name of the universe variable, e.g., 'food' or 'velocity'.
        """
        self.universe = np.asarray(universe)
        self.label = label
        self.defuzzify_method = defuzzify_method
        self.terms = OrderedDict()

        self._id = id(self)
        self._crisp_value_accessed = False

        class _NotGenerator(object):
            def __init__(self, var):
                self.var = var

            def __getitem__(self, key):
                # Get the positive version of the term
                lbl = "NOT-" + key
                if lbl in self.var.terms.keys():
                    return self.var[lbl]

                posterm = self.var[key]
                negterm = FuzzyVariableTerm(lbl, 1. - posterm.mf)
                if posterm.membership_value is not None:
                    negterm.membership_value = 1. - posterm.membership_value
                self.var[lbl] = negterm
                return negterm
        self.not_ = _NotGenerator(self)

    def __repr__(self):
        return "{0}: {1}".format(self.__name__, self.label)

    def __len__(self):
        return self.universe.size

    def __getitem__(self, key):
        """
        Calling variable['label'] will return the 'label' term
        """
        if key in self.terms.keys():
            return self.terms[key]
        else:
            # Build a pretty list of available mf labels and raise an
            # informative error message
            options = ''
            i0 = len(self.terms) - 1
            i1 = len(self.terms) - 2
            for i, available_key in enumerate(self.terms.keys()):
                if i == i1:
                    options += "'" + str(available_key) + "', or "
                elif i == i0:
                    options += "'" + str(available_key) + "'."
                else:
                    options += "'" + str(available_key) + "'; "
            raise ValueError("Membership function '{0}' does not exist for "
                             "{1} {2}.\n"
                             "Available options: {3}".format(
                                 key, self.__name__, self.label, options))

    def __setitem__(self, key, item):
        """
        Enables new membership functions or term to be added with the
        syntax::

          variable['new_label'] = new_mf
        """
        if isinstance(item, FuzzyVariableTerm):
            if item.label != key:
                raise ValueError("Term's label must match new key")
            if item.parent_variable is not None:
                raise ValueError("Term must not already have a parent")
        else:
            # Try to create a term from item, assuming it is a membership
            # function
            item = FuzzyVariableTerm(key, np.asarray(item))

        if self._crisp_value_accessed:
            # TODO: Overcome this limitation
            raise ValueError("Cannot add adjectives after accessing the "
                             "crisp value of this variable.")

        mf = item.mf

        if mf.size != self.universe.size:
            raise ValueError("New membership function {0} must be equivalent "
                             "in length to the universe variable.\n"
                             "Expected {1}, got {2}.".format(
                                 key, self.universe.size, mf.size))

        if (mf.max() > 1. + 1e-6) or (mf.min() < 0 - 1e-6):
            raise ValueError("Membership function {0} contains values out of "
                             "range. Allowed range is [0, 1].".format(key))

        # If above pass, add the new membership function
        item.parent_variable = self
        self.terms[key] = item

    @property
    def crisp_value(self):
        """Derive crisp value based on membership of adjectives"""
        output_mf, cut_mfs = self._find_crisp_value()
        if len(cut_mfs) == 0:
            raise ValueError("No terms have memberships.  Make sure you "
                             "have at least one rule connected to this "
                             "variable and have run the rules calculation.")
        self._crisp_value_accessed = True
        return defuzz(self.universe, output_mf, self.defuzzify_method)

    @crisp_value.setter
    def crisp_value(self, value):
        """Propagate crisp value down to adjectives by calculating membership"""
        if len(self.terms) == 0:
            raise ValueError("Set Term membership function(s) first")

        for label, adj in self.terms.items():
            adj.membership_value = \
                                interp_membership(self.universe, adj.mf, value)
        self._crisp_value_accessed = True

    def _find_crisp_value(self):
        # Check we have some adjectives
        if len(self.terms.keys()) == 0:
            raise ValueError("Set term membership function(s) first")

        # Initilize membership
        output_mf = np.zeros_like(self.universe, dtype=np.float64)

        # Build output membership function
        cut_mfs = {}
        for label, term in self.terms.items():
            cut = term.membership_value
            if cut is None:
                continue # No membership defined for this adjective
            cut_mfs[label] = np.minimum(cut, term.mf)
            np.maximum(output_mf, cut_mfs[label], output_mf)

        return output_mf, cut_mfs

    def view(self, *args, **kwargs):
        """""" + FuzzyVariableVisualizer.view.__doc__
        fig = FuzzyVariableVisualizer(self).view(*args, **kwargs)
        fig.show()


    def automf(self, number=5, variable_type='quality', names=None,
               invert=False):
        """
        Automatically populates the universe with membership functions.

        Parameters
        ----------
        number : [3, 5, 7] or list of names
            Number of membership functions to create. Must be an odd integer.
            At present, only 3, 5, or 7 are supported.
            If a list of names is given, then those are used
        variable_type : string
            Type of variable this is. Accepted arguments are
            * 'quality' : Continuous variable, higher values are better.
            * 'quant' : Quantitative variable, no value judgements.
        names : list
            List of names to use when creating mebership functions (if you don't
            want to use the default ones)
        invert : bool
            Reverses the naming order if True. Membership function peaks still
            march from lowest to highest.

        Notes
        -----
        This convenience function allows quick construction of fuzzy variables
        with overlapping, triangular membership functions.

        It uses a standard naming convention defined for ``'quality'`` as::

        * dismal
        * poor
        * mediocre
        * average (always middle)
        * decent
        * good
        * excellent

        and for ``'quant'`` as::

        * lowest
        * lower
        * low
        * average (always middle)
        * high
        * higher
        * highest

        where the names on either side of ``'average'`` are used as needed to
        create 3, 5, or 7 membership functions.
        """
        if names is not None:
            # set number based on names passed
            number = len(names)
            if number % 2 != 1:
                raise ValueError("Must provide an odd number of names")
        else:
            if number not in [3, 5, 7]:
                raise ValueError("Only number = 3, 5, or 7 supported.")

            if variable_type.lower() == 'quality':
                names = ['dismal',
                         'poor',
                         'mediocre',
                         'average',
                         'decent',
                         'good',
                         'excellent']
            else:
                names = ['lowest',
                         'lower',
                         'low',
                         'average',
                         'high',
                         'higher',
                         'highest']

            if number == 3:
                if variable_type.lower() == 'quality':
                    names = names[1:6:2]
                else:
                    names = names[2:5]
            if number == 5:
                names = names[1:6]

        if invert is True:
            names = names[::-1]

        limits = [self.universe.min(), self.universe.max()]
        universe_range = limits[1] - limits[0]
        widths = [universe_range / ((number - 1) / 2.)] * int(number)
        centers = np.linspace(limits[0], limits[1], number)

        abcs = [[c - w / 2, c, c + w / 2] for c, w in zip(centers, widths)]

        # Clear existing adjectives, if any
        self.terms = OrderedDict()

        # Repopulate
        for name, abc in zip(names, abcs):
            self[name] = trimf(self.universe, abc)
