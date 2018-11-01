from weld.weldobject import WeldObject

from .convertors import default_missing_data_literal
from .lazy_result import LazyStructOfVecResult, WeldVec, WeldChar
from .weld_utils import get_weld_obj_id, create_weld_object, to_weld_literal, create_empty_weld_object, \
    weld_arrays_to_vec_of_struct, weld_vec_of_struct_to_struct_of_vec, extract_placeholder_weld_objects, Cache


def weld_range(start, stop, step):
    """Create a vector for the range parameters above.

    Parameters
    ----------
    start : int
    stop : int or WeldObject
        Could be the lazily computed length of a WeldObject vec.
    step : int

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    if isinstance(stop, WeldObject):
        obj_id, weld_obj = create_weld_object(stop)
        stop = obj_id
    else:
        weld_obj = create_empty_weld_object()

    weld_template = """result(
    for(
        rangeiter({start}L, {stop}, {step}L),
        appender[i64],
        |b: appender[i64], i: i64, e: i64| 
            merge(b, e)
    )
)"""

    stop = '{}L'.format(stop) if isinstance(stop, int) else stop

    weld_obj.weld_code = weld_template.format(start=start,
                                              stop=stop,
                                              step=step)

    return weld_obj


def weld_compare(array, scalar, operation, weld_type):
    """Applies comparison operation between each element in the array with scalar.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input data.
    scalar : {int, float, str, bool, bytes_}
        Value to compare with; must be same type as the values in the array. If not a str,
        it is casted to weld_type (allowing one to write e.g. native Python int).
    operation : str
        Operation to do out of: {<, <=, ==, !=, >=, >}.
    weld_type : WeldType
        Type of the elements in the input array.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    obj_id, weld_obj = create_weld_object(array)

    scalar = to_weld_literal(scalar, weld_type)

    cast = '{type}({scalar})'.format(type=weld_type, scalar=scalar)
    # actually checking WeldVec(WeldChar)
    if isinstance(weld_type, WeldVec):
        cast = get_weld_obj_id(weld_obj, scalar)

    # TODO: there should be no casting! requires Weld fix
    weld_template = """map(
    {array},
    |a: {type}| 
        a {operation} {cast}
)"""

    weld_obj.weld_code = weld_template.format(array=obj_id,
                                              operation=operation,
                                              type=weld_type,
                                              cast=cast)

    return weld_obj


def weld_filter(array, weld_type, bool_array):
    """Returns a new array only with the elements with a corresponding True in bool_array.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input data.
    weld_type : WeldType
        Type of the elements in the input array.
    bool_array : numpy.ndarray or WeldObject
        Array of bool with True for elements in array desired in the result array.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    obj_id, weld_obj = create_weld_object(array)
    bool_obj_id = get_weld_obj_id(weld_obj, bool_array)

    weld_template = """result(
    for(
        zip({array}, {bool_array}),
        appender[{type}],
        |b: appender[{type}], i: i64, e: {{{type}, bool}}| 
            if (e.$1, 
                merge(b, e.$0), 
                b)
    )
)"""

    weld_obj.weld_code = weld_template.format(array=obj_id,
                                              bool_array=bool_obj_id,
                                              type=weld_type)

    return weld_obj


def _replace_slice_defaults(slice_, default_start, default_step):
    start = slice_.start
    stop = slice_.stop
    step = slice_.step

    if start is None:
        start = default_start

    # stop is required when making a slice, no need to replace

    if step is None:
        step = default_step

    return slice(start, stop, step)


def weld_slice(array, weld_type, slice_, default_start=0, default_step=1):
    """Returns a new array according to the given slice.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        1-dimensional array.
    weld_type : WeldType
        Type of the elements in the input array.
    slice_ : slice
        Subset to return. Assumed valid slice.
    default_start : int, optional
        Default value to slice start.
    default_step : int, optional
        Default value to slice step.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    slice_ = _replace_slice_defaults(slice_, default_start, default_step)
    obj_id, weld_obj = create_weld_object(array)

    if slice_.step == 1:
        weld_template = """slice(
    {array},
    {slice_start},
    {slice_stop}
)"""
    else:
        weld_template = """result(
    for(
        iter({array}, {slice_start}, {slice_stop}, {slice_step}),
        appender[{type}],
        |b: appender[{type}], i: i64, e: {type}| 
            merge(b, n)
    )  
)"""

    weld_obj.weld_code = weld_template.format(array=obj_id,
                                              type=weld_type,
                                              slice_start='{}L'.format(slice_.start),
                                              slice_stop='{}L'.format(slice_.stop - slice_.start),
                                              slice_step='{}L'.format(slice_.step))

    return weld_obj


