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

parser.add_argument('--discover', 
                    help = 'Force Discovery of Chromecasts', 
                    action = 'store_true')

args = vars(parser.parse_args())
cast_name = args['name']
discover_mode = args['discover']

# Determine home directory
home = os.path.expanduser("~")

discovered_devices_file = '/tmp/castdevices'

# Scan if no device specified
if (cast_name == ""):
    # Initial value always off
    # special keyword

    if (discover_mode or 
            not os.path.exists(discovered_devices_file)):
        # Use pychromecast to discover
        print("Discovering Chromecasts.. (this may take a while)")
        devices, browser = pychromecast.get_chromecasts()
        print("Found %d devices" % (len(devices)))

        # Default "off" device
        device_list = ['Disabled']
        for cc in devices:
            device_list.append(cc.device.friendly_name)

        # Store discovered 
        f = open(discovered_devices_file, "w")
        for device in device_list:
            f.write("%s\n" % (device))
        f.close()

    else:
        # Use existing cached list of discovered devices
        # updated every minute by the main script
        device_list = []
        with open(discovered_devices_file) as f:
            devices = f.read().splitlines()
            for device in devices:
                device_list.append(device)

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
    cfg_file = open(home + '/.castrc', 'w') 
    json_cfg = {}
    json_cfg['chromecast'] = cast_name
    cfg_file.write('%s\n' % (json.dumps(json_cfg)))
    cfg_file.close()
