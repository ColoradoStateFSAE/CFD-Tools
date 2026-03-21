
L = 62; % Wheel base (inches)
Lf = [29.36,26.48,26.598]; % distance from FW COP to front wheel (inches)
Lr = [8.1,15.95,15.94]; % distance from RW COP to rear wheel (inches)
Lu = [42.93,26.88,27.288]; % distance from undertray cop to front wheel (inches)
H = [42.84,42.84,42.84]; % RW drag cop location from ground (inches)
Ff = [59,65.42,67.852]; % Front downforce (lbf)
Fr = [68,60.48,59.51]; % rear downforce (lbf) 
Fu = [57,47.17,39.789]; % undertray downforce (lbf)
Fdr = [27.4,19.78,20.725]; % rear wing drag (lbf)
List = ["Flat", "-0.2deg", "-0.4deg"]

Fx = Fdr; %Total force in x direction
Fy = Ff + Fr + Fu ; % Total force in y direction
theta = 180-((atand(Fy./Fx))+90); % Angle at which resultant force is acting from vertical
F_resultant = sqrt(Fx.^2 + Fy.^2); % Resultant force acting
Mz = (Fr.*(L+Lr))+ (Fu.*Lu) + (Fdr.*H) - (Ff.*Lf); % Total moment (pitching) about z axis
x_cp = (Mz./Fy) % Cop location along the length of car (x axis)

W_RD = ((Fu.*Lu) + (Fr.*(L+Lr)) + (Fdr.*H) - (Ff.*Lf))./L;
W_FD = ((Ff.*(L+Lf)) + (Fu.*(L-Lu)) - (Fr.*Lr) - (Fdr.*H))./L;

Percent_rear = (W_RD)./ (W_FD+W_RD) %Downforce percentage in the rear
Percent_front = (W_FD)./(W_FD+W_RD) %Downforce percentage in the front