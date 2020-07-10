from time import perf_counter
import numpy as np
import matplotlib.pyplot as plt

import gym
from gym.spaces import Discrete, Box, Space
from gym.utils import seeding

from baselines import logger
# from baselines import deepq

from util.generic import check_rng
from util.plot import plot_task_losses

from tree_search import TreeNode
from tasks import ReluDropGenerator


# Gym Spaces
class Sequence(Space):
    """Gym Space for index sequences."""

    def __init__(self, n):
        self.n = n
        super().__init__((n,), np.int)

    def sample(self):
        return self.np_random.permutation(self.n)

    def contains(self, x):
        return True if (np.sort(np.asarray(x, dtype=int)) == np.arange(self.n)).all() else False

    def __repr__(self):
        return f"Sequence({self.n})"

    def __eq__(self, other):
        return isinstance(other, Sequence) and self.n == other.n


class DiscreteSet(Space):
    """Gym Space for discrete, non-integral elements."""

    def __init__(self, elements):
        self.elements = np.sort(np.asarray(list(elements)).flatten())
        self.n = self.elements.size
        super().__init__((self.n,), self.elements.dtype)

    # @property
    # def n(self):
    #     return self.elements.size

    def sample(self):
        return self.np_random.choice(self.elements)

    def contains(self, x):
        return True if x in self.elements else False

    def __repr__(self):
        return f"DiscreteSet({self.elements})"

    def __eq__(self, other):
        return isinstance(other, DiscreteSet) and self.elements == other.elements


# Gym Environments
class BaseTaskingEnv(gym.Env):
    """Base environment for task scheduling."""

    def __init__(self, n_tasks, task_gen, n_ch, ch_avail_gen):
        self.n_tasks = n_tasks
        self.task_gen = task_gen

        self.n_ch = n_ch
        self.ch_avail_gen = ch_avail_gen

        self.tasks = None
        self.ch_avail = None
        self.node = None
        self.state = None
        self.reset()

        self.reward_range = (-float('inf'), 0)

        _low, _high = list(zip(task_gen.duration_lim, task_gen.t_release_lim, task_gen.slope_lim,
                               task_gen.t_drop_lim, task_gen.l_drop_lim, ))
        self._obs_low = np.broadcast_to(np.asarray(_low), (n_tasks, 5))
        self._obs_high = np.broadcast_to(np.asarray(_high), (n_tasks, 5))

    def reset(self, tasks=None, ch_avail=None):
        if len(tasks) != self.n_tasks or len(ch_avail) != self.n_ch:
            raise ValueError(f"Env requires {self.n_tasks} tasks and {self.n_ch} channels.")

        self.tasks = self.task_gen.rand_tasks(self.n_tasks) if tasks is None else tasks
        self.ch_avail = self.ch_avail_gen(self.n_ch) if ch_avail is None else ch_avail

        TreeNode._tasks = self.tasks
        TreeNode._ch_avail_init = self.ch_avail
        self.node = TreeNode()

    def step(self, action: list):
        raise NotImplementedError

    def render(self, mode='human'):
        if mode == 'human':
            fig_env, ax_env = plt.subplots(num='Task Scheduling Env', clear=True)
            plot_task_losses(self.tasks, ax=ax_env)

    def close(self):
        plt.close('all')


class SeqTaskingEnv(BaseTaskingEnv):
    """Tasking environment, entire sequence selected at once."""

    def __init__(self, n_tasks, task_gen, n_ch, ch_avail_gen):
        super().__init__(n_tasks, task_gen, n_ch, ch_avail_gen)
        self.observation_space = Box(self._obs_low, self._obs_high, dtype=np.float64)
        self.action_space = Sequence(self.n_tasks)

    def reset(self, tasks=None, ch_avail=None):
        super().reset(tasks, ch_avail)

        return np.array([task.gen_rep for task in self.tasks])

    def step(self, action: list):
        obs = None      # since Env is Done

        self.node.seq = action
        reward = -1 * self.node.l_ex

        return obs, reward, True, {}