# TODO: could generalize weld_slice to accept slice with possible WeldObjects
def weld_tail(array, length, n):
    """Return the last n elements.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Array to select from.
    length : int or WeldObject
        Length of the array. Int if already known can simplify the computation.
    n : int
        How many values.

    Returns
    -------
    WeldObject
        Representation of the computation.

    """
    obj_id, weld_obj = create_weld_object(array)
    if isinstance(length, WeldObject):
        length = get_weld_obj_id(weld_obj, length)
        slice_start = '{} - {}L'.format(length, n)
        slice_stop = '{}'.format(length)
    else:
        slice_start = '{}L - {}L'.format(length, n)
        slice_stop = '{}L'.format(length)

    weld_template = """slice(
    {array},
    {slice_start},
    {slice_stop}
)"""

    weld_obj.weld_code = weld_template.format(array=obj_id,
                                              slice_start=slice_start,
                                              slice_stop=slice_stop)

    return weld_obj


def weld_array_op(array1, array2, result_type, operation):
    """Applies operation to each pair of elements in the arrays.

    Their lengths and types are assumed to be the same.
    TODO: what happens if not?

    Parameters
    ----------
    array1 : numpy.ndarray or WeldObject
        Input array.
    array2 : numpy.ndarray or WeldObject
        Second input array.
    result_type : WeldType
        Weld type of the result. Expected to be the same as both input arrays.
    operation : {'+', '-', '*', '/', '&&', '||', 'pow'}
        Which operation to apply. Note bitwise operations (not included) seem to be bugged at the LLVM level.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    obj_id1, weld_obj = create_weld_object(array1)
    obj_id2 = get_weld_obj_id(weld_obj, array2)

    if operation == 'pow':
        action = 'pow(e.$0, e.$1)'
    else:
        action = 'e.$0 {operation} e.$1'.format(operation=operation)

    weld_template = """result(
    for(zip({array1}, {array2}), 
        appender[{type}], 
        |b: appender[{type}], i: i64, e: {{{type}, {type}}}| 
            merge(b, {action})
    )
)"""

    weld_obj.weld_code = weld_template.format(array1=obj_id1,
                                              array2=obj_id2,
                                              type=result_type,
                                              action=action)

    return weld_obj


def weld_invert(array):
    """Inverts a bool array.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input data. Assumed to be bool data.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    obj_id, weld_obj = create_weld_object(array)

    weld_template = """result(
    for({array},
        appender[bool],
        |b: appender[bool], i: i64, e: bool|
            if(e, merge(b, false), merge(b, true))
    )
)"""

    weld_obj.weld_code = weld_template.format(array=obj_id)

    return weld_obj


def weld_iloc_int(array, index):
    """Retrieves the value at index.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input data. Assumed to be bool data.
    index : int
        The array index from which to retrieve value.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    obj_id, weld_obj = create_weld_object(array)

    weld_template = 'lookup({array}, {index}L)'

    weld_obj.weld_code = weld_template.format(array=obj_id,
                                              index=index)

    return weld_obj


def weld_iloc_indices(array, weld_type, indices):
    """Retrieve the values at indices.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input data. Assumed to be bool data.
    weld_type : WeldType
        The WeldType of the array data.
    indices : numpy.ndarray or WeldObject
        The indices to lookup.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    weld_obj = create_empty_weld_object()
    weld_obj_id_array = get_weld_obj_id(weld_obj, array)
    weld_obj_id_indices = get_weld_obj_id(weld_obj, indices)

    weld_template = """result(
    for({indices},
        appender[{type}],
        |b: appender[{type}], i: i64, e: i64|
            merge(b, lookup({array}, e))
    )
)"""

    weld_obj.weld_code = weld_template.format(array=weld_obj_id_array,
                                              indices=weld_obj_id_indices,
                                              type=weld_type)

    return weld_obj


