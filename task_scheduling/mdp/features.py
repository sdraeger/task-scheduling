"""Observation feature extractors and utilities."""

from operator import attrgetter
from warnings import warn

import numpy as np
from gymnasium.spaces import Box, Discrete

from task_scheduling.spaces import DiscreteSet, get_space_lims

feature_dtype = [("name", "<U32"), ("func", object), ("space", object)]


def param_features(param_spaces):
    """
    Create array of parameter features from task parameter spaces.

    Parameters
    ----------
    param_spaces : dict, optional
        Mapping of parameter name strings to gym.spaces.Space objects

    Returns
    -------
    ndarray
        Feature array with fields 'name', 'func', and 'space'.

    """
    data = []
    for name, space in param_spaces.items():
        data.append((name, attrgetter(name), space))

    return np.array(data, dtype=feature_dtype)


def encode_discrete_features(problem_gen):
    """Create parameter features, encoding DiscreteSet-typed parameters to Discrete-type."""
    data = []
    for name, space in problem_gen.task_gen.param_spaces.items():
        if isinstance(space, DiscreteSet):  # use encoding feature func, change space to Discrete

            def func(task):
                return np.flatnonzero(space.elements == getattr(task, name)).item()

            space = Discrete(len(space))
        else:
            func = attrgetter(name)

        data.append((name, func, space))

    return np.array(data, dtype=feature_dtype)


def _make_norm_func(func, space):
    low, high = get_space_lims(space)
    if np.isinf([low, high]).any():
        warn("Cannot make a normalizing `func` due to unbounded `space`.")
        return func

    def norm_func(task):
        return (func(task) - low) / (high - low)

    return norm_func


def normalize(features):
    """Make normalized features."""
    data = []
    for name, func, space in features:
        func = _make_norm_func(func, space)
        space = Box(0, 1, shape=space.shape, dtype=float)
        data.append((name, func, space))
    return np.array(data, dtype=feature_dtype)
