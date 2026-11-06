L = 62; % Wheel base (inches)
Lf = 29.36; % distance from FW COP to front wheel (inches)
Lr = 8.1; % distance from RW COP to rear wheel (inches)
Lu = 42.93; % distance from undertray cop to front wheel (inches)
H = 42.84; % RW drag cop location from ground (inches)
Ff = 52.23; % Front downforce (lbf)
Fr = 74; % rear downforce (lbf) 
Fu = 59.6; % undertray downforce (lbf)
Fdr = 32; % rear wing drag (lbf)

Fx = Fdr; %Total force in x direction
Fy = Ff + Fr + Fu ; % Total force in y direction
theta = 180-((atand(Fy/Fx))+90); % Angle at which resultant force is acting from vertical
F_resultant = sqrt(Fx^2 + Fy^2); % Resultant force acting
Mz = (Fr*(L+Lr))+ (Fu*Lu) + (Fdr*H) - (Ff*Lf); % Total moment (pitching) about z axis
x_cp = (Mz/Fy) % Cop location along the length of car (x axis)


