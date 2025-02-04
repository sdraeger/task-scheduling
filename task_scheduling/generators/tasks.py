"""
Generator objects for tasks.

Notes
-----
Assumes all tasks are instances of the same class. Heterogeneous task types will be supported in a
future version.

"""

from abc import ABC, abstractmethod
from collections import deque
from types import MethodType
from typing import Collection

import numpy as np
import pandas as pd
from gymnasium import spaces

from task_scheduling import tasks as task_types
from task_scheduling.base import RandomGeneratorMixin
from task_scheduling.spaces import DiscreteSet


class Base(RandomGeneratorMixin, ABC):
    """
    Base class for generation of task objects.

    Parameters
    ----------
    cls_task : class
        Class for instantiating task objects.
    param_spaces : dict, optional
        Mapping of parameter name strings to gymnasium.spaces.Space objects
    rng : int or RandomState or Generator, optional
        Random number generator seed or object.

    """

    def __init__(self, cls_task, param_spaces=None, rng=None):
        super().__init__(rng)
        self.cls_task = cls_task

        if param_spaces is None:
            self.param_spaces = {
                name: spaces.Box(-np.inf, np.inf, shape=(), dtype=float)
                for name in self.cls_task.param_names
            }
        else:
            self.param_spaces = param_spaces

    @abstractmethod
    def __call__(self, n_tasks, rng=None):
        """
        Generate tasks.

        Parameters
        ----------
        n_tasks : int
            Number of tasks.
        rng : int or RandomState or Generator, optional
            Random number generator seed or object.

        Returns
        -------
        Generator

        """
        raise NotImplementedError

    def summary(self):
        cls_str = self.__class__.__name__
        return f"{cls_str}\n---"


class BaseIID(Base, ABC):
    """Base class for generation of independently and identically distributed task objects."""

    def __call__(self, n_tasks, rng=None):
        """
        Randomly generate tasks.

        Parameters
        ----------
        n_tasks : int
            Number of tasks.
        rng : int or RandomState or Generator, optional
            Random number generator seed or object.

        Returns
        -------
        Generator

        """
        rng = self._get_rng(rng)
        for __ in range(n_tasks):
            yield self.cls_task(**self._param_gen(rng))

    @abstractmethod
    def _param_gen(self, rng):
        """Randomly generate task parameters."""
        raise NotImplementedError


class GenericIID(BaseIID):
    """
    Generic generator of independently and identically distributed random task objects.

    Parameters
    ----------
    cls_task : class
        Class for instantiating task objects.
    param_gen : callable
        Invoked with 'self' argument, for use as the '_param_gen' method.
    param_spaces : dict, optional
        Mapping of parameter name strings to gymnasium.spaces.Space objects
    rng : int or RandomState or Generator, optional
        Random number generator seed or object.

    """

    def __init__(self, cls_task, param_gen, param_spaces=None, rng=None):
        super().__init__(cls_task, param_spaces, rng)
        self._param_gen_init = MethodType(param_gen, self)

    def _param_gen(self, rng):
        return self._param_gen_init(rng)

    @classmethod
    def linear_drop(cls, param_gen, param_spaces=None, rng=None):
        return cls(task_types.LinearDrop, param_gen, param_spaces, rng)


