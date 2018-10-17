from weld.weldobject import *

from .cache import Cache
from .convertors.utils import to_weld_vec


class LazyResult(object):
    """Wrapper class around a yet un-evaluated Weld result.

    Attributes
    ----------
    weld_expr : WeldObject or numpy.ndarray
        Expression that needs to be evaluated.
    weld_type : WeldType
        Type of the output.
    ndim : int
        Dimensionality of the output.

    """
    _cache = Cache()

    def __init__(self, weld_expr, weld_type, ndim):
        self.weld_expr = weld_expr
        self.weld_type = weld_type
        self.ndim = ndim

    def __repr__(self):
        return "{}(weld_type={}, ndim={})".format(self.__class__.__name__,
                                                  self.weld_type,
                                                  self.ndim)

    def __str__(self):
        return str(self.weld_expr)

    @property
    def values(self):
        """The internal data representation.

        Returns
        -------
        numpy.ndarray or WeldObject
            The internal data representation.

        """
        return self.weld_expr

    def is_raw(self):
        return not isinstance(self.weld_expr, WeldObject)

    def evaluate(self, verbose=False, decode=True, passes=None, num_threads=1,
                 apply_experimental_transforms=True):
        """Evaluate the stored expression.

        Parameters
        ----------
        verbose : bool, optional
            Whether to print output for each Weld compilation step.
        decode : bool, optional
            Whether to decode the result
        passes : list, optional
            Which Weld optimization passes to apply
        num_threads : int, optional
            On how many threads to run Weld
        apply_experimental_transforms : bool
            Whether to apply the experimental Weld transforms.

        Returns
        -------
        numpy.ndarray
            Output of the evaluated expression.

        """
        if isinstance(self.weld_expr, WeldObject):
            old_context = dict(self.weld_expr.context)

            for key in self.weld_expr.context.keys():
                if LazyResult._cache.contains(key):
                    self.weld_expr.context[key] = LazyResult._cache.get(key)

            evaluated = self.weld_expr.evaluate(to_weld_vec(self.weld_type,
                                                            self.ndim),
                                                verbose,
                                                decode,
                                                passes,
                                                num_threads,
                                                apply_experimental_transforms)

            self.weld_expr.context = old_context

            return evaluated
        else:
            return self.weld_expr


# TODO: could make all subclasses but seems rather unnecessary atm
class LazyScalarResult(LazyResult):
    def __init__(self, weld_expr, weld_type):
        super(LazyScalarResult, self).__init__(weld_expr, weld_type, 0)


class LazyLongResult(LazyScalarResult):
    def __init__(self, weld_expr):
        super(LazyScalarResult, self).__init__(weld_expr, WeldLong(), 0)


class LazyDoubleResult(LazyScalarResult):
    def __init__(self, weld_expr):
        super(LazyScalarResult, self).__init__(weld_expr, WeldDouble(), 0)


class LazyStructResult(LazyResult):
    # weld_types should be a list of the Weld types in the struct
    def __init__(self, weld_expr, weld_types):
        super(LazyStructResult, self).__init__(weld_expr, WeldStruct(weld_types), 0)


class LazyStructOfVecResult(LazyStructResult):
    # weld_types should be a list of the Weld types in the struct
    def __init__(self, weld_expr, weld_types):
        weld_vec_types = [WeldVec(weld_type) for weld_type in weld_types]

        super(LazyStructOfVecResult, self).__init__(weld_expr, weld_vec_types)
