clearvars
close all

FLAG.profile = 1;
FLAG.save = 0;
FLAG.check = 0;
FLAG.FixedPriority = 0; % Used to keep same inputs to sequence-schedulers for all algorithms
                        % Something is broken here. EST is doing better
                        % than BB, but checked for same inputs get same
                        % answer.
if FLAG.profile
    profile clear
    profile on -history
end

seed = 12307;
rng(seed)

addpath('./functions/')
addpath('./TaskSelectionSchedulingMultichannelRadar/')


approach_string{1} = 'EST';
% approach_string{2} = 'BB';
approach_string{2} = 'NN_Single';
% approach_string{2} = 'MCTS';
% approach_string{3} = 'NN'; % BB, EST, NN
% approach_string{3} = 'BB';

K = 1; % Number of timelines


%% Setup Supervised Learning Function

mode_stack = 'LIFO';
RP = 0.040; % Resourse Period in ms
Tmax = 30; % Maximum time of simulation in secondes

%% Generate Search Tasks
SearchParams.NbeamsPerRow = [28 29 14 9 10 9 8 7 6];
SearchParams.DwellTime = [36 36 36 18 18 18 18 18 18]*1e-3;
SearchParams.RevistRate = [2.5 5 5 5 5 5 5 5 5]; 
SearchParams.RevistRateUB = SearchParams.RevistRate + 1; % Upper Bound on Revisit Rate
SearchParams.Penalty = 100*ones(size(SearchParams.RevistRate)); % Penalty for exceeding UB
SearchParams.Slope = 1./SearchParams.RevistRate;
Nsearch = sum(SearchParams.NbeamsPerRow);
SearchParams.JobDuration = [];
SearchParams.JobSlope = [];
for jj = 1:length(SearchParams.NbeamsPerRow)
   SearchParams.JobDuration = [ SearchParams.JobDuration  ; repmat( SearchParams.DwellTime(jj), SearchParams.NbeamsPerRow(jj), 1)];
   SearchParams.JobSlope = [ SearchParams.JobSlope  ; repmat( SearchParams.Slope(jj), SearchParams.NbeamsPerRow(jj), 1)];; 
end


%% Generate Track Tasks
Ntrack = 10;

% Spawn tracks with uniformly distributed ranges and velocity
MaxRangeNmi = 200; %
MaxRangeRateMps = 343; % Mach 1 in Mps is 343


truth.rangeNmi = MaxRangeNmi*rand(Ntrack,1);
truth.rangeRateMps = 2*MaxRangeRateMps*rand(Ntrack,1) - MaxRangeRateMps ;

TrackParams.DwellTime = [18 18 18]*1e-3;
TrackParams.RevisitRate = [0.5 1 4];
TrackParams.RevisitRateUB = TrackParams.RevisitRate * 1.5;
TrackParams.Penalty = 100*ones(size(TrackParams.DwellTime));
TrackParams.Slope = 1./TrackParams.RevisitRate;
TrackParams.JobDuration = [];
TrackParams.JobSlope = [];
for jj = 1:Ntrack
    if  truth.rangeNmi(jj) <= 50
        TrackParams.JobDuration = [TrackParams.JobDuration; TrackParams.DwellTime(1)   ];
        TrackParams.JobSlope = [TrackParams.JobSlope;  TrackParams.Slope(1) ];
    elseif truth.rangeNmi(jj) > 50 &&  abs(truth.rangeRateMps(jj)) >= 100
        
    else
        
    end
    
end  



track.duration = 18e-3; % 5 ms (maybe 9 ms)
t_drop_track = zeros(Ntrack,1);


% Create Tiered Revisit rates
% Tier 1 anything close by
tier_RR = [0.5 1 4];
% tier_RR = [RP*1,RP*2,RP*4];
t_drop_track( truth.rangeNmi <= 50 ) = tier_RR(1); % 1 second revisit rate

% Tier 2 far away and fast
t_drop_track( truth.rangeNmi > 50 &  abs(truth.rangeRateMps) >= 100  ) = tier_RR(2); % 1 second revisit rate