class StepTaskingEnv(BaseTaskingEnv):
    """Tasking environment, tasks scheduled sequentially."""

    def __init__(self, n_tasks, task_gen, n_ch, ch_avail_gen):
        super().__init__(n_tasks, task_gen, n_ch, ch_avail_gen)
        _obs_low_step = np.concatenate((np.zeros((self.n_tasks, 1)), self._obs_low), axis=1)
        _obs_high_step = np.concatenate((np.ones((self.n_tasks, 1)), self._obs_high), axis=1)
        self.observation_space = Box(self._obs_low, self._obs_high, dtype=np.float64)

        self.loss_agg = None

    @property
    def action_space(self):
        return DiscreteSet(self.node.seq_rem)

    def reset(self, tasks=None, ch_avail=None):
        super().reset(tasks, ch_avail)

        self.loss_agg = self.node.l_ex

        self.state = np.array([[1] + task.gen_rep for task in self.tasks])
        return self.state

    def step(self, action: int):
        self.state[action][0] = 0       # Set first element of task vector to zero, indicating 'scheduled'.
        obs = self.state

        self.node.seq_extend([action])
        # reward = -1 * self.tasks[action].loss_func(self.node.t_ex[action])
        reward, self.loss_agg = self.loss_agg - self.node.l_ex, self.node.l_ex

        done = len(self.node.seq_rem) == 0

        return obs, reward, done, {}


def wrap_agent(env, agent):
    """Generate scheduling function by running an agent on a single environment episode."""

    def scheduling_agent(tasks, ch_avail):
        observation, reward, done = env.reset(tasks, ch_avail), 0, False
        while not done:
            agent.action_space = env.action_space       # FIXME: hacked to allow proper StepTasking behavior
            action = agent.act(observation, reward, done)
            observation, reward, done, info = env.step(action)

        return env.node.t_ex, env.node.ch_ex

    return scheduling_agent


def wrap_agent_run_lim(env, agent):
    """Generate scheduling function by running an agent on a single environment episode, enforcing max runtime."""

    def scheduling_agent(tasks, ch_avail, max_runtime):

        t_run = perf_counter()

        observation, reward, done = env.reset(tasks, ch_avail), 0, False
        while not done:
            agent.action_space = env.action_space
            action = agent.act(observation, reward, done)
            observation, reward, done, info = env.step(action)

        runtime = perf_counter() - t_run
        if runtime >= max_runtime:
            raise RuntimeError(f"Algorithm timeout: {runtime} > {max_runtime}.")

        return env.node.t_ex, env.node.ch_ex

    return scheduling_agent


class RandomAgent(object):
    """The world's simplest agent!"""
    def __init__(self, action_space):
        self.action_space = action_space

    def act(self, observation, reward, done):
        return self.action_space.sample()


# def train_random_agent(n_tasks, task_gen, n_ch, ch_avail_gen):
#     env = TaskingEnv(n_tasks, task_gen, n_ch, ch_avail_gen)
#     agent = RandomAgent(env.action_space)
#
#     return wrap_agent(env, agent)


def main():
    def ch_avail_generator(n_ch, rng=check_rng(None)):  # channel availability time generator
        return rng.uniform(0, 2, n_ch)

    params = {'n_tasks': 8,
              'task_gen': ReluDropGenerator(duration_lim=(3, 6), t_release_lim=(0, 4), slope_lim=(0.5, 2),
                                            t_drop_lim=(6, 12), l_drop_lim=(35, 50), rng=None),
              'n_ch': 2,
              'ch_avail_gen': ch_avail_generator}

    # env = SeqTaskingEnv(**params)
    env = StepTaskingEnv(**params)

    agent = RandomAgent(env.action_space)

    obs, reward, done = env.reset(), 0, False
    while not done:
        agent.action_space = env.action_space
        act = agent.act(obs, reward, done)
        observation, reward, done, info = env.step(act)
        print(reward)

    # act = deepq.learn(task_env,
    #                   network='mlp',
    #                   lr=1e-3,
    #                   total_timesteps=100000,
    #                   buffer_size=50000,
    #                   exploration_fraction=0.1,
    #                   exploration_final_eps=0.02,
    #                   print_freq=10,
    #                   )


if __name__ == '__main__':
    main()
