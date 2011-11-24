#!/usr/bin/env python
"""
    As far as I am aware cwiid is only avaiable on linux
    The requirements are as follows:
    A working linux bluetooth device!! 
    (http://www.wiili.org/index.php/Compatible_Bluetooth_Devices)
    ====================
    Bluetooth libraries
    ====================
    bluez-utils
    libbluetooth-dev  
    libbluetooth2
 
    ====================
    cwiid software
    ====================
    libcwiid1
    libcwiid1-dev
    python-cwiid


    The below python OSC libraries can be installed using pip.
    The version numbers indicate what I have installed on my system (as
    reported by '>>> pip freeze'
    ====================
    OSC libraries
    ====================
    SimpleOSC==0.3
    pyOSC==0.3.5b-5294

    Pitch and roll calculations were learned from the following document:


    This code is all rather exploratory at the moment.Don't expect it to work!

"""
# Standard library imports
from __future__ import division
import sys
from time import sleep
from math import atan, cos, pi

# Third party libraries
from OSC import OSCClient, OSCMessage, OSCClientError
import cwiid
from cwiid import Wiimote


def listen(w, my_map, freq=0.01):
    """
        Receives an initiliased wiimote to talk to, a 
        wiimote my_mapping object, along with a frequency with which to 
        send messages to the client.

    """
    try:
        while True:   
            sleep(freq)         
            my_map.update_state(w.state)
    except KeyboardInterrupt, e:
        return w
    except OSCClientError, e:
        print("OSC client error has occurred: '%s' \n \
            Is there a server listening at %s ? \n Exiting program." 
                % (e, my_map.address)
        )
        return w

def setup():
    """
        Makes the connection with the wiimote
    """
    ready = raw_input("Press 1 and 2 simultaenously on the wiimote. \
        \n Click any key when done")
    try:
        w = Wiimote()
    except RuntimeError, e:
        print("Error has occured: '%s'. Please ensure wiimote is active by \
            pressing 1 and 2 simulataenoulsy till the control lights up." % e)
        raise e
    w.rpt_mode = cwiid.RPT_ACC | cwiid.RPT_NUNCHUK | cwiid.RPT_BTN
    remote_cal = w.get_acc_cal(cwiid.EXT_NONE)
    try:
        nunchuk_cal = w.get_acc_cal(cwiid.EXT_NUNCHUK)
    except RuntimeError, e:
        print("Nunchuk not detected...disabling support...")
        nunchuk_cal = None
            
    return w, remote_cal, nunchuk_cal

full_mapping = lambda state: \
    dict([('buttons', state['buttons']) ,
        ('acc', state['acc']), ('nunchuk', state['nunchuk'])])
mapping_no_nunchuk = lambda state: \
    dict([('buttons', state['buttons']),('acc', state['acc'])])

class Wiimy_mapping(object):
    """
        Class designed to send the wiimote state via OSC.
        Sends acc, nunchuk and buttons state messages from cwiid.
        This is a base class template, it ought to be extended
        to implement specific mapping strategies.
        acc, buttons and nunchuk can be overriden.
        
    """


    def __init__(self, address=('localhost', 5600)):
        """ Set up a connection to the address specified. """ 
        self.client = OSCClient()
        self.address = address
        self.prev_state = None


    def set_acc_cal(self, remote_cal, nunchuk_cal=None):
        """
            Receives the initial calibration values for
            the remote and the nunchuk. These are used to 
            calculate pitch and roll :)

        """
        self.cal_r_x = \
            remote_cal[0][0] /(remote_cal[1][0] - remote_cal[0][0])
        self.cal_r_y = \
            remote_cal[0][1] /(remote_cal[1][1] - remote_cal[0][1])
        self.cal_r_z = \
            remote_cal[0][2] /(remote_cal[1][2] - remote_cal[0][2])
        if nunchuk_cal:
            self.cal_n_x = \
                nunchuk_cal[0][0] /(nunchuk_cal[1][0] - nunchuk_cal[0][0])
            self.cal_n_y = \
                nunchuk_cal[0][1] /(nunchuk_cal[1][1] - nunchuk_cal[0][1])
            self.cal_n_z = \
                nunchuk_cal[0][2] /(nunchuk_cal[1][2] - nunchuk_cal[0][2])

    def update_state(self, state):
        """
            
        """
        if hasattr(self, 'cal_n_x'):
            state = full_mapping(state)
        else:
            state = mapping_no_nunchuk(state)
        if self.prev_state:
           for k in state:
               if not self.prev_state[k] == state[k]:
                   getattr(self, k)(state[k])
           self.prev_state = state     
        else:
            self.prev_state = state
            for k in state.keys():
                getattr(self, k)(state[k])
        
        
    def acc(self, state):
        """ 
            Extract acceleration, pitch and roll from the wiimote.
            Stub method which can be extended in a subclass to 
            implement specific mappping strategies and send custom messages.

        """
        # Normalise values and calculate pitch and roll
        a_x = state[0] - self.cal_r_x
        a_y = state[2] - self.cal_r_y
        a_z = state[1] - self.cal_r_z
        roll = atan(a_x/a_z)
        if a_z < 0.0:
            if a_x > 0.0:
                roll += pi
            else:
                roll += (pi * -1)
        roll *= -1
        pitch = atan(a_y/a_z*cos(roll))

        # Send OSC message to the server
        msg = OSCMessage('/acc')
        msg.append((a_x, a_z, a_y, pitch, roll))
        self.client.sendto(msg=msg, address=self.address)

    def buttons(self, state):
        """ 
            Stub method which can be extended in a subclass to 
            implement specific mappping strategies and send custom messages.
            The state parameter is a number. When no buttons are pressed 
            state is 0. Each button has it's own number but when multiple
            buttons are pressed these numbers are added together in the state
            variable.

            TODO: List all the button numbers here for convenience.

        """
        pass

    def nunchuk(self, state):
        """ 
            Receive all nunchuk info here: this method should be 
            overriden.

        """
        pass