% Tier 3 far away and slow
t_drop_track( truth.rangeNmi > 50 &  abs(truth.rangeRateMps) < 100  ) = tier_RR(3); % 1 second revisit rate

w_track = 1./t_drop_track;

plot_en = 1;
if plot_en
    figure(1); clf; hold all; grid on;
    tt = 0:01:3;
    plot(tt,cost_linear(tt, SearchParams.Slope' ,0))
    plot(tt,cost_linear(tt, 1/tier_RR(1), 0))
    plot(tt,cost_linear(tt, 1/tier_RR(2), 0))
    plot(tt,cost_linear(tt, 1/tier_RR(3), 0))
    legend('Search','Track 1','Track 2', 'Track 3','Location','best')
    xlabel('Time (s)')
    ylabel('Cost')
    title('Cost vs. Time')
    pretty_plot(gcf)
end


N = 4;

loss_mc = zeros(Tmax/(RP/K),length(approach_string));
t_run_mc = zeros(Tmax/(RP/K),length(approach_string));

TaskSequence = zeros(N,Tmax/(RP/K),length(approach_string));
TaskExecution = zeros(N,Tmax/(RP/K),length(approach_string));
ChannelRecord = zeros(K,Tmax/(RP/K),length(approach_string));

% Load Required Neural Network
NNstring = sprintf('./NN_REPO/net_task_%i_K_%i_FINAL.mat',N,K);
if any(strcmpi(approach_string,'NN_single'))
    load(NNstring)
elseif any(strcmpi( approach_string ,'NN_Multiple'))
    load('./NN_REPO/net_task_8_K_2_FINAL.mat')
elseif any(strcmpi(approach_string,'MCTS'))
    load(NNstring)    
end


for IterAlg = 1:length(approach_string)
    
    %% Generate Data to be scheduled in each dwell
    
    % Initialize master stack
    % stack=java.util.Stack();
    stack = Rstack();
    job = struct('Id',0,'slope',[],'StartTime',0,'DropTime',[],'DropCost',0,'Duration',0,'Type',[],'Priority',0); % Place Holder for Job Description
    job_master = job;
    
    cnt = 1;
    for jj = 1:Nsearch
        job.Id = cnt;
        job.slope = SearchParams.JobSlope(jj);
        job.StartTime = 0;
        %     job.DropTime = t_drop_search;
        %     job.DropCost = c_drop_search;
        job.Duration = SearchParams.JobDuration(jj);
        if job.slope == 0.4 %Horizon Search
            job.Type = 'HS';
        else % Above horizon search (AHS)
            job.Type = 'AHS';
        end
        job.Priority = cost_linear(0,job.slope,job.StartTime); % Initially clock is 0
        stack.push(job);
        job_master(cnt) = job; cnt = cnt + 1;
    end
    
    LastSearchId = cnt-1; % Used to find surviellance frame times
    
    for jj = 1:Ntrack
        job.Id = cnt;
        job.slope = w_track(jj);
        job.StartTime = 0;
        %     job.DropTime = t_drop_track(jj);
        %     job.DropCost = c_drop_search;
        job.Duration = track.duration;        
        TrackIndex = find(w_track(jj) == unique(w_track));
        job.Type = ['T' num2str(TrackIndex)];
        job.Priority = cost_linear(0,job.slope,job.StartTime); % Initially clock is 0
        stack.push(job);
        job_master(cnt) = job; cnt = cnt + 1;
    end
    
    
    
    %% Begin Simulation Loop
    % Specify number of task to process at any given time
%     N = RP/search.duration;
%     N = 8;
    N_mc = 1;
    i_mc = 1; % Used for Monte Carlo index. set to 1 initially later add loop
    
%     N_alg = numel(fcn_search);
    N_alg = 1;
    
    
    X = [];
    Y = [];
    
%     JobRevistTime = cell(size(job_master,2),1);
    metrics.JobRevistCount = zeros(size(job_master,2),1);
    metrics.JobType = {job_master.Type};
 
    
    tstart = tic;
    
    iter = 1;
    ChannelAvailableTime = zeros(K,1);
    for timeSec = 0:RP/K:Tmax
        
        
        if min(ChannelAvailableTime) > timeSec % Don't schedule unless a channel is free
            continue
        end
        
        if mod(timeSec,RP*10) == 0
            fprintf('Time = %0.2f \n', timeSec)
        end
        
        % Reassess Track Priorities ( Need to reshuffle jobs based on current cost
        % of each delayed task )
        for n = 1:size(job_master,2)
            job_master(n).Priority = cost_linear(timeSec,job_master(n).slope,job_master(n).StartTime);
            if job_master(n).Priority == Inf
                job_master(n).Priority = -Inf; % Reassign to make lower priority
            end
        end        
        
        
        
        
        if sum([job_master.Priority] ~= -Inf) < N 
%             keyboard
            continue
        end
            
%         figure(111); clf; hold all;
%         plot([job_master.StartTime])
%         plot([job_master.Priority])
        

        if FLAG.FixedPriority == 1
            priorityIdx = [1:length(job_master)];
        else        
            [~,priorityIdx] = sort([job_master.Priority],'descend');
        end
        job_master = job_master(priorityIdx);
       
        fprintf('Iteration %i \n',iter)
        T = struct2table(job_master);
        if mod(timeSec,RP*10) == 0
            disp(T)
        end
        
        % Initially all task have same start time Take first Ntasks to schedule
        queue = job_master(1:N);
        job_master(1:N) = []; % Remove jobs being scheduled
        %     w = [queue.slope];
        s_task = [queue.StartTime]';
        d_task = [queue.Duration]';
        w_task = [queue.slope]';
        %     t_drop = [queue.DropTime;
        
        
        metrics.JobRevistCount([queue.Id]) = metrics.JobRevistCount([queue.Id]) + 1;
        for n = 1:N
            JobRevistTime{ queue(n).Id }( metrics.JobRevistCount(queue(n).Id) )     = timeSec;
        end
        
        
        queueID(:,iter,IterAlg)= [queue.Id];
        queueRecord{iter,IterAlg} = queue;
        
        %     metrics.JobRevistTime( [queue.Id] ,metrics.JobRevistCount([queue.Id]) ) = timeSec;
        
        
        % Anonymous functions can be slowwwwww ... probably can vectorize the call
        % to this function to speed things up
        l_task = cell(N,1);
        for n = 1:N
            l_task{n} = @(t) cost_linDrop(t, queue(n).slope ,  queue(n).StartTime  ,  queue(n).DropTime  ,  queue(n).DropCost );
        end
        
        % Schedule Tasks using BB and generate relevant sampled data
        for i_a = 1:N_alg
                       
            drop_task = zeros(N,1); deadline_task = 100*ones(N,1);
            [loss,t_run,T,t_ex,ChannelAvailableTime] = PerformTaskAssignment(approach_string,IterAlg,N,K,s_task,w_task,d_task,deadline_task,drop_task,RP,ChannelAvailableTime);
                        
            %         [t_ex,loss,t_run,Xnow,Ynow] = fcn_search{i_a}(s_task,d_task,l_task,timeSec);
            
            loss_mc(iter,IterAlg) = loss;
            t_run_mc(iter,IterAlg) = t_run;
            TaskSequence(:,iter,IterAlg) = T(1:N);
            TaskExecution(:,iter,IterAlg) = t_ex;
            ChannelRecord(:,iter,IterAlg) = ChannelAvailableTime;
            
            if exist('Xnow')
                X = cat(3,X,Xnow);
                Y = [Y; Ynow];
            end
        end
        
        
        job_type = [queue.Type];
        occupancy.search(iter) = sum(job_type == 'S')/N;
        occupancy.track(iter) = sum(job_type == 'T')/N;
        
        [~,sortIdx] = sort(t_ex);
        
        new_job = struct('Id',0,'slope',[],'StartTime',0,'DropTime',[],'DropCost',0,'Duration',0,'Type',[],'Priority',0); % Place Holder for Job Description
        
        for n = 1:N
            new_job(n).Id = queue(sortIdx(n)).Id;
            new_job(n).StartTime = t_ex(sortIdx(n)) + queue(sortIdx(n)).Duration ;
            new_job(n).slope = queue(sortIdx(n)).slope;
            new_job(n).DropTime = queue(sortIdx(n)).DropTime;
            new_job(n).DropCost = queue(sortIdx(n)).DropCost;
            new_job(n).Duration = queue(sortIdx(n)).Duration;
            new_job(n).Type = queue(sortIdx(n)).Type;
        end
        %     for n = 1:N
        %        new_job(n).Priority = cost_linear(timeSec,new_job(n).slope,new_job(n).StartTime);
        %     end
        
        
        job_master = [job_master, new_job];
        
        
        
        %     formatJobsFcn(job_master)
        
        
        
        %     disp( [job_master.StartTime] )
        %     disp({job_master.Type})
        
        % Update Track Truth Positions
        pos = truth.rangeNmi * 1852;
        vel = truth.rangeRateMps;
        truth.rangeNmi = ( pos + (timeSec + RP)*vel ) /1852;
        
        
        iter = iter + 1;
        
    end
    
    TimeElapsed(IterAlg) = toc(tstart);
    
    fprintf('Elapsed Time %f \n\n',TimeElapsed(IterAlg))
    
    
    %% Diagnostics    
    for n = 1:length(metrics.JobRevistCount)
        try 
            metrics.RevisitRate(n) =  mean( diff([JobRevistTime{n}] ));
        catch
            metrics.RevisitRate(n) = 0;
        end
    end
    

    metrics.UniqueJobTypes = unique(metrics.JobType);       
    for jj = 1:length(metrics.UniqueJobTypes)
       JobIndex = find( strcmpi(metrics.JobType,metrics.UniqueJobTypes(jj)) );
       metrics.JobTypeRR(jj) = mean(metrics.RevisitRate(JobIndex));
    end
    
    
%     LastSearchId = min(LastSearchId,length(JobRevistTime));
    SurvFrameTime = JobRevistTime{LastSearchId};
    AvgSurvFrameTime = mean(diff(SurvFrameTime));
    
    desiredRevisitRate = 1./[job_master.slope];
    desiredRevisitRate([job_master.Id]) = desiredRevisitRate; % Sort by Id number 1:NumIds
    
    RawUtility = desiredRevisitRate - metrics.RevisitRate;
    RawPenalty  = RawUtility;
    RawPenalty(RawPenalty > 0) = 0; % Pass/Fail anything that's positive ignore
    TotalUtility = sum(RawUtility); % More positive is better
    TotalPenalty = sum(RawPenalty);    % Less negative is better
    penalty_vec(IterAlg) = TotalPenalty;
    
    
    fprintf('Total Penalty %f \n\n',TotalPenalty)
    
    
    
    
    figure(2 + (IterAlg-1)*4); clf;
    % subplot(2,2,1)
    hold all; grid on;
    plot(occupancy.search)
    plot(occupancy.track)
    legend('Search','Track')
    xlabel('Iteration')
    ylabel('Occupancy')
    title(['Job Occupancy: ' approach_string{IterAlg}])
    pretty_plot(gcf)
    fname = ['.\Figures\' approach_string{IterAlg} '_Job_Occupancy'];
    if FLAG.save
        saveas(gcf,[fname '.fig'])
        saveas(gcf,[fname '.epsc'])
    end
    
    figure(3 + (IterAlg-1)*4); clf;
    % subplot(2,2,2)
    hold all; grid on;
    for n = 1:size(JobRevistTime,2)
        plot( JobRevistTime{n} , ones(size(JobRevistTime{n})) + (n-1) ,'x' )
    end
    xlabel('Revist Time (s)')
    ylabel('Job Id')
    title(['Job Revisit Time: ' approach_string{IterAlg} ])
    pretty_plot(gcf)
    if FLAG.save
        fname = ['.\Figures\' approach_string{IterAlg} '_Job_Revisit_Time'];
        saveas(gcf,[fname '.fig'])
        saveas(gcf,[fname '.epsc'])
    end
    
    figure(4 + (IterAlg-1)*4); clf;
    % subplot(2,2,[3]);
    cla; hold all;
    plot(metrics.RevisitRate,[1:size(metrics.RevisitRate,2)],'bd','MarkerSize',8,'LineWidth',3)
    plot(1./[job_master.slope],[job_master.Id],'ro')
    
    xlabel('Revist Rate (s)')
    ylabel('Job Id')
    grid on;
    aa = axis;
    xlim([0 aa(2)]);
    xpos = aa(2)*.25;
    ypos = (aa(4) - aa(3))*.25 + aa(3);
    text(AvgSurvFrameTime,LastSearchId,['Avg. Surv. Frame Time = ' num2str(AvgSurvFrameTime) '\rightarrow'],'LineWidth',6,'HorizontalAlignment','right')
    title(sprintf('Job Revisit Rate %s \n Utility = %0.2f,  Penalty = %0.2f',approach_string{IterAlg},TotalUtility,TotalPenalty))
    legend('Achieved Rate','Desired Rate')
    pretty_plot(gcf)
    if FLAG.save
        fname = ['.\Figures\' approach_string{IterAlg} '_Achieved_Rate'];
        saveas(gcf,[fname '.fig'])
        saveas(gcf,[fname '.epsc'])
    end
    
    figure(5 + (IterAlg-1)*4); clf;
    % subplot(2,2,4);
    cla;
    plot([job_master.slope],[job_master.Id],'o')
    xlabel('Cost Slope')
    ylabel('Job Id')
    title(['Final Job Priority: ' approach_string{IterAlg}])
    pretty_plot(gcf)
    if FLAG.save
        fname = ['.\Figures\' approach_string{IterAlg} '_Job_Priority'];
        saveas(gcf,[fname '.fig'])
        saveas(gcf,[fname '.epsc'])
    end
end

%% Final Plots
% leg_str{1} = 'EST';
% leg_str{2} = 'NN';
% leg_str{3} = 'BB';
% penalty_vec = [-0.128465 -0.030758 -0.015145];
leg_str = approach_string;
shape = 'oxsd';
time_vec = TimeElapsed./(iter-1)*1000;
% time_vec = [0.547488 3.0350  27.202844]/51*1000;

figure(6); clf;
hold all; grid on
for jj = 1:length(approach_string)
    plot(time_vec(jj),-penalty_vec(jj),shape(jj),'MarkerSize',10,'LineWidth',3)
end
% plot(time_vec(2),-penalty_vec(2),'x','MarkerSize',10,'LineWidth',3)
% plot(time_vec(3),-penalty_vec(3),'s','MarkerSize',10,'LineWidth',3)
legend(leg_str,'Location','best')
ylabel('Cumulative Penalty')
xlabel('Computation Time (ms)')
title('Computation Time vs. Penalty (Closer to 0 \rightarrow Better Performance)')

pretty_plot(gcf)
if FLAG.save
    fname = ['.\Figures\' 'Compute_Time'];
    saveas(gcf,[fname '.fig'])
    saveas(gcf,[fname '.epsc'])
end


figure(7); clf;
AvgCost = mean(loss_mc);
for jj = 1:size(loss_mc,2)
    AvgCost(jj) = mean( loss_mc( loss_mc(:,jj) > 0,jj));
end
AvgTime = mean(t_run_mc)*1000;
clf;
hold all; grid on
for jj = 1:length(approach_string)
    plot(AvgTime(jj),AvgCost(jj),shape(jj),'MarkerSize',10,'LineWidth',3)
end
% plot(time_vec(2),-penalty_vec(2),'x','MarkerSize',10,'LineWidth',3)
% plot(time_vec(3),-penalty_vec(3),'s','MarkerSize',10,'LineWidth',3)
legend(leg_str,'Location','best')
ylabel('Cost')
xlabel('Computation Time (ms)')
title('Computation Time vs. Cost')

pretty_plot(gcf)
if FLAG.save
    fname = ['.\Figures\' 'Cost_vs_Time'];
    saveas(gcf,[fname '.fig'])
    saveas(gcf,[fname '.epsc'])
end



%%

if FLAG.profile
    profile viewer
end
