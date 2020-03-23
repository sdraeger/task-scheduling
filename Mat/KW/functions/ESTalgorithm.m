function [Cost,t_ex,NumDropTask,T] = ESTalgorithm(data)

% Earliest Start Time Algorithm
% Takes tasks in data and assigns them to timeline using the EST algorithm.
% Input: data summarized below

% Output: 
% Cost - cost of assigning tasks to timeline using this algorithm
% t_ex - time tasks are executed
% T - sequence of tasks T(1) is first task assigned, T(N) last task
% NumDropTask - number of tasks that get dropped


N = data.N; % Number of tasks
K = data.K; % Number of timelines
s_task = data.s_task; % Start times (release-times) of tasks
w_task = data.w_task; % Weights of tasks. Bigger --> higher priority
deadline_task = data.deadline_task; % When task will be dropped
length_task = data.length_task; % How long tasks takes to complete
drop_task = data.drop_task; % Penalty for dropping task



[~,T] = sort(s_task); % Sort jobs based on starting times

% Assign those tasks to a timeline. 
[Cost,t_ex,NumDropTask] = MultiChannelSequenceScheduler(T,N,K,s_task,w_task,deadline_task,length_task,drop_task);
      %         [T,Cost.EST(monte,cnt.N),t_ex,NumDropTask] = EST_MultiChannel(N,K,s_task,w_task,deadline_task,length_task,drop_task);
      