class WiiphoneMapping(Wiimy_mapping):
    """
        Experimental class exploring nice mappings
        for the wiiphone instrument.
        
    """

    def __init__(self, address=('localhost', 5600)):
        """
        """
        
        super(WiiphoneMapping, self).__init__(address)
        self.pos = 1
        self.root_note = 60 # Root note of the scale (midi note number)
        self.hold = False # Hold position variable
        self.raise_wii = False # Have we raised the remote?
        

    def acc(self, state):
        """ 
            Send messages related to the acceleration values


        """
        # Need to calculate pitch and roll here...
        a_x = state[0] - self.cal_r_x
        a_y = state[1] - self.cal_r_y
        a_z = state[2] - self.cal_r_z
        roll = atan(a_x/a_z)
        if a_z < 0.0:
            if a_x > 0.0:
                roll += pi
            else:
                roll += (pi * -1)
        roll *= -1
        pitch = atan(a_y/a_z*cos(roll))
        msg = OSCMessage('/wii/acc')
        # Hack x and y values to make it easy to play the patch
        if a_x <= 93:
            a_x = 55
        elif a_x <=103:
            a_x = 75
        elif a_x <= 112:
            a_x = 93
        elif a_x <= 123:
            a_x = 120
        elif a_x <= 133:
            a_x = 140
        a_y = (((a_y-40)/160) * 100) + 20
        print("y is: %f, x is %f" % (a_y, a_x))
        if not self.raise_wii and a_z < a_y:
            self.raise_wii = True
            self.track_acc_vals = []
        if self.raise_wii:
            self.track_acc_vals.append((a_y, a_z))
            if a_z >= a_y:
                print ("Detecting a hit... \
                    Here are the tracked values: %s" % self.track_acc_vals)
                msg = OSCMessage('/wii/hit')
                msg.append(a_z)
                self.client.sendto(msg=msg, address=self.address)
                self.raise_wii = False
        msg = OSCMessage('/wii/acc')
        msg.append((a_x, a_y, a_z))
        self.client.sendto(msg=msg, address=self.address)
        msg = OSCMessage('/wii/orientation')
        msg.append((pitch, roll))
        self.client.sendto(msg=msg, address=self.address)

    def buttons(self, state):
        """ Extract button A, minus and plus only. """

        msg_a = OSCMessage('/wii/button/a')
        msg_minus = OSCMessage('/wii/button/minus')
        msg_plus = OSCMessage('/wii/button/plus')
        a = 0
        minus = 0
        plus = 0
        
        if state in (8, 24, 4104, 4120):
            a = 1
        if state in (16, 24, 4104, 4120):
            minus = 1
        if state in (4096, 24, 4104, 4120):
            plus = 1
        msg_a.append(a)
        msg_minus.append(minus)
        msg_plus.append(plus)
        self.client.sendto(msg=msg_a, address=self.address)
        self.client.sendto(msg=msg_minus, address=self.address)
        self.client.sendto(msg=msg_plus, address=self.address)
        msg_hold = OSCMessage('/wii/hold')
        if state == 4 and not self.hold:
            self.hold = True
            msg_hold.append(1)
            self.client.sendto(msg=msg_hold, address=self.address)
        if state == 0:
            self.hold = False
            msg_hold.append(0)
            self.client.sendto(msg=msg_hold, address=self.address)

        if state == 2048:
            msg_up = OSCMessage('/wii/button/up')
            self.root_note += 1
            msg_up.append(self.root_note)
            self.client.sendto(msg=msg_up, address=self.address)
        if state == 1024:
            msg_down = OSCMessage('/wii/button/down')
            self.root_note -= 1
            msg_down.append(self.root_note) 
            self.client.sendto(msg=msg_down, address=self.address)

    def nunchuk(self, state):
        """ 
            Map the nunchuk

        """
        # Need to calculate pitch and roll here...
        a_x = state['acc'][0] - self.cal_n_x
        a_y = state['acc'][1] - self.cal_n_y
        a_z = state['acc'][2] - self.cal_n_z
        roll = atan(a_x/a_z)
        pitch = atan(a_y/a_z*cos(roll))
        msg = OSCMessage('/nunchuk/acc')
        msg.append((a_x, a_y, a_z))
        self.client.sendto(msg=msg, address=self.address)
        msg = OSCMessage('/nunchuk/orientation')
        msg.append((pitch, roll))
        self.client.sendto(msg=msg, address=self.address)
        msg = OSCMessage('/nunchuk/joystick')
        msg.append(state['stick'])
        self.client.sendto(msg=msg, address=self.address)
        msg_z = OSCMessage('/nunchuk/button/z')
        msg_c = OSCMessage('/nunchuk/button/c')
        z = 0
        c = 0
        if state['buttons'] in [1, 3]:
            z = 1
        if state['buttons'] in [2,3]:
            c = 1
        msg_z.append(z)
        msg_c.append(c)
        self.client.sendto(msg=msg_z, address=self.address)
        self.client.sendto(msg=msg_c, address=self.address)
            

    
if __name__ == '__main__':
    if len(sys.argv) == 3:
        print ("Expecting arg1 to be server address and arg2 to be the port")
        address = (sys.argv[1], sys.argv[2])
    else:
        add = ('localhost', 5600)
    my_map = WiiphoneMapping(add)
    (w, remote_cal, nunchuk_cal) = setup()
    my_map.set_acc_cal(remote_cal, nunchuk_cal)
    listen(w, my_map)  
        
