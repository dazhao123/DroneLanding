#!/usr/bin/env python
import rospy
import tf
import math
import geometry_msgs.msg
from geometry_msgs.msg import Twist
from geometry_msgs.msg import Pose, PoseStamped
from geometry_msgs.msg import TransformStamped
from math import pow, atan2, sqrt, pi, degrees
from std_msgs.msg import Float32MultiArray
from tf.transformations import euler_from_quaternion
from tf.transformations import quaternion_from_euler
from mavros_msgs.srv import SetMode
from mavros_msgs.srv import CommandBool
from mavros_msgs.srv import CommandTOL

def euclidean_distance(xd, yd, zd):
    return sqrt(pow((xd), 2) + pow((yd), 2) + pow((zd), 2))


class State:
    def __init__(self, x = 0, y = 0, z = 0):
        self.x = x
        self.y = y
	self.z = z

class PID:
    def __init__(self,kp=1,kd=0,ki=0,dt=0.01):

        #GAINS
        self.kp = kp
        self.kd = kd
        self.ki = ki

        #TIME STEP
        self.dt = dt

        #Default ERROR INITIALIZATION
        self.err_previous = 0.001
        self.err_acc = 0

    def compute(self,err):

        #compute dervivative
        err_deriv = (err - self.err_previous)/self.dt
        
        #update integration
        self.err_acc = self.err_acc + self.dt * (err + self.err_previous)/2
        
        #compute pid equation
        pid = self.kp*err + self.kd*err_deriv + self.ki*self.err_acc

        #update error
        self.err_previous = err

        return pid

