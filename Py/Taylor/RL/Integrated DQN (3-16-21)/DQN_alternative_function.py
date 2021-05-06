def DQN_alternative_function(number_of_tasks,number_of_features,zero_cost_reward,order_of_features,
                         epsilon,epsilon_decay,epsilon_minimum,gamma,gamma_decay,gamma_minimum,
                         number_of_episodes,replay_memory_size,minimum_replay_memory_size,minibatch_size,update_target_every,batch_size):
    
    
    #%% Import Statements:
    
    import collections
    import matplotlib.pyplot
    import numpy
    import random
    
    from cost_alternative import cost_function
    from EST import EST_function
    # from reward import reward_function
    from task_generator_Integrated import task_generator_function
    from tensorflow import keras
    
    
    #%% Definitions of Variables Based on User-Specified Inputs:
    
    r_N_index = order_of_features["Release Times"]
    w_N_index = order_of_features["Weights"]
    l_N_index = order_of_features["Lengths"]
    
    
    #%% Environment:
    
    class Scheduler:
    
        def action(self,action_value,action_vector_before):
    
            action_vector_after = action_vector_before
    
            count = 0
    
            for i in range(len(action_vector_before)):
    
                if action_vector_before[i] > 0:
    
                    count += 1
    
            action_vector_after[action_value] = 1+count
    
            return action_vector_after
    
    class SchedulerEnv:
    
        observation_space_size = (1,number_of_tasks*number_of_features+number_of_tasks)
        action_space_size = number_of_tasks
    
        def reset(self):
    
            observation = task_generator_function(number_of_tasks)
    
            action_vector = numpy.zeros(number_of_tasks)
    
            return observation, action_vector
    
        def step(self,observation,action_value,action_vector_before,step_penalty):
    
            observation_array = numpy.array(observation)
    
            r_N = observation_array[(r_N_index-1),:]
            w_N = observation_array[(w_N_index-1),:]
            l_N = observation_array[(l_N_index-1),:]
    
            action_vector_after = Scheduler.action(self,action_value,action_vector_before)
            action_vector_after_array = numpy.array(action_vector_after)
    
            cost = cost_function(r_N,w_N,l_N,action_vector_after_array)
    
            # reward = reward_function(cost,zero_cost_reward)
            reward = -cost
            reward_with_penalty = reward-step_penalty
    
            new_observation = observation_array
    
            done = False # TASKS ARE SCHEDULED ONE-BY-ONE
    
            done_check = 0 in action_vector_after
    
            if done_check == False:
    
                done = True
    
            return reward_with_penalty, new_observation, done, action_vector_after
    
    env = SchedulerEnv()
    
    
    #%% DQN:
    
    class DQN:
    
        def __init__(self):
    
            #%% Main Model (Fit):
            self.model = self.create_model()
    
            #%% Target Model (Predict):
            self.target_model = self.create_model()
            self.target_model.set_weights(self.model.get_weights())
    
            #%% Replay Memory:
            self.replay_memory = collections.deque(maxlen=replay_memory_size)
    
            # Counter to Update Target Model:
            self.target_update_counter = 0
    
        def create_model(self):
    
            model = keras.models.Sequential()
    
            model.add(keras.layers.Dense(number_of_tasks*number_of_features+number_of_tasks,input_shape=(number_of_tasks*number_of_features+number_of_tasks,)))
            model.add(keras.layers.Activation('relu'))
    
            model.add(keras.layers.Dense(env.action_space_size,activation='linear'))
    
            model.compile(optimizer=keras.optimizers.Adam(lr=0.001),loss='mse') # metrics=['accuracy']
    
            return model
    
        def update_replay_memory(self,transition):
    
            self.replay_memory.append(transition)
    
        def train(self,terminal_state,step):
    
            if len(self.replay_memory) < minimum_replay_memory_size:
    
                return
    
            minibatch_before = random.sample(self.replay_memory,minibatch_size)
            minibatch_before_array = numpy.array(minibatch_before)
    
            minibatch_after_current_states = []
            minibatch_after_new_current_states = []
    
            for i in range(len(minibatch_before_array)):
    
                current_row = minibatch_before_array[i]
    
                current_state_in_current_row = current_row[0]
                new_current_state_in_current_row = current_row[3]
    
                current_action_vector = current_row[5]
                new_current_action_vector = current_row[6]
    
                r_N_in_current_state_in_current_row = current_state_in_current_row[r_N_index-1]
                w_N_in_current_state_in_current_row = current_state_in_current_row[w_N_index-1]
                l_N_in_current_state_in_current_row = current_state_in_current_row[l_N_index-1]
    
                r_N_in_new_current_state_in_current_row = new_current_state_in_current_row[r_N_index-1]
                w_N_in_new_current_state_in_current_row = new_current_state_in_current_row[w_N_index-1]
                l_N_in_new_current_state_in_current_row = new_current_state_in_current_row[l_N_index-1]
    
                current_state_row_to_append = numpy.concatenate((r_N_in_current_state_in_current_row,w_N_in_current_state_in_current_row,l_N_in_current_state_in_current_row,current_action_vector),axis=0)
                new_current_state_row_to_append = numpy.concatenate((r_N_in_new_current_state_in_current_row,w_N_in_new_current_state_in_current_row,l_N_in_new_current_state_in_current_row,new_current_action_vector),axis=0)
    
                minibatch_after_current_states.append(current_state_row_to_append)
                minibatch_after_new_current_states.append(new_current_state_row_to_append)
    
            current_states = numpy.array(minibatch_after_current_states)
            new_current_states = numpy.array(minibatch_after_new_current_states)
    
            current_q_values_all = self.model.predict(current_states)
            future_q_values_all = self.target_model.predict(new_current_states)
    
            X = []
            Y = []
    
            for index, (observation,action_value,reward,_,done,action_vector_before,action_vector_after) in enumerate(minibatch_before):
    
                r_N_in_current_state = observation[r_N_index-1]
                w_N_in_current_state = observation[w_N_index-1]
                l_N_in_current_state = observation[l_N_index-1]
    
                action_vector_before_in_current_state = action_vector_before
    
                current_state_to_append = numpy.concatenate((r_N_in_current_state,w_N_in_current_state,l_N_in_current_state,action_vector_before_in_current_state),axis=0)
    
                if not done:
    
                    max_future_q_value = numpy.max(future_q_values_all[index])
    
                    new_q_value = -reward+gamma*max_future_q_value # HEREHEREHERE!!!
    
                else:
    
                    new_q_value = -reward # HEREHEREHERE!!!
    
                current_q_values = current_q_values_all[index]
                current_q_values[action_value] = new_q_value
    
                X.append(current_state_to_append)
                Y.append(current_q_values)
    
            self.model.fit(numpy.array(X),numpy.array(Y),batch_size=minibatch_size,verbose=0,shuffle=False)
    
            if terminal_state:
    
                self.target_update_counter += 1
    
            if self.target_update_counter > update_target_every:
    
                self.target_model.set_weights(self.model.get_weights())
    
                self.target_update_counter = 0
    
        def get_q_values(self,current_state):
    
            return self.model.predict(numpy.reshape(numpy.array(current_state),env.observation_space_size))
    
    agent = DQN()
    
    
    #%% Training (DQN):
    
    episode_results_all = []
    
    episode_reward_all = []
    
    for episode in range(1,number_of_episodes+1):
    
        if episode % 1000 == 0: # HEREHEREHERE!!!
    
            print(f"\n\tEpisode: {episode}")
    
        episode_reward = 0
        episode_penalty = 0
        step = 1
    
        observation, action_vector_before = env.reset()
    
        observation_array = numpy.reshape(observation,(1,number_of_tasks*number_of_features))
        action_vector_before_array  = numpy.reshape(action_vector_before,(1,number_of_tasks))
    
        current_state = numpy.concatenate((observation_array,action_vector_before_array),axis=1)
    
        done = False
    
        while not done:
    
            check = 1
    
            step_penalty = 0
    
            if numpy.random.random() > epsilon:
    
                disposable_vector = agent.get_q_values(current_state)
    
                n_inf = float("-inf")
    
                while check > 0:
    
                    action_value = numpy.argmax(disposable_vector)
    
                    check = action_vector_before[action_value]
    
                    if check > 0:
    
                        step_penalty += 0.1 # HEREHEREHERE!!!
    
                        disposable_vector[0,action_value] = n_inf
    
            else:
    
                while check > 0:
    
                    action_value = numpy.random.randint(0,env.action_space_size)
    
                    check = action_vector_before[action_value]
    
            reward, new_observation, done, action_vector_after = env.step(observation,action_value,action_vector_before,step_penalty)
    
            episode_reward += reward
            episode_penalty += step_penalty
    
            transition = (observation,action_value,reward,new_observation,done,action_vector_before,action_vector_after)
    
            agent.update_replay_memory(transition)
    
            agent.train(done,step)
    
            new_observation_array = numpy.reshape(new_observation,(1,number_of_tasks*number_of_features))
            action_vector_after_array  = numpy.reshape(action_vector_after,(1,number_of_tasks))
    
            current_state = numpy.concatenate((new_observation_array,action_vector_after_array),axis=1)
    
            step += 1
    
        episode_results = current_state
        episode_results_all.append(episode_results)
    
        episode_reward_all.append(episode_reward)
    
        if episode < number_of_episodes-update_target_every:
            if epsilon > epsilon_minimum:
                epsilon *= epsilon_decay
                epsilon = max(epsilon_minimum,epsilon)
        else:
            epsilon = epsilon_minimum # HEREHEREHERE!!!
    
        # if gamma > gamma_minimum:
        #     gamma *= gamma_decay
        #     gamma = max(gamma_minimum,gamma)
    
    
    #%% Costs (All):
    
    DQN_cost_all = []
    
    for i in range(number_of_episodes):
    
        DQN_observation = numpy.array(episode_results_all[i])
    
        r_N_DQN = DQN_observation[0,(r_N_index-1):(r_N_index+2)]
        w_N_DQN = DQN_observation[0,(r_N_index+2):(w_N_index+4)]
        l_N_DQN = DQN_observation[0,(w_N_index+4):(l_N_index+6)]
    
        DQN_action_vector = DQN_observation[0,(l_N_index+6):(l_N_index+9)]
    
        DQN_cost = cost_function(r_N_DQN,w_N_DQN,l_N_DQN,DQN_action_vector)
        DQN_cost_all.append(DQN_cost)
    
    EST_index_all = []
    EST_cost_all = []
    EST_reward_all = []
    
    for i in range(number_of_episodes):
    
        EST_observation = numpy.array(episode_results_all[i])
    
        r_N_EST = EST_observation[0,(r_N_index-1):(r_N_index+2)]
        w_N_EST = EST_observation[0,(r_N_index+2):(w_N_index+4)]
        l_N_EST = EST_observation[0,(w_N_index+4):(l_N_index+6)]
    
        EST_index, EST_cost, EST_reward = EST_function(number_of_tasks,r_N_EST,w_N_EST,l_N_EST)
    
        EST_index_all.append(EST_index)
        EST_cost_all.append(EST_cost)
        EST_reward_all.append(EST_reward)
    
    
    #%% Averages (All):
    
    number_of_batches = int(number_of_episodes/batch_size)
    
    episode_reward_average = numpy.zeros(number_of_batches)
    DQN_cost_average = numpy.zeros(number_of_batches)
    EST_cost_average = numpy.zeros(number_of_batches)
    
    for i in range(number_of_batches):
    
        episode_reward_all_batch = episode_reward_all[i*batch_size:(i+1)*batch_size]
        DQN_cost_all_batch = DQN_cost_all[i*batch_size:(i+1)*batch_size]
        EST_cost_all_batch = EST_cost_all[i*batch_size:(i+1)*batch_size]
    
        episode_reward_average[i] = numpy.average(episode_reward_all_batch)
        DQN_cost_average[i] = numpy.average(DQN_cost_all_batch)
        EST_cost_average[i] = numpy.average(EST_cost_all_batch)
    
    DQN_training_cost_average_total = numpy.average(DQN_cost_all[0:(number_of_episodes-update_target_every-1)])
    print(f"\n\tDQN Average Cost (Training) = {DQN_training_cost_average_total:.2f}")
    EST_training_cost_average_total = numpy.average(EST_cost_all[0:(number_of_episodes-update_target_every-1)])
    print(f"\n\tEST Average Cost (Training) = {EST_training_cost_average_total:.2f}")
    DQN_testing_cost_average_total = numpy.average(DQN_cost_all[(number_of_episodes-update_target_every-1):])
    print(f"\n\tDQN Average Cost (Testing) = {DQN_testing_cost_average_total:.2f}")
    EST_testing_cost_average_total = numpy.average(EST_cost_all[(number_of_episodes-update_target_every-1):])
    print(f"\n\tEST Average Cost (Testing) = {EST_testing_cost_average_total:.2f}")
    
    
    #%% Plots:
    
    figure, (plot_1,plot_2) = matplotlib.pyplot.subplots(1,2)
    figure.suptitle('Training (Exploration)')
    plot_1.plot(episode_reward_all[0:(number_of_episodes-update_target_every-1)],'k')
    plot_1.set_title('Reward for DQN')
    plot_2.plot(episode_reward_average[0:int(((number_of_episodes-update_target_every)/batch_size)-1)],'k')
    plot_2.set_title('Average Reward for DQN')
    
    matplotlib.pyplot.show()
    
    figure, (plot_1,plot_2) = matplotlib.pyplot.subplots(1,2)
    figure.suptitle('Training (Exploration)')
    plot_1.plot(DQN_cost_average[0:int(((number_of_episodes-update_target_every)/batch_size)-1)],'k')
    plot_1.set_title('Average Cost for DQN')
    plot_2.plot(EST_cost_average[0:int(((number_of_episodes-update_target_every)/batch_size)-1)],'k')
    plot_2.set_title('Average Cost for EST')
    
    matplotlib.pyplot.show()
    
    figure, (plot_1,plot_2) = matplotlib.pyplot.subplots(1,2)
    figure.suptitle('Testing (Exploitation)')
    plot_1.plot(DQN_cost_all[(number_of_episodes-update_target_every-1):],'k')
    plot_1.set_title('Cost for DQN')
    plot_2.plot(EST_cost_all[(number_of_episodes-update_target_every-1):],'k')
    plot_2.set_title('Cost for EST')
    
    matplotlib.pyplot.show()
    
    
    #%% Export and Return Statements:
    
    return DQN_training_cost_average_total, EST_training_cost_average_total, DQN_testing_cost_average_total, EST_testing_cost_average_total
    
    
    #%% Documentation:
    
    # Examples => https://pythonprogramming.net/deep-q-learning-dqn-reinforcement-learning-python-tutorial/
    #             https://pythonprogramming.net/training-deep-q-learning-dqn-reinforcement-learning-python-tutorial/