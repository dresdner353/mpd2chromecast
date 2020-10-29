#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import argparse
import os
import json

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

# Scan if no device specified
if (cast_name == ""):
    print("Discovering Chromecasts.. (this may take a while)")
    devices, browser = pychromecast.get_chromecasts()
    total_devices = len(devices)
    print("Found %d devices" % (total_devices))

    # First item in list is keyword 'off'
    total_devices += 1 
    device_list = ['off']
    for cc in devices:
        device_list.append(cc.device.friendly_name)

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
    cfg_file = open(home + '/.castrc', 'w') 
    json_cfg = {}
    json_cfg['chromecast'] = cast_name
    cfg_file.write('%s\n' % (json.dumps(json_cfg)))
    cfg_file.close()
