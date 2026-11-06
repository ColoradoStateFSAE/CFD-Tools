% Code for aero balance
L = 62; % Wheel base (inches)
Lf = 29.36; % distance from FW COP to front axel (inches)
Lr = 8.1; % distance from RW COP to rear axel (inches)
Lu = 42.93 ; % distance from undertray cop to front axel
H = 42.84; % RW drag cop location from ground (inches)
Ff = 59; % Front downforce (lbf)
Fr = 68; % rear downforce (lbf) 
Fu = 57; % Undertray df (lbf)
Fdr = 27.4; % rear wing drag (lbf) (0 deg pitch 26.2)


W_RD = ((Fu*Lu) + (Fr*(L+Lr)) + (Fdr*H) - (Ff*Lf))/L;
W_FD = ((Ff*(L+Lf)) + (Fu*(L-Lu)) - (Fr*Lr) - (Fdr*H))/L;

Percent_rear = (W_RD)/ (W_FD+W_RD) %Downforce percentage in the rear
Percent_front = (W_FD)/(W_FD+W_RD) %Downforce percentage in the front