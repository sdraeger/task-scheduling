"""Base classes for MDP agent schedulers."""

from abc import ABC, abstractmethod

from task_scheduling.mdp.environments import Base as BaseEnv


class Base(ABC):
    """
    Base class for agent schedulers.

    Parameters
    ----------
    env : BaseEnv
        OpenAi gym environment.

    """

    def __init__(self, env):
        if not isinstance(env, BaseEnv):
            raise TypeError(f"`env` must be of type BaseEnv, got {type(env)}")
        self.env = env

    def __call__(self, tasks, ch_avail):
        """
        Call scheduler, produce execution times and channels.

        Parameters
        ----------
        tasks : Collection of task_scheduling.tasks.Base
            Tasks.
        ch_avail : Collection of float
            Channel availability times.

        Returns
        -------
        ndarray
            Task execution times.
        ndarray
            Task execution channels.

        """
        obs, _ = self.env.reset(tasks=tasks, ch_avail=ch_avail)

        done = False
        while not done:
            action = self.predict(obs)
            obs, reward, done, truncated, info = self.env.step(action)

        return self.env.node.sch

    @abstractmethod
    def predict(self, obs):
        """
        Take an action given an observation.

        Parameters
        ----------
        obs : array_like
            Observation.

        Returns
        -------
        int or array_like
            Action.

        """
        raise NotImplementedError

    def summary(self):
        out = "Env:" f"\n{self._print_env()}"
        return out

    def _print_env(self):
        if isinstance(self.env, BaseEnv):
            return self.env.summary()
        else:
            return str(self.env)


class RandomAgent(Base):
    """Uniformly random actor."""

    def predict(self, obs):
        action_space = self.env.action_space
        # action_space = self.env.infer_action_space(obs)

        return action_space.sample(), None


class BaseLearning(Base):
    """
    Base class for learning schedulers.

    Parameters
    ----------
    env : BaseEnv
        OpenAi gym environment.
    model
        The learning object.
    learn_params : dict, optional
        Parameters used by the `learn` method.

    """

    _learn_params_default = {}

    def __init__(self, env, model, learn_params=None):
        self.model = model
        super().__init__(env)

        self._learn_params = self._learn_params_default.copy()
        if learn_params is None:
            learn_params = {}
        self.learn_params = learn_params  # invoke property setter

        self.frozen = False  # set `True` to disable learning in `results` subpackage

    @property
    def learn_params(self):
        return self._learn_params

    @learn_params.setter
    def learn_params(self, params):
        self._learn_params.update(params)

    @abstractmethod
    def learn(self, n_gen, verbose=0):
        """
        Learn from the environment.

        Parameters
        ----------
        n_gen : int
            Number of problems to generate data from.
        verbose : int, optional
            Progress print-out level.

        """
        raise NotImplementedError

    @abstractmethod
    def reset(self, *args, **kwargs):
        """Reset the learner."""
        raise NotImplementedError

    def summary(self):
        str_model = f"Model:" f"\n{self._print_model()}"
        return super().summary() + "\n\n" + str_model

    def _print_model(self):
        return f"```\n" f"{str(self.model)}\n" f"```"
