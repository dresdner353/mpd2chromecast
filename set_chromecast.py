#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import argparse
import os
import time
import sys
import json


def load_config():
    global gv_cfg_filename
    global gv_cfg_dict

    cfg_file = open(gv_cfg_filename, 'r')
    json_str = cfg_file.read()
    gv_cfg_dict = json.loads(json_str)
    cfg_file.close()

    return 


def save_config():
    global gv_cfg_filename
    global gv_cfg_dict

    cfg_file = open(gv_cfg_filename, 'w') 
    cfg_file.write('%s\n' % (json.dumps(gv_cfg_dict)))
    cfg_file.close()

    return 
# main

parser = argparse.ArgumentParser(
        description='Set Desired Chromecast')

parser.add_argument('--name', 
                    help = 'Chromecast Friendly Name', 
                    default = "",
                    required = False)

args = vars(parser.parse_args())
cast_name = args['name']

# Determine home directory
home = os.path.expanduser("~")
gv_cfg_filename = home + '/.mpd2chromecast'   

# config defaults
gv_cfg_dict = {}
gv_cfg_dict['castDevice'] = 'Disabled'
gv_cfg_dict['castMode'] = 'direct'

if os.path.exists(gv_cfg_filename):
    load_config()

# Scan if no device specified
if (cast_name == ""):
    # Initial value always off
    # special keyword

    # Use pychromecast to discover
    print("Discovering Chromecasts.. (this may take a while)")
    devices, browser = pychromecast.get_chromecasts()
    print("Found %d devices" % (len(devices)))

    # build list of discovered devices and sort
    device_list = []
    for cc in devices:
        device_list.append(cc.device.friendly_name)
    device_list.sort()
    # prepend Default "off" device
    device_list = ['Disabled'] + device_list

    # Display and select
    total_devices = len(device_list)
    index = 0
    for device in device_list:
        print("%2d   %s" % (index, device))
        index += 1

    index = int(input("Enter device number: "))
    if (index < 0 or index >= total_devices):
        print("Invalid selection.. should be in range 0..%d" % (total_devices - 1))
    else:
        cast_name = device_list[index]

if cast_name != "":
    print("Setting desired Chromecast to [%s]" % (cast_name))
    gv_cfg_dict['castDevice'] = cast_name
    save_config()