class Controller:
    '''
    main class of the ros node controlling the robot.
    '''

    def __init__(self):

        #initialization of the ros node and relevant pub/sub
        rospy.init_node("PID_node")
        self.velocity_publisher=rospy.Publisher("/mavros/setpoint_velocity/cmd_vel_unstamped",Twist,queue_size=1)
        self.position_publisher=rospy.Publisher("/mavros/setpoint_position/local",PoseStamped,queue_size=1) 
        self.bebop_subscriber=rospy.Subscriber("/relative_distance", Float32MultiArray ,self.call_back)
        self.position_subscriber=rospy.Subscriber("/mavros/local_position/pose", PoseStamped ,self.pos_call_back)

        #robot current state
        self.state = State()

        self.local_position = PoseStamped()

        #controller frequency in Hz
        self.hz=50.0
        self.rate = rospy.Rate(self.hz)
        self.dt=(1.0/self.hz)

        #define pids
        self.pid_rho_2d = PID(kp=0.3, ki=0.01, dt=self.dt)
        self.pid_rho_height = PID(kp=0.1, ki=0.01, dt=self.dt)

    # transformation
    def call_back(self, msg):
        #print(msg.data)
        self.state.x = -msg.data[1]
        self.state.y = -msg.data[0]
        self.state.z = -msg.data[2]

    def pos_call_back(self, msg):
        self.local_position.pose.position.x = msg.pose.position.x
        self.local_position.pose.position.y = msg.pose.position.y
        self.local_position.pose.position.z = msg.pose.position.z


    def takeoff(self):
        print("Fly to z = 2")
        pos_msg = PoseStamped()
        pos_msg.pose.position.x = 0
        pos_msg.pose.position.y = 0
        pos_msg.pose.position.z = 2
        for i in range(200):
            self.position_publisher.publish(pos_msg)
            self.rate.sleep()

    def move_in_2d(self, tolerance_2d):
        vel_msg = Twist()

        # move in 2d
        rho = euclidean_distance(self.state.x, self.state.y)
        while rho >= tolerance_2d or rho==0 and not math.isnan(self.state.x):
            rospy.loginfo("2d Distance from goal:"+str(rho))
            rho = euclidean_distance(self.state.x, self.state.y)

            err_x = self.state.x
            err_y = self.state.y

            #Compute PID
            vx = self.pid_rho_2d.compute(err_x)
            vy = self.pid_rho_2d.compute(err_y)

            #fill message
            vel_msg.linear.x = vx 
            vel_msg.linear.y = vy
            vel_msg.linear.z = 0.0
            vel_msg.angular.x = 0.0
            vel_msg.angular.y = 0.0
            vel_msg.angular.z = 0.0

            #debugging
            print("vx: {:6f}, x distance: {:6f}".format(vel_msg.linear.x, self.state.x))
            print("vy: {:6f}, y distance: {:6f}".format(vel_msg.linear.y, self.state.y))
            print("vz: {:6f}, z distance: {:6f}".format(vel_msg.linear.z, self.state.z))
            print("_________________")

            #publish
            self.velocity_publisher.publish(vel_msg)
            self.rate.sleep()

    def move_in_height(self, tolerance_height):
        vel_msg = Twist()
        height = self.state.z
        
        while height >= tolerance_height and not math.isnan(self.state.x):
            rospy.loginfo("height from goal:"+str(height))
            height = self.state.z

            vz = self.pid_rho_height.compute(err_z) * 0.2

            #fill message
            vel_msg.linear.x = 0.0 
            vel_msg.linear.y = 0.0
            vel_msg.linear.z = vz
            vel_msg.angular.x = 0.0
            vel_msg.angular.y = 0.0
            vel_msg.angular.z = 0.0

            #debugging
            print("vx: {:6f}, x distance: {:6f}".format(vel_msg.linear.x, self.state.x))
            print("vy: {:6f}, y distance: {:6f}".format(vel_msg.linear.y, self.state.y))
            print("vz: {:6f}, z distance: {:6f}".format(vel_msg.linear.z, self.state.z))
            print("_________________")

            #publish
            self.velocity_publisher.publish(vel_msg)
            self.rate.sleep()

        
    def move_to_goal(self):

        tolerance_2d = [0.5, 0.25]
        tolerance_height = [1, 0.5]
        move_in_2d(tolerance_2d[0])
        print("_________________start descending - 1_________________")
        move_in_height(tolerance_height[0])

        move_in_2d(tolerance_2d[1])
        print("_________________start descending - 2_________________")
        move_in_height(tolerance_height[1])

        # stop the robot
        vel_msg.linear.x=0.0
        vel_msg.linear.y=0.0
        vel_msg.linear.z=0.0
        self.velocity_publisher.publish(vel_msg)

        # Land
        print "\n Landing"
        rospy.wait_for_service('/mavros/cmd/land')
        try:
            land_cl = rospy.ServiceProxy('/mavros/cmd/land', CommandTOL)
            response = land_cl(altitude = height, latitude=0, longitude=0, min_pitch=0, yaw=0)
            rospy.loginfo(response)
        except rospy.ServiceException as e:
            print("Landing failed: %s" %e)

        # Disarm
        print "\n Disarming"
        rospy.wait_for_service('/mavros/cmd/arming')
        try:
            arming_cl = rospy.ServiceProxy('/mavros/cmd/arming', CommandBool)
            response = arming_cl(value = False)
            rospy.loginfo(response)
        except rospy.ServiceException as e:
            print("Disarming failed: %s" %e)

        #if not math.isnan(self.state.x):


        #if self.local_position.pose.position.z > 0:
        #    print("landing begin")
        #    vel_msg.linear.x=0.0
        #    vel_msg.linear.y=0.0
        #    vel_msg.linear.z=-2.0
        #    for i in range(1000):
        #        self.velocity_publisher.publish(vel_msg)
        #        self.rate.sleep()


        #pos_msg = PoseStamped()
        #pos_msg.pose.position.x = self.local_position.pose.position.x
        #pos_msg.pose.position.y = self.local_position.pose.position.y
        #pos_msg.pose.position.z = 0
        #for i in range(200):
        #    self.position_publisher.publish(pos_msg)
        #    self.rate.sleep()
        
        rospy.loginfo("I'm here(relative info): "+ str(self.state.x) + " , " + str(self.state.y) +" , " + str(self.state.z))
        print("___")

        return


if __name__ == '__main__':
    try:
        x = Controller()

        # TAKE OFF
        x.takeoff()

        #MOVE TO THE GOALS
        x.move_to_goal()

        #spin
        rospy.spin()

    except rospy.ROSInterruptException:
        pass 