def weld_iloc_indices_with_missing(array, weld_type, indices):
    """Retrieve the values at indices. Indices greater than array length get replaced with
    a corresponding-type missing value literal.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input data. Assumed to be bool data.
    weld_type : WeldType
        The WeldType of the array data.
    indices : numpy.ndarray or WeldObject
        The indices to lookup.

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    weld_obj = create_empty_weld_object()
    weld_obj_id_array = get_weld_obj_id(weld_obj, array)
    weld_obj_id_indices = get_weld_obj_id(weld_obj, indices)

    missing_literal = default_missing_data_literal(weld_type)
    if weld_type == WeldVec(WeldChar()):
        missing_literal = get_weld_obj_id(weld_obj, missing_literal)
    weld_template = """let len_array = len({array});
result(
    for({indices},
        appender[{type}],
        |b: appender[{type}], i: i64, e: i64|
            if(e > len_array,
                merge(b, {missing}),
                merge(b, lookup({array}, e))
            )
    )
)"""

    weld_obj.weld_code = weld_template.format(array=weld_obj_id_array,
                                              indices=weld_obj_id_indices,
                                              type=weld_type,
                                              missing=missing_literal)

    return weld_obj


def weld_element_wise_op(array, weld_type, scalar, operation):
    """Applies operation to each element in the array with scalar.

    Parameters
    ----------
    array : numpy.ndarray or WeldObject
        Input array.
    weld_type : WeldType
        Type of each element in the input array.
    scalar : {int, float, str, bool, bytes_}
        Value to compare with; must be same type as the values in the array. If not a str,
        it is casted to weld_type (allowing one to write e.g. native Python int).
    operation : {+, -, *, /, pow}

    Returns
    -------
    WeldObject
        Representation of this computation.

    """
    obj_id, weld_obj = create_weld_object(array)

    scalar = to_weld_literal(scalar, weld_type)

    if operation == 'pow':
        action = 'pow(e, {scalar})'.format(scalar=scalar)
    else:
        action = 'e {operation} {scalar}'.format(scalar=scalar,
                                                 operation=operation)

    weld_template = """result(
    for({array}, 
        appender[{type}], 
        |b: appender[{type}], i: i64, e: {type}| 
            merge(b, {action})
    )
)"""

    weld_obj.weld_code = weld_template.format(array=obj_id,
                                              type=weld_type,
                                              action=action)

    return weld_obj


# this function does the actual sorting
def _weld_sort(arrays, weld_types, indexes_to_sort, ascending=True):
    assert len(indexes_to_sort) == 1

    weld_obj_vec_of_struct = weld_arrays_to_vec_of_struct(arrays, weld_types)

    weld_obj = create_empty_weld_object()
    weld_obj_struct_id = get_weld_obj_id(weld_obj, weld_obj_vec_of_struct)

    types = '{{{}}}'.format(', '.join((str(weld_type) for weld_type in weld_types)))
    # TODO: update here when sorting on structs is possible
    ascending_sort_func = '{}'.format(', '.join(('e.${}'.format(i) for i in indexes_to_sort)))
    zero_literals = dict(enumerate([to_weld_literal(0, weld_type) for weld_type in weld_types]))
    descending_sort_func = '{}'.format(', '.join(('{} - e.${}'.format(zero_literals[i], i) for i in indexes_to_sort)))
    sort_func = ascending_sort_func if ascending else descending_sort_func

    weld_template = 'sort({struct}, |e: {types}| {sort_func})'

    weld_obj.weld_code = weld_template.format(struct=weld_obj_struct_id,
                                              types=types,
                                              sort_func=sort_func)

    return weld_obj


def weld_sort(arrays, weld_types, indexes_to_sort, readable_text, ascending=True):
    """Sort the arrays.

    Parameters
    ----------
    arrays : list of numpy.ndarray or WeldObject
        Arrays to put in a struct.
    weld_types : list of WeldType
        The Weld types of the arrays in the same order.
    indexes_to_sort : list of int
        Indexes on which to sort, e.g. the first 2 columns would be [0, 1].
    readable_text : str
        Explanatory string to add in the Weld placeholder.
    ascending : bool, optional

    Returns
    -------
    list of WeldObject
        Representation of this computation.

    """
    weld_obj_sort = _weld_sort(arrays, weld_types, indexes_to_sort, ascending)
    weld_obj_struct = weld_vec_of_struct_to_struct_of_vec(weld_obj_sort, weld_types)

    intermediate_result = LazyStructOfVecResult(weld_obj_struct, weld_types)
    dependency_name = Cache.cache_intermediate_result(intermediate_result, readable_text)

    weld_objects = extract_placeholder_weld_objects(dependency_name, len(weld_types), readable_text)

    return weld_objects