class ContinuousUniformIID(BaseIID):
    """
    Random generator of I.I.D. tasks with independently uniform continuous parameters.

    Parameters
    ----------
    cls_task : class
        Class for instantiating task objects.
    param_lims : dict of Collection
        Mapping of parameter name strings to 2-tuples of parameter limits.
    rng : int or RandomState or Generator, optional
        Random number generator seed or object.

    """

    def __init__(self, cls_task, param_lims, rng=None):
        param_spaces = {
            name: spaces.Box(*param_lims[name], shape=(), dtype=float)
            for name in cls_task.param_names
        }
        super().__init__(cls_task, param_spaces, rng)

        self.param_lims = param_lims

    def _param_gen(self, rng):
        """Randomly generate task parameters."""
        return {name: rng.uniform(*self.param_lims[name]) for name in self.cls_task.param_names}

    def __eq__(self, other):
        if isinstance(other, ContinuousUniformIID):
            return self.cls_task == other.cls_task and self.param_lims == other.param_lims
        else:
            return NotImplemented

    def summary(self):
        str_ = super().summary()
        str_ += f"\nTask class: {self.cls_task.__name__}"

        df = pd.DataFrame(
            {name: self.param_lims[name] for name in self.cls_task.param_names},
            index=pd.CategoricalIndex(["low", "high"]),
        )
        df_str = df.to_markdown(tablefmt="github", floatfmt=".3f")

        str_ += f"\n\n{df_str}"
        return str_

    @classmethod
    def linear(cls, duration_lim=(3, 6), t_release_lim=(0, 4), slope_lim=(0.5, 2), rng=None):
        """Construct `Linear` task objects."""
        param_lims = dict(duration=duration_lim, t_release=t_release_lim, slope=slope_lim)
        return cls(task_types.Linear, param_lims, rng)

    @classmethod
    def linear_drop(
        cls,
        duration_lim=(3, 6),
        t_release_lim=(0, 4),
        slope_lim=(0.5, 2),
        t_drop_lim=(6, 12),
        l_drop_lim=(35, 50),
        rng=None,
    ):
        """Construct `LinearDrop` task objects."""
        param_lims = dict(
            duration=duration_lim,
            t_release=t_release_lim,
            slope=slope_lim,
            t_drop=t_drop_lim,
            l_drop=l_drop_lim,
        )
        return cls(task_types.LinearDrop, param_lims, rng)

    @classmethod
    def exp(
        cls, duration_lim=(1, 2), t_release_lim=(-1, 1), a_lim=(0.5, 1.5), b_lim=(1, 5), rng=None
    ):
        """Construct `Exponential` task objects."""
        param_lims = dict(duration=duration_lim, t_release=t_release_lim, a=a_lim, b=b_lim)
        return cls(task_types.Exponential, param_lims, rng)


class DiscreteIID(BaseIID):
    """
    Random generator of I.I.D. tasks with independent discrete-valued parameters.

    Parameters
    ----------
    cls_task : class
        Class for instantiating task objects.
    param_probs: dict of str to dict
        Mapping of parameter name strings to dictionaries mapping values to probabilities.
    rng : int or RandomState or Generator, optional
        Random number generator seed or object.

    """

    def __init__(self, cls_task, param_probs, rng=None):
        param_spaces = {
            name: DiscreteSet(list(param_probs[name].keys())) for name in cls_task.param_names
        }
        super().__init__(cls_task, param_spaces, rng)

        self.param_probs = param_probs

    def _param_gen(self, rng):
        """Randomly generate task parameters."""
        return {
            name: rng.choice(
                list(self.param_probs[name].keys()), p=list(self.param_probs[name].values())
            )
            for name in self.cls_task.param_names
        }

    def __eq__(self, other):
        if isinstance(other, DiscreteIID):
            return self.cls_task == other.cls_task and self.param_probs == other.param_probs
        else:
            return NotImplemented

    def summary(self):
        str_ = super().summary()
        str_ += f"\nTask class: {self.cls_task.__name__}"
        for name in self.cls_task.param_names:
            s = pd.DataFrame(
                {name: self.param_probs[name].keys(), "Pr": self.param_probs[name].values()}
            )
            str_ += f"\n\n{s.to_markdown(tablefmt='github', floatfmt='.3f', index=False)}"

        return str_

    @classmethod
    def linear_uniform(
        cls, duration_vals=(3, 6), t_release_vals=(0, 4), slope_vals=(0.5, 2), rng=None
    ):
        """Construct `Linear` task objects."""
        param_probs = {
            "duration": dict(zip(duration_vals, np.ones(len(duration_vals)) / len(duration_vals))),
            "t_release": dict(
                zip(t_release_vals, np.ones(len(t_release_vals)) / len(t_release_vals))
            ),
            "slope": dict(zip(slope_vals, np.ones(len(slope_vals)) / len(slope_vals))),
        }
        return cls(task_types.Linear, param_probs, rng)

    @classmethod
    def linear_drop_uniform(
        cls,
        duration_vals=(3, 6),
        t_release_vals=(0, 4),
        slope_vals=(0.5, 2),
        t_drop_vals=(6, 12),
        l_drop_vals=(35, 50),
        rng=None,
    ):
        """Construct `LinearDrop` task objects."""
        param_probs = {
            "duration": dict(zip(duration_vals, np.ones(len(duration_vals)) / len(duration_vals))),
            "t_release": dict(
                zip(t_release_vals, np.ones(len(t_release_vals)) / len(t_release_vals))
            ),
            "slope": dict(zip(slope_vals, np.ones(len(slope_vals)) / len(slope_vals))),
            "t_drop": dict(zip(t_drop_vals, np.ones(len(t_drop_vals)) / len(t_drop_vals))),
            "l_drop": dict(zip(l_drop_vals, np.ones(len(l_drop_vals)) / len(l_drop_vals))),
        }
        return cls(task_types.LinearDrop, param_probs, rng)


