from math import isclose

import numpy as np

from task_scheduling.algorithms import branch_bound
from task_scheduling.tree_search import ScheduleNode, ScheduleNodeShift
from task_scheduling.util import evaluate_schedule
from task_scheduling.generators import problems as problem_gens


n_ch = 1
n_tasks = 8

ch_avail_lim = (-1, 1)

relu_lims = dict(duration_lim=(.03, .06), t_release_lim=(-4, 4), slope_lim=(0.5, 2),
                 t_drop_lim=(6, 12), l_drop_lim=(35, 50))


def test_argsort():
    """Check that seq=np.argsort(sch['t']) maps to an optimal schedule."""

    problem_gen = problem_gens.Random.continuous_relu_drop(n_tasks, n_ch, ch_avail_lim, **relu_lims)
    for i, (tasks, ch_avail) in enumerate(problem_gen(10)):
        print(f"{i}", end='\n')

        sch = branch_bound(tasks, ch_avail, verbose=True, rng=None)
        loss = evaluate_schedule(tasks, sch)

        seq_sort = np.argsort(sch['t'])
        node_sort = ScheduleNode(tasks, ch_avail, seq_sort)

        assert isclose(loss, node_sort.loss)


def test_shift():
    """Check accuracy of ScheduleNodeShift solution."""

    problem_gen = problem_gens.Random.continuous_relu_drop(n_tasks, n_ch, ch_avail_lim, **relu_lims)
    for i, (tasks, ch_avail) in enumerate(problem_gen(1000)):
        print(f"{i}", end='\n')

        seq = np.random.permutation(problem_gen.n_tasks)
        node = ScheduleNode(tasks, ch_avail, seq)
        node_s = ScheduleNodeShift(tasks, ch_avail, seq)

        assert np.allclose(node.sch['t'], node_s.sch['t'])
        assert abs(node.loss - node_s.loss) < 1e-9


def main():
    # test_argsort()
    test_shift()


if __name__ == '__main__':
    main()
