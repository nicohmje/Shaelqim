#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import rospy
import numpy as np
import math
import random
import cv2 as cv
from scipy import signal
from sklearn.cluster import DBSCAN
from skimage.morphology import dilation, disk
from skimage.draw import line



from cv_bridge import CvBridge, CvBridgeError


from sensor_msgs.msg import Image
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
import matplotlib.pyplot as plt
from std_msgs.msg import Int32
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid, Odometry
3
class Nodes:
    def __init__(self, x,y):
        self.x = x
        self.y = y
        self.cost = float('inf')
        self.parent = None
        self.children = []

class RRTStarPlanning:
    def __init__(self, stepSize=4, radius=20, max_iters=600, cpm=50, is_occupied=0):
        self.img = None
        self.radius = radius
        self.stepSize= stepSize
        self.max_iters = max_iters
        self.cpm = cpm
        self.occup = is_occupied
        self.busy = False

    def set_image(self, img):
        if self.busy:
            return
        self.img = img
        self.start = (self.img.shape[0]-1, img.shape[1]//2)

    def plan(self, end):
        if self.img is None:
            return [None]
        self.node_list = [0]
        self.end = end
        return self.RRT()
    
    def rel_to_grid(self, rel):
        x = (self.img.shape[0]-1) - (rel[0]*self.cpm)
        y = (self.img.shape[1]//2) - (rel[1]*self.cpm)
        return (int(x),int(y))
    
    def grid_to_rel(self, grid):
        x = (self.img.shape[0]-1 - grid[0])/self.cpm
        y = ((self.img.shape[1]//2) - grid[1])/self.cpm
        return (x, y)
    
    def collision(self, x1, y1, x2, y2):
        # Switched from bresenham to skimage.draw.line
        discrete_line = (zip(*line(x1,y1,x2,y2)))
        for point in discrete_line:
            try:
                if self.img[point[0], point[1]] == self.occup:  # Assuming obstacle is white
                    return True
            except:
                continue
        return False

    def check_collision(self, x1,y1,x2,y2):
        hx,hy=self.img.shape
        if y1<0 or y1>hy or x1<0 or x1>hx:
            directCon = False
            nodeCon = False
        else:
            if self.collision(x1,y1,self.end[0],self.end[1]):
                directCon = False
            else:
                dst, _ = self.dist_and_angle(x1,y1,self.end[0],self.end[1])

                # Threshold distance from last point to goal (optional)
                if dst > self.stepSize*2:
                    directCon = True
                else:
                    directCon= True

            if self.collision(x1,y1,x2,y2):
                nodeCon = False
            else:
                nodeCon = True

        return(directCon,nodeCon)

    # return dist and angle b/w two points
    def dist_and_angle(self, x1,y1,x2,y2):
        dist = math.sqrt( ((x1-x2)**2)+((y1-y2)**2) )
        angle = math.atan2(y2-y1, x2-x1)
        return(dist,angle)
    
    # b/w two nodes (im lazy)
    def distance(self, n1, n2):
        dist = math.sqrt( ((n2.x-n1.x)**2)+((n2.y-n1.y)**2) )
        return dist
    

    def near_nodes(self, new_node):
        return [node for node in self.node_list if self.distance(node, new_node) < self.radius]

    def best_parent(self, nx, ny):
        best_cost = float('inf')
        best_node = None
        next_node = Nodes(nx, ny)
        for i in range(len(self.node_list)):
            n = self.node_list[i]
            dst = self.distance(n, next_node)
            if dst > self.radius:
                print("out of radius")
                continue
            cost = n.cost + dst
            if cost<best_cost and not self.collision(n.x, n.y, next_node.x, next_node.y):
                best_cost = cost
                best_node = i
            else:
                pass
                # print("cost", cost, best_cost)
        return best_node, best_cost
    
    def rewire(self, new_node, near_nodes):
        for node in near_nodes:
            cost_via_new_node = new_node.cost + self.distance(new_node, node)
            if cost_via_new_node < node.cost and not self.collision(new_node.x , new_node.y, node.x, node.y):
                if node.parent:
                    node.parent.children.remove(node)
                node.parent = new_node
                new_node.children.append(node)
                node.cost = cost_via_new_node
                self.update_children_costs(node)  # Recursively update costs of all children

    def update_children_costs(self, node):
        for child in node.children:
            proposed_cost = node.cost + self.distance(node, child)
            if proposed_cost < child.cost:
                # print("UPDATED CHILD NODE COST")
                child.cost = proposed_cost
                self.update_children_costs(child)  # Recursively update children's costs

    # return the neaerst node index
    def nearest_node(self, x,y):
        temp_dist=[]
        for i in range(len(self.node_list)):
            dist,_ = self.dist_and_angle(x,y,self.node_list[i].x,self.node_list[i].y)
            temp_dist.append(dist)
        return temp_dist.index(min(temp_dist))

    # generate a random point in the occup grid space
    def rnd_point(self, h,l):
        new_y = random.randint(0, h-1)
        new_x = random.randint(0, l-1)
        return (new_x,new_y)


    def RRT(self):

        h,l= self.img.shape # dim of the loaded image

        if self.img[self.start[0], self.start[1]] == self.occup:
            return [None, None]
        
        # if self.img[self.end[0], self.end[1]] == 0:
        #     print("END IS COLLISION")
        #     return [None, None]

        if not self.collision(self.start[0], self.start[1], self.end[0], self.end[1]):
            #Just go straight to the end
            return [self.start, self.end]
               
        self.node_list[0] = Nodes(self.start[0],self.start[1])
        self.node_list[0].parent = None
        self.node_list[0].cost = 0

        i=1
        loop = 0
        self.busy = True
        pathFound = False
        while pathFound==False and (not rospy.is_shutdown()):
            # print(f"iter {i}")
            if i > self.max_iters:
                self.busy = False
                return [None, None]

            if loop > 40:
                # print("MAX LOOP")
                return [None, None]
            
            nx,ny = self.rnd_point(h,l)
            
            nearest_ind = self.nearest_node(nx,ny)
            nearest_x = self.node_list[nearest_ind].x
            nearest_y = self.node_list[nearest_ind].y

            _,theta = self.dist_and_angle(nearest_x,nearest_y,nx,ny)
            tx=int(nearest_x + self.stepSize*np.cos(theta))
            ty=int(nearest_y + self.stepSize*np.sin(theta))
            
            if ty<0 or ty>self.img.shape[1]-1 or tx<0 or tx>self.img.shape[0]-1:
                loop += 1
                # print("bounds")
                continue

            nearest_ind, new_cost = self.best_parent(tx, ty)

            if nearest_ind is None:
                # print("no best parent")
                loop += 1
                continue
                
            #check direct connection
            directCon,nodeCon = self.check_collision(tx,ty,nearest_x,nearest_y)
            # print("Check collision:",tx,ty,directCon,nodeCon)

            
            if directCon and nodeCon:
                self.node_list.append(i)
                self.node_list[i] = Nodes(tx,ty)

                self.node_list[i].parent = self.node_list[nearest_ind]
                self.node_list[nearest_ind].children.append(self.node_list[i])
                self.node_list[i].cost = new_cost

                # self.rewire(self.node_list[i], self.near_nodes(self.node_list[i]))

                print(f"Path has been found in {i} iterations")

                node = self.node_list[i]
                pos = (node.x, node.y)
                checkpoints = [pos]
                print("pos", pos)
                while True:
                    pos, node = self.get_parent_coord(node)
                    print("pos", pos)
                    checkpoints.append(pos)
                    if node is None or pos == self.start:
                        break
                # checkpoints.reverse()
                self.busy = False
                return checkpoints

            elif nodeCon:

                self.node_list.append(i)
                self.node_list[i] = Nodes(tx,ty)
                self.node_list[i].parent = self.node_list[nearest_ind]
                self.node_list[nearest_ind].children.append(self.node_list[i])
                self.node_list[i].cost = new_cost

                self.rewire(self.node_list[i], self.near_nodes(self.node_list[i]))
                i += 1
                loop = 0
                continue

            else:
                print("no cin")
                loop += 1
                continue
    
    def get_parent_coord(self,node):
        if node.parent is None:
            return self.start, None
        x = node.parent.x 
        y = node.parent.y
        parent = node.parent

        return (x,y), parent


class Bottle:
    def __init__(self, index, position=None, gate=None, colour=None):
        self.index = index
        self.position = position
        self.gate = gate
        self.colour = colour

    def get_position(self):
        return (self.position[0], self.position[1])
    
    def set_position(self, position:tuple):
        self.position = position

    def set_colour(self, colour:int):
        self.colour = colour

    def get_colour(self):
        return self.colour

    def set_gate(self, gate:int):
        self.gate = gate

    def get_gate(self):
        return self.gate
    
    def get_index(self):
        return self.index
        


class Gate:
    def __init__(self, center_position=None, bottle_index1=None, bottle_index2=None, colour=None):
        self.center_position = center_position
        self.bottle_index1 = bottle_index1
        self.bottle_index2 = bottle_index2

        self.offset_point1 = None
        self.offset_point2 = None

        self.confirmed = False
        self.colour = colour

        # print("New gate alert! :", self.bottle_index1,self.bottle_index2)

    def confirm(self):
        self.confirmed = True

    def get_center_pos(self):
        return self.center_position
    
    def set_colour(self, colour:int, bottles:list):
        bottles[self.bottle_index1].set_colour(colour)
        bottles[self.bottle_index2].set_colour(colour)

        self.colour = colour
    
    def get_colour(self):
        return self.colour
    
    def get_bottles_indices(self):
        return self.bottle_index1, self.bottle_index2
    

    def get_offset_points(self):
        return self.offset_point1, self.offset_point2

    def update(self, bottles:list):
        c1 = bottles[self.bottle_index1].get_position()
        c2 = bottles[self.bottle_index2].get_position()

        vec = np.array(c1) - np.array(c2)
        perp_vec = np.array([-vec[1], vec[0]])
        unit_perp_vec = perp_vec / np.linalg.norm(perp_vec)

        offset = 0.24 #Self.sim 0.24

        cX = np.mean([c1[0],c2[0]])
        cY = np.mean([c1[1],c2[1]])

        self.center_position = (cX, cY)

        self.offset_point1 = np.array(self.center_position) + offset * unit_perp_vec
        self.offset_point2 = np.array(self.center_position) - offset * unit_perp_vec
        


class TurtleController:

    def __init__(self):
            
            self.image_pub = rospy.Publisher("/masked_frame", Image, queue_size=1)
            self.error_pub = rospy.Publisher("/error", Int32, queue_size=1)
            self.cmd_vel_pub = rospy.Publisher("/cmd_vel", Twist, queue_size=1)
            self.occupancy_grid_pub = rospy.Publisher('occupancy_grid_road', OccupancyGrid, queue_size=4)
            

            rospy.Subscriber("/param_change_alert", Bool, self.get_params)

            self.laser_scan = None
            self.cv_image = None
            self.image = None
            self.cv_image_rect = None
            self.theta = None
            self.pos = None


            self.detect_stepline = False

            self.step = 1


            self.ang_vel = 0
            self.cmd_speed = 0

            self.error = 0

            self.avg_radius = 0

            self.occupancy_grid = None
            self.occupancy_grid2 = None

            self.left_lane = [np.nan, np.nan]  
            self.right_lane = [np.nan, np.nan]


            self.buffer = 0

            self.current_index = 0

            self.inside_tunnel = False

            
            # self.order = [1,0,2] #0 blue, 1 green, 2 yellow


            self.bridge = CvBridge()

            self.last_detection = None
            self.get_params()

            self.pathplanner = RRTStarPlanning(stepSize=self.rrt_step, radius=self.rrt_radius, max_iters=self.rrt_maxiters, cpm=self.CELLS_PER_METER, is_occupied=self.IS_FREE) 

            self.bottles = []
            self.gates = []

            self.colour_to_gate = {0:None, 1:None, 2:None}

            # self.same_bottle_threshold = (6,0.12)[self.sim]
            self.confirmed = False

            self.found_colours = False

            self.state = 0 #0 exploring, 1 transiting, 2 crossing 
            self.target_gate = None

            rospy.on_shutdown(self.stop_and_clean_up)


        

            rospy.Subscriber("/camera/image", Image, self.callback_image)
            rospy.Subscriber("/occupancy_grid_noroad", OccupancyGrid, self.occupCB)
            rospy.Subscriber("/lidar_data", LaserScan, self.lidarCB)
            rospy.Subscriber("/image_rect_color", Image, self.callback_image_rect)
            rospy.Subscriber("/odom", Odometry, self.odomCB)


    def stop_and_clean_up(self):
        cmd_twist = Twist()

        cmd_twist.angular.z = 0
        cmd_twist.linear.x = 0

        self.cmd_vel_pub.publish(cmd_twist)



    def turtle_to_odom(self, rel):
        #Convert from turtle frame to odom fram
        rel = self.pathplanner.grid_to_rel(rel)
        
        y = self.pos[1] + (math.sin(self.theta) * rel[0] + math.cos(self.theta) * rel[1])
        x = self.pos[0] + (math.cos(self.theta) * rel[0] - math.sin(self.theta) * rel[1])
        return (x,y)
    
    def odom_to_grid(self, odom):
        #convert from odom frame to turtle(occup grid) frame
        x_prime = odom[0] - self.pos[0]
        y_prime = odom[1] - self.pos[1]
        rel_0 = x_prime * math.cos(self.theta) + y_prime * math.sin(self.theta)
        rel_1 = -x_prime * math.sin(self.theta) + y_prime * math.cos(self.theta)
        return self.pathplanner.rel_to_grid((rel_0, rel_1))


    

    def odomCB(self, msg:Odometry):
        # print("Odom CB")
        w,x,y,z = msg.pose.pose.orientation.w, msg.pose.pose.orientation.x, msg.pose.pose.orientation.y, msg.pose.pose.orientation.z 
        self.old_theta = self.theta
        self.old_pos = self.pos
        self.theta = math.atan2(2*x*y + 2 * z * w, 1 - 2*y*y - 2*z*z)
        self.pos = (msg.pose.pose.position.x, msg.pose.pose.position.y)
        




    def challenge_2(self):

        # lidar_occup = np.copy(self.occupancy_grid.filled(0))
        # lidar_occup = np.transpose(np.rot90(lidar_occup, k=2, axes=(1,0)))        
        # occu_grid_cp = (lidar_occup > 95)

        # # Create a structuring element (disk) corresponding to half the robot's width
        # selem = disk(3)  # 'radius' should be set to half the robot's width in pixels

        # # Dilate the obstacle map
        # inflated_obstacles = dilation(occu_grid_cp, selem)
        # inflated_obstacles = np.where(inflated_obstacles, 0, 100)

        # self.occupancy_grid2 = inflated_obstacles
        if self.occupancy_grid2 is None:
            return
        self.pathplanner.max_iters = 50
        self.pathplanner.stepSize = 4
        self.pathplanner.set_image(self.occupancy_grid2)
        self.publish_occupancy_grid()


        goal = [1.71,1.6]

        distance_to_goal = np.linalg.norm(np.array((goal[0] - self.pos[0], goal[1]-self.pos[1])))

        angle_to_goal = (math.atan2(goal[1] - self.pos[1], goal[0] - self.pos[0])) - self.theta 

        relative_pos = (math.cos(angle_to_goal)*distance_to_goal, math.sin(angle_to_goal)*distance_to_goal)


        goal_grid_pos = self.pathplanner.rel_to_grid((relative_pos))
        start_grid_pos = self.pathplanner.rel_to_grid((0,0))

        print("start, goal", start_grid_pos, goal_grid_pos)

        cells = list(self.traverse_grid(goal_grid_pos, start_grid_pos))
        
        if cells[-1] == start_grid_pos:
            cells.reverse()

        closest_cell = goal_grid_pos
        s1, s2 = self.occupancy_grid2.shape

        for i in cells:
            if i[0]>(s1-1) or i[0]<0 or i[1]<0 or i[1]>(s2-1):
                break
            # else:
            #     closest_cell = i
            if self.occupancy_grid2[i[0], i[1]] == 100:
                closest_cell = i
        
        goals = self.pathplanner.plan(closest_cell)

        print("planner result: ", goals)

        self.cmd_speed = 0.2

        target = goals[1]

        print("Target", target)

        if target is None:
            print("Not found")
            local_waypoint = np.array((10, 0))
            # self.cmd_speed = 0.0
        else:
            local_waypoint = np.array((self.occupancy_grid2.shape[0] - target[0], target[1] - 0.5 * self.occupancy_grid2.shape[1]))

        distance = np.linalg.norm(local_waypoint)
        heading = math.atan2(local_waypoint[1], local_waypoint[0])

        print("DISTANDHEADINIG", distance, heading)

        Kp = (-1.5, -1.5)[self.sim]

        if abs(heading) > (0.3,0.6)[self.sim]:
            self.cmd_speed = 0.05
        self.ang_vel = heading * Kp
        
        print("jead", self.cmd_speed)











    def occupCB(self, msg):
        data = np.asarray(msg.data, dtype=np.int8).reshape(msg.info.height, msg.info.width)
        self.occupancy_grid = np.ma.array(data, mask=data==-1, fill_value=-1)
        self.grid_height = msg.info.width
        self.stamp = msg.header.stamp
        self.grid_width = msg.info.height
        self.CELL_Y_OFFSET = (self.grid_width // 2) - 1

        if self.step == 5:
            # if self.current_index == 3:
            #     rospy.signal_shutdown("Finished all challenges.")
            self.last_challenge()


    def make_cmd(self):
        cmd_twist = Twist()
        # self.cmd_speed = 0
        # self.ang_vel = 0

        print("Step:", self.step)
        if not self.step:
            self.cmd_speed = self.max_speed
            self.ang_vel = 0

        if self.step <= 1:
            if self.image is None or self.laser_scan is None:
                rospy.logwarn("No image received!")
                pass
            else:
                #pass
                if np.mean(self.laser_scan.ranges[87:93]) < 0.2:
                    print("JOHMN CENA")
                    self.cmd_speed = 0
                    self.ang_vel = 0
                    pass 
                else:
                    print(np.mean(self.laser_scan.ranges[87:93]))
                    self.lane_assist_controller()

        elif self.step == 2:
            if self.laser_scan is None:
                rospy.logwarn("No LiDAR data received!")
            else:
                self.challenge_2()
                # self.lane_assist_controller()
                # self.obstacle_detection()
        
        elif self.step == 3:
            if self.laser_scan is None:
                rospy.logwarn("No LiDAR data received!")
                pass
            else:
                # self.lane_assist_controller()
                self.lidar_only()
                # self.obstacle_detection()
                pass

        elif self.step == 4:
            if self.image is None:
                rospy.logwarn("No image received!")
                pass
            else:
                if self.buffer <4:
                    self.cmd_speed = 0.1
                    self.ang_vel = 0.0
                    self.buffer += 1
                else:
                #pass
                    self.lane_assist_controller()

        elif self.step == 5:
            if self.cv_image_rect is None:
                print("NO IAMGE RECT")
            else:
                pass
                # self.last_challenge()

        # print("ang_vel = ", self.ang_vel)
        cmd_twist.linear.x = self.cmd_speed

        if self.sim:
            pass
            self.ang_vel = min(self.ang_vel_clip, max(-self.ang_vel_clip, self.ang_vel))
        else:
            pass
            # self.ang_vel = min(self.ang_vel_clip, max(-self.ang_vel_clip, self.ang_vel))


        cmd_twist.angular.z = self.ang_vel

        # print("ang vel, speed", self.ang_vel, self.cmd_speed)

        # speed pub
        self.cmd_vel_pub.publish(cmd_twist)


    def lidarCB(self, data:LaserScan) :
        self.laser_scan = data


    def lidar_only(self):
        # center_pos_index = int(len(self.laser_scan.ranges)//2 + 1)

        # # print("ang_vel", self.ang_vel)

        # offset = 75

        
        Kp = (5.0, 8.0)[self.sim]

        # print(90 - np.argmax(self.laser_scan.ranges))

        # dir = Kp * (90 - np.argmax(self.laser_scan.ranges))

        # print("dir ", dir)

        left_ranges = np.array(self.laser_scan.ranges[135:155])
        right_ranges = np.array(self.laser_scan.ranges[30:40])
        front_ranges = np.array(self.laser_scan.ranges[75:105])

        print(left_ranges)

        dst_left = np.mean(left_ranges[(np.where(left_ranges > 0))]) 
        dst_right = np.mean(right_ranges[(np.where(right_ranges > 0))])
        dst_front = np.mean(front_ranges[(np.where(front_ranges > 0))])

        if np.isnan(dst_left):
            dst_left = 0.9
        if np.isnan(dst_right):
            dst_right = 0.9

        print("left ", dst_left)
        print("right ", dst_right)
        print("inside tunnel ", self.inside_tunnel_thresh)
        
        if dst_left < self.inside_tunnel_thresh and dst_right < self.inside_tunnel_thresh and self.inside_tunnel == False:
            print("entered tunnel")
            self.inside_tunnel = True
            dir = Kp * ((dst_left-dst_right)/(0.7*dst_front))

            print(dir)

            
            dir = min(10, max(-10, dir))

            self.ang_vel = dir
        elif self.inside_tunnel == True:

            print("inside tunnel")
            dir = Kp * (dst_left-dst_right)

            print(dir)

            
            dir = min(10, max(-10, dir))

            self.ang_vel = dir
        else:
            self.ang_vel = 0

        self.cmd_speed = 0.15


    def traverse_grid(self, start, end):
        """
        Bresenham's line algorithm for fast voxel traversal

        CREDIT TO: Rogue Basin
        http://www.roguebasin.com/index.php/Bresenham%27s_Line_Algorithm
        """
        x1,y1 = start
        x2, y2 = end

        return (zip(*line(x1,y1,x2,y2)))
    
        # # Setup initial conditions
        # x1, y1 = start
        # x2, y2 = end
        # dx = x2 - x1
        # dy = y2 - y1

        # # Determine how steep the line is
        # is_steep = abs(dy) > abs(dx)

        # # Rotate line
        # if is_steep:
        #     x1, y1 = y1, x1
        #     x2, y2 = y2, x2

        # # Swap start and end points if necessary and store swap state
        # if x1 > x2:
        #     x1, x2 = x2, x1
        #     y1, y2 = y2, y1

        # # Recalculate differentials
        # dx = x2 - x1
        # dy = y2 - y1

        # # Calculate error
        # error = int(dx / 2.0)
        # ystep = 1 if y1 < y2 else -1

        # # Iterate over bounding box generating points between start and end
        # y = y1
        # points = []
        # for x in range(x1, x2 + 1):
        #     coord = (y, x) if is_steep else (x, y)
        #     points.append(coord)
        #     error -= abs(dy)
        #     if error < 0:
        #         y += ystep
        #         error += dx
        # return points
    
    
    def check_collision(self, cell_a, cell_b, margin=0):
        """
        Checks whether the path between two cells
        in the occupancy grid is collision free.
        """ 
        obstacles = []

        for i in range(-margin, margin + 1):  # for the margin, check
            cell_a_margin = (cell_a[0]+i, cell_a[1])
            cell_b_margin = (cell_b[0]+i, cell_b[1])
            for cell in self.traverse_grid(cell_a_margin, cell_b_margin):
                # print(cell, self.occupancy_grid[cell[0], cell[1]])
                if (cell[0] * cell[1] < 0) or (cell[0] >= self.occupancy_grid.shape[0]) or (cell[1] >= self.occupancy_grid.shape[1]):
                    print("oob")
                    continue
                try:
                    if self.occupancy_grid[cell[0], cell[1]] == self.IS_OCCUPIED:
                        # print("occupied")
                        obstacles.append(cell)
                        break
                except:
                    print("Out of bounds")
                    obstacles.append(cell)
                    break
        return obstacles


    def get_params(self, event=True):
        rospy.loginfo("Updating the parameters")
        try:
            try:
                self.sim = rospy.get_param("use_sim_time")
            except:
                self.sim = False


            ## PARAMS   

            self.order = rospy.get_param("/order", default=[0,1,2])

            self.CELLS_PER_METER = rospy.get_param("/occup_cellspermeter", default=50)
            self.IS_FREE = rospy.get_param("/occup_isfree", default=0)
            self.IS_OCCUPIED = rospy.get_param("/occup_osoccupied", default=100)

            self.road_maxwidth = rospy.get_param("/road_maxwidth", default=240)
            self.road_lane_offset = rospy.get_param("/road_lane_offset", default=0.3)

            self.inside_tunnel_thresh = rospy.get_param("/lidar_inside_tunnel_threshold", default=0.55)

            self.rrt_step = rospy.get_param("/rrt_step", default=6)
            self.rrt_radius = rospy.get_param("/rrt_radius", default=60)
            self.rrt_maxiters = rospy.get_param("/rrt_maxiters", default=400)

            self.same_bottle_threshold = rospy.get_param("/bottles_same_bottle_threshold", default=0.12)
            self.bottles_area_threshold = rospy.get_param("/bottles_area_threshold", default=200)
            self.bottles_target_distance = rospy.get_param("/bottles_target_distance", default=0.46)
            self.bottles_tolerance = rospy.get_param("/bottles_tolerance", default=0.06)

            print("PARAM ", self.bottles_target_distance)

            self.ang_vel_clip = rospy.get_param("/ang_vel_clip", default=10.0)

            self.stepline_delay = rospy.get_param("/step_last_detection_threshold", default=6.0)
            self.stepline_upper_area = rospy.get_param("/step_upper_area_threshold", default=2400)
            self.stepline_lower_area = rospy.get_param("/step_lower_area_threshold", default=3200)

            self.max_speed = rospy.get_param("/max_speed", default=0.22)


            ## ROAD

            # Yellow colour Gains
            self.left_H_l = rospy.get_param("/left_H_l", default=77)
            self.left_S_l = rospy.get_param("/left_S_l", default=32)
            self.left_V_l = rospy.get_param("/left_V_l", default=76)

            self.left_H_u = rospy.get_param("/left_H_u", default=102)
            self.left_S_u = rospy.get_param("/left_S_u", default=180)
            self.left_V_u = rospy.get_param("/left_V_u", default=132)

            # White colour Gains
            self.right_H_l = rospy.get_param("/right_H_l", default=100)
            self.right_S_l = rospy.get_param("/right_S_l", default=74)
            self.right_V_l = rospy.get_param("/right_V_l", default=123)

            self.right_H_u = rospy.get_param("/right_H_u", default=120)
            self.right_S_u = rospy.get_param("/right_S_u", default=255)
            self.right_V_u = rospy.get_param("/right_V_u", default=255)

            # Red colour Gains (Assuming two ranges for red)
            self.stepline1_H_l = rospy.get_param("/stepline1_H_l", default=0)
            self.stepline1_S_l = rospy.get_param("/stepline1_S_l", default=0)
            self.stepline1_V_l = rospy.get_param("/stepline1_V_l", default=0)

            self.stepline1_H_u = rospy.get_param("/stepline1_H_u", default=10)
            self.stepline1_S_u = rospy.get_param("/stepline1_S_u", default=255)
            self.stepline1_V_u = rospy.get_param("/stepline1_V_u", default=255)

            self.stepline2_H_l = rospy.get_param("/stepline2_H_l", default=170)
            self.stepline2_S_l = rospy.get_param("/stepline2_S_l", default=50)
            self.stepline2_V_l = rospy.get_param("/stepline2_V_l", default=131)

            self.stepline2_H_u = rospy.get_param("/stepline2_H_u", default=180)
            self.stepline2_S_u = rospy.get_param("/stepline2_S_u", default=170)
            self.stepline2_V_u = rospy.get_param("/stepline2_V_u", default=222)


            ## BOTTLES

            #Blue colour Gains
            self.blue_H_l = rospy.get_param("/blue_H_l", default=77)
            self.blue_S_l = rospy.get_param("/blue_S_l", default=32)
            self.blue_V_l = rospy.get_param("/blue_V_l", default=76)

            self.blue_H_u = rospy.get_param("/blue_H_u", default=102)
            self.blue_S_u = rospy.get_param("/blue_S_u", default=180)
            self.blue_V_u = rospy.get_param("/blue_V_u", default=132)

            # Yellow colour Gains
            self.yellow_H_l = rospy.get_param("/yellow_H_l", default=100)
            self.yellow_S_l = rospy.get_param("/yellow_S_l", default=74)
            self.yellow_V_l = rospy.get_param("/yellow_V_l", default=123)

            self.yellow_H_u = rospy.get_param("/yellow_H_u", default=120)
            self.yellow_S_u = rospy.get_param("/yellow_S_u", default=255)
            self.yellow_V_u = rospy.get_param("/yellow_V_u", default=255)

            # Green colour Gains
            self.green_H_l = rospy.get_param("/green_H_l", default=100)
            self.green_S_l = rospy.get_param("/green_S_l", default=74)
            self.green_V_l = rospy.get_param("/green_V_l", default=123)

            self.green_H_u = rospy.get_param("/green_H_u", default=120)
            self.green_S_u = rospy.get_param("/green_S_u", default=255)
            self.green_V_u = rospy.get_param("/green_V_u", default=255)


        except rospy.ROSException as e:
            rospy.logerr("Failed to get parameters: {}".format(e))



    def callback_image(self, msg):
        self.cv_image = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        self.process_image(self.cv_image)
        

    def callback_image_rect(self, msg):
        self.cv_image_rect = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        if self.laser_scan is None:
                rospy.logwarn("No LiDAR data received!")
                return
        if self.step <=2 and self.sim:
            self.second_process(self.cv_image_rect)


    def obstacle_detection(self):

        if self.occupancy_grid is None:
            return False
        # print("Obstacles left front right ", self.obs_left, self.obs_front, self.obs_right)
        
        MARGIN = (4, 5)[self.sim]
        current_pos = (self.occupancy_grid.shape[0]//2 - 1, 0)

        if self.sim:
            goal_pos = (self.occupancy_grid.shape[0]//2 - 1, 12)
        else:
            goal_pos = (self.occupancy_grid.shape[0]//2 - 1, 8)

        print(current_pos)
        
        

        error = self.occupancy_grid.shape[0]//2 - (np.median(self.check_collision(current_pos, goal_pos, margin=MARGIN), axis = 0))

        print("obs error", error)

        if (np.isnan(error)).any():
            pass
        else:
            print("Obstacle!", error[0])
            if error[0]:
                self.cmd_speed = 0.1
                Kp = (0.6, 0.4)[self.sim]
                self.ang_vel = error[0] * Kp
            print("recourse:", self.ang_vel)


    def lane_assist_controller(self):

        if self.left_lane is None or self.right_lane is None:
            return
    
        rows, cols = self.image.shape[:2]
        
        speed = self.max_speed
        if self.step == 4:
            speed = 0.1

        print("left, right", self.left_lane, self.right_lane)

        if self.left_lane[1]> self.image.shape[1]//2:
            self.left_lane[1] = 0
        if self.right_lane[1]< self.image.shape[1]//2:
            self.right_lane[1] = self.image.shape[1]

        print("left, right", self.left_lane, self.right_lane)

        

        if np.isnan(self.left_lane[1]):
            if np.isnan(self.right_lane[1]):
                print("left and right nan")
                center_of_road = self.error + self.image.shape[1]//2
                speed = 0
            else:
                # print("left nan")
                if self.step == 2 and self.sim:
                    center_of_road = 0
                else:
                    center_of_road = self.right_lane[1] - (cols * 0.45)
        else:
            if np.isnan(self.right_lane[1]):
                # print("right nan")
                if self.step == 2 and self.sim:
                    center_of_road = self.image.shape[1]
                else:
                    center_of_road = self.left_lane[1] + (cols * 0.45)
            else:
                center_of_road = self.left_lane[1] + (self.right_lane[1] - self.left_lane[1])*0.5

        print("width ", self.right_lane[1] - self.left_lane[1], "\n")

        max_width = self.road_maxwidth
        offset = self.road_lane_offset

        if (self.right_lane[1] - self.left_lane[1]) > max_width and self.step < 4:
            print("Road split detected, following white line.")
            # print("left lane, cols", self.left_lane[1], cols*offset)
            center_of_road = self.left_lane[1] + (cols * offset)
        elif (self.right_lane[1] - self.left_lane[1]) > max_width:
            center_of_road = self.right_lane[1] - (cols * offset)


        self.error = center_of_road - self.image.shape[1]//2

        # self.error = max(min(10, self.error),-10)

        print("error", self.error)

        # print("img shape", self.image.shape)

        print("center of road", center_of_road)



        if self.sim:
            Kp = -0.05
        else:
            Kp = -0.02

        self.cmd_speed =  speed #0.22
        self.ang_vel = self.error * Kp

    #Function that warps the image
    def warp(self, img, source_points, destination_points, destn_size):
        matrix = cv.getPerspectiveTransform(source_points, destination_points)
        warped_img = cv.warpPerspective(img, matrix, destn_size)
        return warped_img

    #Function that unwarps the image
    def unwarp(self, img, source_points, destination_points, source_size):
        matrix = cv.getPerspectiveTransform(destination_points, source_points)
        unwarped_img = cv.warpPerspective(img, matrix, source_size)
        return unwarped_img

    def preprocessing(self, img):

        hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)


        if self.sim:
            lower_yellow = np.array([self.left_H_l,self.left_S_l,self.left_V_l])
            upper_yellow = np.array([self.left_H_u,self.left_S_u,self.left_V_u])

            # Define HSV thresholds for red colour
            lower_right = np.array([self.right_H_l, self.right_S_l, self.right_V_l])
            upper_right = np.array([self.right_H_u, self.right_S_u, self.right_V_u])

            # Create masks for yellow and white colours
            mask_left = cv.inRange(hsv, lower_yellow, upper_yellow)
            mask_right = cv.inRange(hsv, lower_right, upper_right)

        else:
            lower_left = np.array([self.left_H_l, self.left_S_l, self.left_V_l])
            upper_left = np.array([self.left_H_u, self.left_S_u, self.left_V_u])

            lower_stepline1 = np.array([self.stepline1_H_l, self.stepline1_S_l, self.stepline1_V_l])
            upper_stepline1 = np.array([self.stepline1_H_u, self.stepline1_S_u, self.stepline1_V_u])
            lower_stepline2 = np.array([self.stepline2_H_l, self.stepline2_S_l, self.stepline2_V_l])
            upper_stepline2 = np.array([self.stepline2_H_u, self.stepline2_S_u, self.stepline2_V_u])


            mask_left = cv.inRange(hsv, lower_left, upper_left)

            mask_stepline1 = cv.inRange(hsv, lower_stepline1, upper_stepline1)
            mask_stepline2 = cv.inRange(hsv, lower_stepline2, upper_stepline2)
            mask_stepline_inter = cv.bitwise_or(mask_stepline1, mask_stepline2)
            
            kernel = np.ones((15,15), np.uint8)
            mask_right = cv.morphologyEx(mask_stepline_inter, cv.MORPH_CLOSE, kernel)




        mask_frame = mask_left + mask_right

        return mask_left, mask_right

    #Function that defines the polygon region of interest
    def regionOfInterest(self,img, polygon):
        mask = np.zeros_like(img)
        x1, y1 = polygon[0]
        x2, y2 = polygon[1]
        x3, y3 = polygon[2]
        x4, y4 = polygon[3]
        m1 = (y2-y1)/(x2-x1)
        m2 = (y3-y2)/(x3-x2)
        m3 = (y4-y3)/(x4-x3)
        m4 = (y4-y1)/(x4-x1)
        b1 = y1 - m1*x1
        b2 = y2 - m2*x2
        b3 = y3 - m3*x3
        b4 = y4 - m4*x4

        for i in range(mask.shape[0]):
            for j in range(mask.shape[1]):
                if i>=m1*j+b1 and i>=m2*j+b2 and i>=m3*j+b3 and i<=m4*j+b4:
                    mask[i][j] = 1

        masked_img = np.multiply(mask, img)
        return masked_img

    def fitCurve(self,img, lane='left'):
        # Calculate the histogram of the bottom half of the image
        histogram = np.sum(img[img.shape[0]//2:,:], axis=0)
        midpoint = int(histogram.shape[0]/2)
        
        # Initial base positions for the left and right x-coordinates
        if lane == 'left':
            x_base = np.argmax(histogram[:midpoint])
        elif lane == 'right':
            x_base = np.argmax(histogram[midpoint:]) + midpoint
        else:
            raise ValueError("Invalid lane specified. Use 'left' or 'right'.")

        # Parameters
        nwindows = 50
        margin = 50
        minpix = 50
        window_height = int(img.shape[0]/nwindows)

        # Lane finding
        lane_indices = []
        x_current = x_base
        y, x = img.nonzero()

        for window in range(nwindows):
            win_y_low = img.shape[0] - (window+1) * window_height
            win_y_high = img.shape[0] - window * window_height
            win_x_low = x_current - margin
            win_x_high = x_current + margin

            good_indices = ((y >= win_y_low) & (y < win_y_high) & 
                            (x >= win_x_low) & (x < win_x_high)).nonzero()[0]
            lane_indices.append(good_indices)

            if len(good_indices) > minpix:
                x_current = int(np.mean(x[good_indices]))

        lane_indices = np.concatenate(lane_indices)
        lanex = x[lane_indices]
        laney = y[lane_indices]
        
        if len(lane_indices) < 3000:
            return None, None


        try:
            fit = np.polyfit(laney, lanex, 2)
        except:
            return None, None

        if lane == 'left':
            return fit, None
        else:
            return None, fit


        # try:
        #     left_fit = np.polyfit(lefty, leftx, 2)
        #     print("left")
        #     return left_fit, None
        # except:
        #     try:
        #         right_fit = np.polyfit(righty, rightx, 2)
        #         print("right")
        #         return None, right_fit
        #     except:
        #         print("None")
        #         return None, None


    def estimate_missing_lane(self, detected_fit, lane_side, lane_width_pixels):
        """
        Estimate the polynomial of the missing lane by shifting the detected lane's polynomial.
        
        :param detected_fit: Polynomial coefficients (a, b, c) of the detected lane
        :param lane_side: 'left' if the left lane is detected, 'right' otherwise
        :param lane_width_pixels: Width of the lane in pixels
        :return: Polynomial coefficients of the estimated missing lane
        """
        a, b, c = detected_fit
        if lane_side == 'left':
            # Estimate the right lane by adding the lane width to the constant term of the polynomial
            missing_lane_fit = (a, b, c + lane_width_pixels)
        elif lane_side == 'right':
            # Estimate the left lane by subtracting the lane width
            missing_lane_fit = (a, b, c - lane_width_pixels)
        else:
            raise ValueError("lane_side must be 'left' or 'right'")
        
        return missing_lane_fit

    def findPoints(self, img_shape, left_fit=None, right_fit=None):
        ploty = np.linspace(0, img_shape[0]-1, img_shape[0])

        LANE_WIDTH_PIXELS = 610
        
        if left_fit is not None and right_fit is None:
            right_fit = self.estimate_missing_lane(left_fit, 'left', LANE_WIDTH_PIXELS)
        elif right_fit is not None and left_fit is None:
            left_fit = self.estimate_missing_lane(right_fit, 'right', LANE_WIDTH_PIXELS)
        
        if left_fit is not None:
            left_fitx = left_fit[0]*ploty**2 + left_fit[1]*ploty + left_fit[2]
            pts_left = np.array([np.transpose(np.vstack([left_fitx, ploty]))])
        else:
            pts_left = None
        
        if right_fit is not None:
            right_fitx = right_fit[0]*ploty**2 + right_fit[1]*ploty + right_fit[2]
            pts_right = np.array([np.flipud(np.transpose(np.vstack([right_fitx, ploty])))])
        else:
            pts_right = None
        
        return pts_left, pts_right


    #Function that fills the space between the detected lane curves
    def fillCurves(self, img_shape, pts_left, pts_right):
        pts = np.hstack((pts_left, pts_right))
        img = np.zeros((img_shape[0], img_shape[1], 3), dtype='uint8')
        cv.fillPoly(img, np.int_([pts]), (255,0,255))
        return img


    def radiusOfCurvature(self,img, left_fit, right_fit):
        y_eval = img.shape[0]//2
        try:
            left_radius = -1 * ((1 + (2*left_fit[0]*y_eval + left_fit[1])**2)**1.5) / (2*left_fit[0])
        except:
            left_radius = None
        try:
            right_radius = -1 * ((1 + (2*right_fit[0]*y_eval + right_fit[1])**2)**1.5) / (2*right_fit[0])
        except:
            right_radius = None
        if left_radius is None:
            if right_radius is None:
                avg_radius = None
            else:
                avg_radius = right_radius
        else:
            if left_radius is None:
                avg_radius = left_radius
            else:
                avg_radius = (left_radius+right_radius)/2
        return avg_radius


    def combine_vision_and_lidar(self, roadmap):
        occup_grid = self.occupancy_grid

        pass


    def second_process(self, image):
        height, width, _ = image.shape

        # polygon = [(int(width*0.05), int(height)), (int(width*0.3), int(height*0.7)), (int(width*0.7), int(height*0.7)), (int(0.95*width), int(height))]
        # polygon = [(int(0), int(height)), (int(1), int(130)), (int(width-1), int(130)), (int(width), int(height))]
        # masked_img = self.regionOfInterest(processed_img, polygon)

        if self.sim:
            source_points = np.float32([[101,140], [width-101,140], [-200,height], [width+200,height]])
            destination_points = np.float32([[0,0], [800,0], [0,450],[800, 450]])
        else:
            source_points = np.float32([[0,0], [width,0], [-850,height], [width+850,height]])
            destination_points = np.float32([[0,0], [500,0], [0,600],[500, 600]])

        warped_img_size = (800, 450)
        warped_img = self.warp(image, source_points, destination_points, warped_img_size)  

        left, right = self.preprocessing(warped_img)


    
        kernel = np.ones((41,41), np.uint8)
        opening_left = cv.morphologyEx(left, cv.MORPH_CLOSE, kernel)
        opening_right = cv.morphologyEx(right, cv.MORPH_CLOSE, kernel)




        warped_img_shape = (warped_img.shape)

        left_fit, _ = self.fitCurve(opening_left, lane="left")
        _, right_fit = self.fitCurve(opening_right, lane="right")

        if left_fit is None and right_fit is None:
            print("no fit")
            return
        
        if left_fit is None:
            center_fit = right_fit
        elif right_fit is None:
            center_fit = left_fit
        else:
            center_fit = (left_fit + right_fit) * 0.5


        pts_left, pts_right = self.findPoints(warped_img_shape, left_fit, right_fit)


        fill_curves = self.fillCurves(warped_img_shape, pts_left, pts_right)

        unwarped_fill_curves = self.unwarp(fill_curves, source_points, destination_points, (width, height))
        window1 = cv.addWeighted(image, 1, unwarped_fill_curves, 1, 0)


        # self.avg_radius = self.radiusOfCurvature(warped_img, left_fit, right_fit)

        # print("RADIUS", self.avg_radius)



        road = self.warp(window1, source_points, destination_points, warped_img_size)


        # image_message = self.bridge.cv2_to_imgmsg(road, "passthrough")
        # self.image_pub.publish(image_message)

        road_mask1 = cv.inRange(road, np.array([240,240,240]), np.array([255,255,255]))
        road_mask2 = cv.inRange(road, np.array([0,240,240]), np.array([30,255,255]))
        road_mask3 = cv.inRange(road, np.array([240,0,240]), np.array([255,30,255]))

        road_mask = road_mask1 + road_mask2 + road_mask3

        road = cv.bitwise_and(road, road, mask=road_mask)

        road = cv.GaussianBlur(road,(11,11),0)
        road = cv.resize(road, (40,22))


        last_row = road[-1,:,:]
        tiled = np.tile(last_row[np.newaxis, :, :], (6,1,1))
        road = np.vstack((road, tiled))

    
        road = cv.cvtColor(road, cv.COLOR_BGR2GRAY)
        _,road = cv.threshold(road,40,255,cv.THRESH_BINARY)

            
        kernel = np.ones(shape=[2, 2])
        self.occupancy_grid2 = signal.convolve2d(
            road.astype("int"), kernel.astype("int"), boundary="symm", mode="same"
        )
        self.occupancy_grid2 = np.clip(self.occupancy_grid2, 0, 50)

        self.merge_occup_grids()     



        
        pass


    def merge_occup_grids(self):
        

        lidar_occup = np.copy(self.occupancy_grid)

        lidar_occup = np.transpose(np.rot90(lidar_occup, k=2, axes=(1,0)))

        lidar_occup = signal.medfilt2d(lidar_occup, 3)


        if self.sim:
            if self.step <= 2:
                lidar_occup = lidar_occup[72:, 55:-55]
                # Create a structuring element (disk) corresponding to half the robot's width
                selem = disk(4)  # 'radius' should be set to half the robot's width in pixels

                # Dilate the obstacle map
                inflated_obstacles = dilation(lidar_occup, selem)

                selem = disk(3)  # 'radius' should be set to half the robot's width in pixels
                inflated_road = dilation(self.occupancy_grid2, selem)
                
                lidar_occup = np.where(inflated_obstacles, 100, 0)

                occu = np.where(inflated_road >0 ,0, 100)

                occu = np.bitwise_or(lidar_occup, occu)

                self.occupancy_grid2 = np.where(occu >0 ,0, 100)
            else:
                self.occupancy_grid2 = np.bitwise_or(lidar_occup, self.occupancy_grid2)
            # self.occupancy_grid2 = lidar_occup
            # self.occupancy_grid2 = np.where(self.occupancy_grid2 >0 ,0, 100)

            # padding_width = 1
            # self.occupancy_grid2 = np.pad(occu, ((padding_width, 0), (padding_width, padding_width)), mode='constant', constant_values=100)

        
        else:
            self.occupancy_grid2 = np.bitwise_or(lidar_occup, self.occupancy_grid2)

            



        # # self.publish_occupancy_grid()


    def publish_occupancy_grid(self):
        """
        Publish populated occupancy grid to ros2 topic
        Args:
            scan_msg (LaserScan): message from lidar scan topic
        """
        oc = OccupancyGrid()
        oc.header.frame_id = "base_footprint"
        oc.header.stamp = rospy.Time.now()
        oc.info.origin.position.y -= (((self.occupancy_grid2.shape[1] / 2)) / self.CELLS_PER_METER)
        oc.info.width = self.occupancy_grid2.shape[0]
        oc.info.height = self.occupancy_grid2.shape[1]
        oc.info.resolution = 1 / self.CELLS_PER_METER
        oc.data = np.fliplr(np.rot90(self.occupancy_grid2, k=1)).flatten().tolist()
        self.occupancy_grid_pub.publish(oc)
        

    def undistort(self, img, balance=0.3, dim2=None, dim3=None):
        DIM = [320,240]
        K = np.array([[95.06302, 0.04031, 159.22853],
              [0., 95.154, 119.47541],
              [0., 0., 1.]])  # Camera matrix
        D = np.array([0.017580, 0.003274, -0.000498, -0.000042])  # Distortion coefficients

        dim1 = img.shape[:2][::-1]  #dim1 is the dimension of input image to un-distort
        assert dim1[0]/dim1[1] == DIM[0]/DIM[1], "Image to undistort needs to have same aspect ratio as the ones used in calibration"
        if not dim2:
            dim2 = dim1
        if not dim3:
            dim3 = dim1
        scaled_K = K * dim1[0] / DIM[0]  # The values of K is to scale with image dimension.
        scaled_K[2][2] = 1.0  # Except that K[2][2] is always 1.0
        # This is how scaled_K, dim2 and balance are used to determine the final K used to un-distort image. OpenCV document failed to make this clear!
        new_K = cv.fisheye.estimateNewCameraMatrixForUndistortRectify(scaled_K, D, dim2, np.eye(3), balance=balance)
        map1, map2 = cv.fisheye.initUndistortRectifyMap(scaled_K, D, np.eye(3), new_K, dim3, cv.CV_16SC2)
        undistorted_img = cv.remap(img, map1, map2, interpolation=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT)
        return undistorted_img


    def process_image(self, image):

        self.image = np.copy(image)

        if self.step <= 4:
            # Convert image to HSV colour space
            hsv = cv.cvtColor(image, cv.COLOR_BGR2HSV)

            rectangle = np.copy(hsv)


            if self.sim:
                rectangle[:150, :, :] = 0
                rectangle[220:, :, :] = 0
            else:
                pass
                # rectangle[:250, :, :] = 0
                # rectangle[:, :40, :] = 0 
                # rectangle[:, 280:, :] = 0



            # Left lane
            lower_left = np.array([self.left_H_l, self.left_S_l, self.left_V_l])
            upper_left = np.array([self.left_H_u, self.left_S_u, self.left_V_u])

            # Right lane
            lower_right = np.array([self.right_H_l, self.right_S_l, self.right_V_l])
            upper_right = np.array([self.right_H_u, self.right_S_u, self.right_V_u])

            # Step line
            lower_stepline1 = np.array([self.stepline1_H_l, self.stepline1_S_l, self.stepline1_V_l])
            upper_stepline1 = np.array([self.stepline1_H_u, self.stepline1_S_u, self.stepline1_V_u])
            lower_stepline2 = np.array([self.stepline2_H_l, self.stepline2_S_l, self.stepline2_V_l])
            upper_stepline2 = np.array([self.stepline2_H_u, self.stepline2_S_u, self.stepline2_V_u])




            # Create masks for left, right and stepline colours
            mask_left = cv.inRange(rectangle, lower_left, upper_left)

            if not self.sim:
                rectangle[:350, : : ] = 0
        

            mask_right = cv.inRange(rectangle, lower_right, upper_right)



            kernel = np.ones((15,15), np.uint8)
            mask_left = cv.morphologyEx(mask_left, cv.MORPH_CLOSE, kernel)
            mask_right = cv.morphologyEx(mask_right, cv.MORPH_CLOSE, kernel)

            rectangle = np.copy(hsv)
            if not self.sim:
                pass
                # rectangle[:150, : : ] = 0
            else:
                rectangle[:200, :, :] = 0
                # rectangle[:, :60, :] = 0
                # rectangle[:, 280:, :] = 0

            mask_stepline1 = cv.inRange(rectangle, lower_stepline1, upper_stepline1)
            mask_stepline2 = cv.inRange(rectangle, lower_stepline2, upper_stepline2)
            mask_stepline_inter = cv.bitwise_or(mask_stepline1, mask_stepline2)

            mask_stepline_inter = cv.morphologyEx(mask_stepline_inter, cv.MORPH_CLOSE, kernel)



            # In the real world, the right lane is red, so we use the red colour (with the two ranges). 
            # It's easier to just switch stepline and right than to change everything. 

            if self.sim:
                masked_left = cv.bitwise_and(image, rectangle, mask=mask_left)
                masked_right = cv.bitwise_and(image, rectangle, mask=mask_right)
            else:
                masked_left = cv.bitwise_and(image, rectangle, mask=mask_left)
                masked_right = cv.bitwise_and(image, rectangle, mask=mask_stepline_inter)



            
            # Combine masked images
        
            masked_frame = masked_left + masked_right



            if self.sim:
                stepline_contour, _ = cv.findContours(mask_stepline_inter, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
                masked_stepline = cv.bitwise_and(image, rectangle, mask=mask_stepline_inter)
            else:
                stepline_contour, _ = cv.findContours(mask_right, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
                masked_stepline = cv.bitwise_and(image, rectangle, mask=mask_right)

            
            if len(stepline_contour) > 0:
                largest_contour = max(stepline_contour, key=cv.contourArea)
                cv.drawContours(self.image, [largest_contour], -1, (0, 255, 0), 3)


            area = 0
            for i in stepline_contour:
                stepline_area = cv.contourArea(i)
                if stepline_area>area:
                    area = stepline_area
            
            stepline_area = area


            print("AREA STEPLINE  ", stepline_area)

            # lower = (15000,2400)[self.sim]
            lower = self.stepline_lower_area
            # upper = (30000,3200)[self.sim] 
            upper = self.stepline_upper_area

            # print("range", lower, upper)

            # last_detection_threshold = (6,14)[self.sim and self.step == 2]
            last_detection_threshold = self.stepline_delay
            if self.step == 2 and self.sim:
                last_detection_threshold = 14


            if (stepline_area > lower and stepline_area < upper):
                if (not self.last_detection is None) and (((rospy.Time.now() - self.last_detection).to_sec()) < last_detection_threshold):
                    print("folse detekshion", self.last_detection.to_sec(), ((rospy.Time.now() - self.last_detection).to_sec()))
                    pass
                else:
                    self.detect_stepline = True
            else:
                if self.detect_stepline:
                    rospy.logwarn(f"STEP + 1")
                    self.step +=1
                    self.last_detection = rospy.Time.now()
                    self.detect_stepline = False


            if self.sim:
                contours_left, _ = cv.findContours(mask_left, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
                contours_right, _ = cv.findContours(mask_right, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
            else:
                contours_left, _ = cv.findContours(mask_left, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
                contours_right, _ = cv.findContours(mask_stepline_inter, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)

            left_lane, right_lane = None,None
            # Find the largest contour based on area
            if len(contours_left)>0:
                left_lane = max(contours_left, key=cv.contourArea)
                cv.drawContours(self.image, [left_lane], -1, (0, 255, 0), 3)
            if len(contours_right)>0:
                right_lane = max(contours_right, key=cv.contourArea)
                cv.drawContours(self.image, [right_lane], -1, (255, 255, 0), 3)


            # Calculate the centroid of the largest contour

            if not self.left_lane is None:
                M = cv.moments(left_lane)
            if M["m00"] != 0:
                self.left_lane[1] = int(M["m10"] / M["m00"])
                self.left_lane[0] = int(M["m01"] / M["m00"])
            else:
                self.left_lane = [np.nan, np.nan]
            # Calculate the centroid of the largest contour
            if not self.right_lane is None:
                M = cv.moments(right_lane)
            if M["m00"] != 0:
                self.right_lane[1] = int(M["m10"] / M["m00"])
                self.right_lane[0] = int(M["m01"] / M["m00"])
            else:
                self.right_lane = [np.nan, np.nan]


            center_left = tuple([self.left_lane[1], self.left_lane[0]])
            center_right = tuple([self.right_lane[1], self.right_lane[0]])

            radius = 10 
            colour = (0, 255, 0)  # Green 
            colour2 = (255, 255, 0) # Cyan
            thickness = 2 

            # Draw the circle on the self.image
            if not np.isnan(center_left[0]):
                cv.circle(self.image, center_left, radius, colour, thickness)
            if not np.isnan(center_right[0]):
                cv.circle(self.image, center_right, radius, colour2, thickness)
            # cv.circle(self.image, center_road, radius, colour2, 5)



            image_message = self.bridge.cv2_to_imgmsg(mask_left, "passthrough")
            self.image_pub.publish(image_message)

            
        else:
            pass

    def last_challenge(self):

        if self.occupancy_grid is None:
            rospy.logwarn("No occup grid")
            return
        

        lidar_occup = np.copy(self.occupancy_grid.filled(0))

        
        kernel = np.ones((15,15), np.uint8)



        lidar_occup = np.transpose(np.rot90(lidar_occup, k=2, axes=(1,0)))

        lidar_occup = signal.medfilt2d(lidar_occup, 3)
        print("max", np.max(lidar_occup))


        
        self.occupancy_grid2 = np.zeros((lidar_occup.shape[0], lidar_occup.shape[1], 3), dtype=np.uint8)

        self.occupancy_grid2 = cv.cvtColor(self.occupancy_grid2, cv.COLOR_BGR2GRAY)
        
        self.pathplanner.set_image(self.occupancy_grid2)



        OccuGrid2 = (np.argwhere(lidar_occup == 100))
        # n_clusters_ = 0

        if OccuGrid2.shape[0]: 

            clustering = DBSCAN(eps=3, min_samples=10).fit(OccuGrid2)
            
            labels = clustering.labels_
            n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)

            print("clusters ", n_clusters_)

            unique_labels = set(labels)
            core_samples_mask = np.zeros_like(labels, dtype=bool)
            core_samples_mask[clustering.core_sample_indices_] = True

            colours = [plt.cm.Spectral(each) for each in np.linspace(0, 1, len(unique_labels))]
            for k, col in zip(unique_labels, colours):
                # if k == -1:
                #     # Black used for noise.
                #     col = [0, 0, 0, 1]

                class_member_mask = labels == k

                xy = OccuGrid2[class_member_mask & core_samples_mask]
                print("LEN XY", len(xy))
                if len(xy)>0 and len(xy)<30:
                    x = round(np.mean(xy[:,0]))
                    y = round(np.mean(xy[:,1]))    


                    x, y = self.turtle_to_odom((x,y))

                    matched = False

                    for i in self.bottles:
                        x2, y2 = i.get_position()
                        distance = math.sqrt((x2 - x)**2 + (y2 - y)**2)
                        if abs(distance) < self.same_bottle_threshold:
                            # print(f"matched with an existing bottle, distance: {distance}, pos : {x,y}")
                            i.set_position((x,y))
                            if not i.get_gate() is None:
                                self.gates[i.get_gate()].update(self.bottles)
                            matched = True
                            break
                        else:
                            continue
                    if not matched and not self.confirmed:
                        print("new bottle discovered!", (x,y),)
                        self.bottles.append(Bottle(len(self.bottles), (x,y)))
                    # cv.circle(self.occupancy_grid2, [x,y], 4, (0,255,255), 4)


        potential_neighbors = {}
        neighbors = []
        res_neighbors = {}


        

        target_distance = self.bottles_target_distance
        tolerance = self.bottles_tolerance

        if not self.confirmed:
            for i in range(len(self.bottles)):
                potential_neighbors[i] = []
                for j in range(len(self.bottles)):
                        if i==j:
                            continue
                        x1, y1 = self.bottles[i].get_position()
                        x2, y2 = self.bottles[j].get_position()
                        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                        print("DISTANCE BETWEEN BOTTLES ", distance)
                        if abs(distance - target_distance) < tolerance:
                            print("DISTANCE ", distance, distance - target_distance)
                            potential_neighbors[i].append(j)
                            # print(i,j)
                            
            # print("potential", potential_neighbors)

            for i in potential_neighbors:
                if len(potential_neighbors[i]) == 1:
                    if len(potential_neighbors[potential_neighbors[i][0]]) == 1:
                        if potential_neighbors[potential_neighbors[i][0]][0] == i:
                            # print(f"Neighbors found: {i}, {potential_neighbors[i]}")
                            if not any(i in gate for gate in neighbors):
                                neighbors.append((i, potential_neighbors[i][0]))
                    else: 
                        try:
                            res_neighbors[potential_neighbors[i][0]].append(i)
                        except:
                            res_neighbors[potential_neighbors[i][0]] = [i]

            for i in res_neighbors:
                if len(res_neighbors[i])==1:
                    neighbors.append((i, res_neighbors[i][0]))
                else:
                    pass
                    # print(f"ambiguity for {i}")

            # print("neighbors:", neighbors)


            for i in neighbors:
                if self.bottles[i[0]].get_gate() is None or self.bottles[i[1]].get_gate() is None:
                    pass
                else:
                    if self.bottles[i[0]].get_gate() == self.bottles[i[1]].get_gate():
                        continue
                c1 = self.bottles[i[0]].get_position()
                c2 = self.bottles[i[1]].get_position()

                cX = np.mean([c1[0],c2[0]])
                cY = np.mean([c1[1],c2[1]])

                # self.occupancy_grid2[cX,cY] = 127

                self.bottles[i[0]].set_gate(len(self.gates))
                self.bottles[i[1]].set_gate(len(self.gates))

                self.gates.append(Gate(center_position=(cX,cY), bottle_index1=self.bottles[i[0]].get_index(), bottle_index2=self.bottles[i[1]].get_index()))
                # cv.circle(self.occupancy_grid2, [cX,cY], 2, (0,255,0), 3)
        nb = {}

        for g in range(0,len(self.gates)):
            nb[g] = 0


        for i in self.bottles:
            # print(i.get_position())
            if not i.get_gate() is None:
                try:    
                    nb[i.get_gate()] += 1

                    if self.gates[i.get_gate()].get_colour() == self.order[self.current_index] and self.found_colours:
                        pass
                        # print("Opened target gate")
                    else:
                        # self.occupancy_grid2[self.gates[i.get_gate()].get_center_pos()[0], self.gates[i.get_gate()].get_center_pos()[1]] = 127
                        b1,b2 = self.gates[i.get_gate()].get_bottles_indices()
                        cells = list(self.traverse_grid(self.odom_to_grid(self.bottles[b1].get_position()), self.odom_to_grid(self.bottles[b2].get_position())))
                        # print(b1, b2)
                        # print(self.odom_to_grid(self.bottles[b1].get_position()))
                        # print(self.odom_to_grid(self.bottles[b2].get_position()))
                        for c in cells:
                            try:
                                self.occupancy_grid2[c[0],c[1]] = 127
                            except:
                                continue
                except:
                    pass
            try:
                pos = self.odom_to_grid(i.get_position())
                self.occupancy_grid2[pos[0],pos[1]] = 100
            except:
                pass
            # cv.circle(occu_grid35, [i.get_position()[0],i.get_position()[1]], 1, (0,255,0), 2)  

        self.active_gates = [key for key, value in nb.items() if value == 2]

        # for i in self.active_gates:
        #     p1, p2 = self.gates[i].get_offset_points()
        #     if p1 is None or p2 is None:
        #         continue
        #     self.occupancy_grid2[round(p1[0]), round(p1[1])] = 66
        #     self.occupancy_grid2[round(p2[0]), round(p2[1])] = 66

        if len(self.active_gates) == 3 and not self.confirmed:
            self.confirmed = True
            rospy.logwarn("found all gates!")
            for i in self.active_gates:
                self.gates[i].confirm()

        # print("Active gates ", len(self.active_gates))
        # print("nb bottles: ", len(self.bottles))

        self.merge_occup_grids()
        self.last_challenge2()
        pass

    def last_challenge2(self):

        goal_point = None

        self.image_rect = np.copy(self.cv_image_rect)


        try:
            hsv = cv.cvtColor(self.cv_image_rect, cv.COLOR_BGR2HSV)
        except:
            print("ERROR WITH THE HSV?")
            return

        # Blue lane
        BlueBottle_l = np.array([self.blue_H_l, self.blue_S_l, self.blue_V_l])
        BlueBottle_u = np.array([self.blue_H_u, self.blue_S_u, self.blue_V_u])

		# Green lane
        GreenBottle_l = np.array([self.green_H_l, self.green_S_l, self.green_V_l])
        GreenBottle_u = np.array([self.green_H_u, self.green_S_u, self.green_V_u])


        yellowBottle_l = np.array([self.yellow_H_l, self.yellow_S_l, self.yellow_V_l])
        yellowBottle_u = np.array([self.yellow_H_u, self.yellow_S_u, self.yellow_V_u])
        mask_yellow = cv.inRange(hsv, yellowBottle_l, yellowBottle_u)

        mask_blue = cv.inRange(hsv, BlueBottle_l, BlueBottle_u)
        mask_green = cv.inRange(hsv, GreenBottle_l, GreenBottle_u)

        contours_blue, _ = cv.findContours(mask_blue, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
        contours_green, _ = cv.findContours(mask_green, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
        contours_yellow, _ = cv.findContours(mask_yellow, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)


        # threshold = (6000, 200)[self.sim]
        threshold = self.bottles_area_threshold



        yellow_bottles = []
        green_bottles = []
        blue_bottles = []

        for i in contours_blue:
            if cv.contourArea(i) > threshold:
                print("contour blue area: ", cv.contourArea(i))
                M = cv.moments(i)
                if M["m00"] != 0:
                    y = int(M["m10"] / M["m00"])
                    x = int(M["m01"] / M["m00"])
                    blue_bottles.append([x,y, cv.contourArea(i)])
                cv.drawContours(self.image_rect, [i], -1, (255, 20, 20), 3)

        for i in contours_green:
            if cv.contourArea(i) > threshold:
                # print("contour green area: ", cv.contourArea(i))
                M = cv.moments(i)
                if M["m00"] != 0:
                    y = int(M["m10"] / M["m00"])
                    x = int(M["m01"] / M["m00"])
                    green_bottles.append([x,y, cv.contourArea(i)])
                cv.drawContours(self.image_rect, [i], -1, (20, 255, 20), 3)

        for i in contours_yellow:
            if cv.contourArea(i) > threshold:
                # print("contour yellow area: ", cv.contourArea(i))
                M = cv.moments(i)
                if M["m00"] != 0:
                    y = int(M["m10"] / M["m00"])
                    x = int(M["m01"] / M["m00"])
                    yellow_bottles.append([x,y, cv.contourArea(i)])
                cv.drawContours(self.image_rect, [i], -1, (20, 20, 255), 3)

        #0 blue, 1 green, 2 yellow
        gates = {0:[None, None], 1:[None, None], 2:[None, None]}

        if len(yellow_bottles) == 2:
            avg_area_yellow = (yellow_bottles[0][2] + yellow_bottles[1][2]) * 0.5
            center_yellow = (yellow_bottles[0][1] + 0.5*(yellow_bottles[1][1] - yellow_bottles[0][1]))

            offcenter_yellow = center_yellow - (self.image_rect.shape[1] * 0.5)

            gates[2] = [offcenter_yellow, avg_area_yellow]
        
        if len(blue_bottles) == 2:
            avg_area_blue = (blue_bottles[0][2] + blue_bottles[1][2]) * 0.5
            center_blue = (blue_bottles[0][1] + 0.5*(blue_bottles[1][1] - blue_bottles[0][1]))

            offcenter_blue = center_blue - (self.image_rect.shape[1] * 0.5)

            gates[0] = [offcenter_blue, avg_area_blue]
        
        if len(green_bottles) == 2:
            avg_area_green = (green_bottles[0][2] + green_bottles[1][2]) * 0.5
            center_green = (green_bottles[0][1] + 0.5*(green_bottles[1][1] - green_bottles[0][1]))

            offcenter_green = center_green - (self.image_rect.shape[1] * 0.5)

            gates[1] = [offcenter_green, avg_area_green]


        possible_pairing = {0: [], 1: [], 2: []}

        for i in self.active_gates:
            if self.gates[i].get_colour() is None:
                center = self.odom_to_grid(self.gates[i].get_center_pos())
                local_center = (self.occupancy_grid.shape[1] - center[0], center[1] - 0.5*self.occupancy_grid.shape[0])
                angle = math.atan2(local_center[1], local_center[0])
                distance = math.sqrt(local_center[0]**2 + local_center[1]**2)
                # print("distna", distance)
                if abs(angle) < 0.3 and distance < 45:
                    for key, value in gates.items():
                        if value[0] is None:
                            continue
                        else:
                            if abs(value[0] - angle*10) < 30:
                                possible_pairing[key].append(i)

        for colour, gate in possible_pairing.items():
            if len(gate) == 1:
                rospy.logwarn(f"FOUND colour FOR GATE {gate}, colour IS {colour}")
                self.gates[gate[0]].set_colour(colour, self.bottles)

        for gate in self.active_gates:
            print(gate, self.gates[gate].get_colour())




        if self.state == 0:
            colours = [0,1,2]
            unassigned_gates = []

            for i in self.active_gates:
                if not self.gates[i].get_colour() is None:
                    colours.remove(self.gates[i].get_colour())
                else:
                    unassigned_gates.append(i)


            # print("remaingin colours, unassigned_gates ", colours, unassigned_gates)


            if len(colours) == 1 and len(unassigned_gates) == 1:
                rospy.logwarn(f"FOUND REMAINING colour FOR GATE {unassigned_gates[0]}, colour IS {colours[0]}")
                self.gates[unassigned_gates[0]].set_colour(colours[0], self.bottles)
            elif len(colours) == 1:
                for i in self.bottles:
                    if i.get_gate() is None:
                        # print(f"Go to this position {i.get_position()}")
                        goal_point = np.array(i.get_position())


            points = []
            distances = []
            indices = []
            if len(colours) > 0:
                # print("Not found the one we want yet. We'll explore a bit.")
                for i in self.active_gates:
                    if self.gates[i].get_colour() is None:
                        if not self.gates[i].get_offset_points()[0] is None:
                            point, dist = self.closest_point(self.gates[i].get_offset_points())
                            points.append(point)
                            distances.append(dist)
                            indices.append(i)
                            
            else:
                for i in self.active_gates:
                    if self.gates[i].get_colour() == self.order[self.current_index]:
                        # print("GOING TO THE CORRECT ONE!")
                        self.found_colours = True
                        self.state = 1
                        goal_point = self.closest_point(self.gates[i].get_offset_points())[0]
                        self.target_gate = i

            if len(points)>0:
                # print("Closest point :" , points[np.argmin(distances)])
                self.target_gate = indices[np.argmin(distances)]
                goal_point = points[np.argmin(distances)]


        elif self.state == 1:
            for i in self.active_gates:
                    if self.gates[i].get_colour() == self.order[self.current_index]:
                        # print("GOING TO THE CORRECT ONE!")
                        self.found_colours = True
                        self.state = 1
                        goal_point = self.closest_point(self.gates[i].get_offset_points())[0]
                        self.target_gate = i
            goal_point = self.closest_point(self.gates[self.target_gate].get_offset_points())[0]
        elif self.state == 2:
            goal_point = self.closest_point(self.gates[self.target_gate].get_offset_points(), closest=False)[0]
        # elif self.state == 1:
        #     goal_point = self.closest_point(self.gates[i].get_offset_points())[0]
        # elif self.state == 2:
        #     #Get opposite point
        #     goal_point = self.closest_point(self.gates[i].get_offset_points(), closest=False)[0]

        image_message = self.bridge.cv2_to_imgmsg(self.image_rect, "passthrough")
        self.image_pub.publish(image_message)

        if not goal_point is None:
            self.path_planning(goal_point)

        


    def closest_point(self, points, closest=True):
        
        point1 = self.odom_to_grid(points[0])
        point2 = self.odom_to_grid(points[1])

        

        # local_center = (self.occupancy_grid.shape[1] - center[0], center[1] - 0.5*self.occupancy_grid.shape[0])
        p1 = (self.occupancy_grid.shape[1] - point1[0], point1[1] - 0.5*self.occupancy_grid.shape[0])
        p2 = (self.occupancy_grid.shape[1] - point2[0], point2[1] - 0.5*self.occupancy_grid.shape[0])
 
        d1 = math.sqrt(p1[0]**2 + p1[1]**2)
        d2 = math.sqrt(p2[0]**2 + p2[1]**2)

        if closest:
            if d1 < d2:
                return point1, d1
            else:
                return point2, d2
        else:
            if d1 > d2:
                return point1, d1
            else:
                return point2, d2
            
            
    def path_planning(self, goal):


        goal = np.array(goal, dtype=np.int16)

        print("state ", self.state)

        self.cmd_speed = self.max_speed

        if goal[1] >= self.occupancy_grid.shape[0]:
            goal[1] = self.occupancy_grid.shape[0]-1
        if goal[0] >= self.occupancy_grid.shape[1]:
                goal[0] = self.occupancy_grid.shape[1]-1

        # print("GOAL", goal, self.occupancy_grid.shape, self.occupancy_grid2.shape)

        lidar_occup = np.copy(self.occupancy_grid2)

        # lidar_occup = np.transpose(np.rot90(lidar_occup, k=2, axes=(1,0)))

        # lidar_occup = signal.medfilt2d(lidar_occup, 3)

        occu_grid_cp = (lidar_occup > 95)


        # Create a structuring element (disk) corresponding to half the robot's width
        selem = disk(3)  # 'radius' should be set to half the robot's width in pixels

        # Dilate the obstacle map
        inflated_obstacles = dilation(occu_grid_cp, selem)
        inflated_obstacles = np.where(inflated_obstacles, 0, 100)


        self.pathplanner.set_image(inflated_obstacles)

        # self.occupancy_grid2 = inflated_obstacles

        self.publish_occupancy_grid()


        # print("starting path planning")

        goals = self.pathplanner.plan(goal)
        # print("waypoints : ", goals)
        waypoint = goals[1]

        if waypoint is None:
            # self.cmd_speed = 0
            local_waypoint = np.array((10, 0))
        else:
            local_waypoint = np.array((self.occupancy_grid2.shape[0] - waypoint[0], waypoint[1] - 0.5 * self.occupancy_grid2.shape[1]))

        distance = np.linalg.norm(local_waypoint)

        # print(f"Distance to waypoint {distance}, state {self.state}, current index {self.current_index}")
        if self.state == 2 and not self.target_gate is None:
            if (abs(self.odom_to_grid(self.gates[self.target_gate].get_center_pos())[0] - self.occupancy_grid.shape[1] ) < 3) and (abs(self.odom_to_grid(self.gates[self.target_gate].get_center_pos())[1] - (self.occupancy_grid.shape[0] * 0.5) ) < 4):
                rospy.logwarn("TRANSITED")
                self.state = 1
                self.current_index += 1

        if distance < 5.0 and not self.found_colours:  

            target_point, _ = self.closest_point(self.gates[self.target_gate].get_offset_points(), closest=False)
            # print("Target point: ", target_point)
            heading = math.atan2(target_point[1], target_point[0])
            Kp = (1.5, -1.5)[self.sim]
            self.ang_vel = np.sign(heading) * 0.75
            self.cmd_speed = 0




        elif distance < 5.0 and self.found_colours and not self.state==2:
            # print("Transitting.")
            self.state = 2
        # elif distance < 5.0 and self.found_colours and self.state == 2:
        #     rospy.logwarn("Transitted.")
        #     self.current_index += 1
        #     self.state = 1
        elif not distance < 5.0:
            heading = math.atan2(local_waypoint[1], local_waypoint[0])

            # print("DISTANDHEADINIG", distance, heading)

            for i in goals[1:]:
                pass
                # self.occupancy_grid2[int(i[0]),int(i[1])] = 0

            
            
            Kp = (-1.5, -1.5)[self.sim]
            if abs(heading) > (0.3,0.6)[self.sim]:
                self.cmd_speed = 0.
            self.ang_vel = heading * -1.5
        


        

        

        # print("ang_vel", self.ang_vel)
        pass

if __name__ == "__main__":
    rospy.init_node("lane_detection", anonymous = True)
    turtle_controller = TurtleController()
    rate = rospy.Rate(10)
    while(not rospy.is_shutdown()):
        # Run it at a fixed rate
        # Helps with differentiation, timeouts, etc
        turtle_controller.make_cmd()
        rate.sleep()

    stop = Twist()
    stop.angular.z = 0
    stop.linear.x = 0
    turtle_controller.cmd_vel_pub.publish(stop)