class Fixed(Base, ABC):
    """
    Permutation task generator.

    Parameters
    ----------
    tasks : Collection of task_scheduling.tasks.Base
        Tasks.
    param_spaces : dict, optional
        Mapping of parameter name strings to gymnasium.spaces.Space objects
    rng : int or RandomState or Generator, optional
        Random number generator seed or object.

    """

    def __init__(self, tasks, param_spaces=None, rng=None):
        cls_task = tasks[0].__class__
        if not all(isinstance(task, cls_task) for task in tasks[1:]):
            raise TypeError("All tasks must be of the same type.")

        if param_spaces is None:
            param_spaces = {
                name: DiscreteSet([getattr(task, name) for task in tasks])
                for name in cls_task.param_names
            }

        super().__init__(cls_task, param_spaces, rng)

        self.tasks = list(tasks)

    @abstractmethod
    def __call__(self, n_tasks, rng=None):
        """
        Generate fixed tasks.

        Parameters
        ----------
        n_tasks : int
            Number of tasks.
        rng : int or RandomState or Generator, optional
            Random number generator seed or object.

        Returns
        -------
        Generator

        """
        raise NotImplementedError

    def __eq__(self, other):
        if isinstance(other, Fixed):
            return self.tasks == other.tasks
        else:
            return NotImplemented

    @classmethod
    def _task_gen_to_fixed(cls, n_tasks, task_gen, rng):
        tasks = list(task_gen(n_tasks, rng))
        return cls(tasks, task_gen.param_spaces, rng)

    @classmethod
    def continuous_linear_drop(cls, n_tasks, rng=None, **task_gen_kwargs):
        task_gen = ContinuousUniformIID.linear_drop(**task_gen_kwargs)
        return cls._task_gen_to_fixed(n_tasks, task_gen, rng)

    @classmethod
    def discrete_linear_drop(cls, n_tasks, rng=None, **task_gen_kwargs):
        task_gen = DiscreteIID.linear_drop_uniform(**task_gen_kwargs)
        return cls._task_gen_to_fixed(n_tasks, task_gen, rng)


class Deterministic(Fixed):
    def __call__(self, n_tasks, rng=None):
        """Yield tasks in deterministic order."""
        if n_tasks != len(self.tasks):
            raise ValueError(f"Number of tasks must be {len(self.tasks)}.")

        for task in self.tasks:
            yield task


class Permutation(Fixed):
    def __call__(self, n_tasks, rng=None):
        """Yield tasks in a uniformly random order."""
        if n_tasks != len(self.tasks):
            raise ValueError(f"Number of tasks must be {len(self.tasks)}.")

        rng = self._get_rng(rng)
        for task in rng.permutation(self.tasks).tolist():
            yield task


class Dataset(Fixed):  # FIXME: inherit from `Base`??
    """
    Generator of tasks from a dataset.

    Parameters
    ----------
    tasks : Sequence of task_scheduling.tasks.Base
        Stored tasks to be yielded.
    shuffle : bool, optional
        Shuffle task during instantiation.
    repeat : bool, optional
        Allow tasks to be yielded more than once.
    param_spaces : dict, optional
        Mapping of parameter name strings to gymnasium.spaces.Space objects
    rng : int or RandomState or Generator, optional
        Random number generator seed or object.

    """

    def __init__(self, tasks, shuffle=False, repeat=False, param_spaces=None, rng=None):
        super().__init__(tasks, param_spaces, rng)

        self.tasks = deque()
        self.add_tasks(tasks)

        if shuffle:
            self.shuffle()

        self.repeat = repeat

    def add_tasks(self, tasks):
        """Add tasks to the queue."""
        if isinstance(tasks, Collection):
            self.tasks.extendleft(tasks)
        else:
            self.tasks.appendleft(tasks)  # for single tasks

    def shuffle(self, rng=None):
        """Shuffle the task queue."""
        rng = self._get_rng(rng)
        self.tasks = deque(rng.permutation(self.tasks))

    def __call__(self, n_tasks, rng=None):
        """
        Yield tasks from the queue.

        Parameters
        ----------
        n_tasks : int
            Number of tasks.
        rng : int or RandomState or Generator, optional
            Random number generator seed or object.

        Returns
        -------
        Generator

        """
        for __ in range(n_tasks):
            if len(self.tasks) == 0:
                raise ValueError("Task generator data has been exhausted.")

            task = self.tasks.pop()
            if self.repeat:
                self.tasks.appendleft(task)

            yield task
